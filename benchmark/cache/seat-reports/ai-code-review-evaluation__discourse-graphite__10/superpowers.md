I reviewed the patch myself, as the override required (no subagent). I loaded `superpowers:requesting-code-review` and used its Critical/Important/Minor scale, reading the code around the patch at head d1c69189f3. I did not run any tests or install anything, so every claim below is reasoned from the code. There was no spec, so I reviewed against the commit's intent: move embeddable hosts from a site setting into a table, with a category for each host.

## Findings

1. **db/migrate/20150818190757_create_embeddable_hosts.rb:9-11 and :15 — Critical.** The migration crashes when the `embed_category` row does not exist.
   - Discourse only stores site settings that differ from their default, and `embed_category` defaulted to `''`. Most installs therefore have no such row, and on those the SELECT returns 0 rows.
   - `execute(...)[0]['id']` then indexes an empty `PG::Result`. With pg 0.18.1 (Gemfile.lock:220), `PG::Result#[]` raises `IndexError` ("Index 0 is out of range") for an out-of-range row; it does not return nil.
   - The fallback on line 15 has the same pattern for `uncategorized_category_id`. That row is seeded by fixtures after migrations run, so on a fresh database (`rake db:create db:migrate`, which CI does) both lookups hit 0 rows.
   - Result: upgrades fail on most production sites, and fresh setups fail.
   - Failing check: on an empty test DB, `RAILS_ENV=test bundle exec rake db:drop db:create db:migrate` should abort at this migration with `IndexError`. Lines 18-20 show the right pattern: check `cmd_tuples > 0` before indexing.

2. **db/migrate/20150818190757_create_embeddable_hosts.rb:22-25 — Important.** Migrated hosts are copied verbatim, so existing allowed hosts stop matching.
   - The old `SiteSetting.allows_embeddable_host?` accepted values with a scheme. The removed spec cases "works with a http host" and "works with a https host" covered `http://eviltrout.com` and `https://eviltrout.com`.
   - The migration inserts raw strings and skips the model's `before_validation`, which strips the scheme and path. A value like `http://eviltrout.com` or `https://example.com/1234` is stored as-is.
   - `EmbeddableHost.record_for_host` (app/models/embeddable_host.rb:17) compares `lower(host) = uri.host`, which never matches a stored scheme or path.
   - After the upgrade, those sites get `InvalidAccess` on every embed request (EmbedController#ensure_embeddable) and in TopicRetriever.
   - The interpolated `'#{h}'` also aborts the migration on any value containing `'`. Trailing `\r` or whitespace from the old textarea is kept too.
   - Failing check: seed `site_settings(name='embeddable_hosts', value='http://eviltrout.com')`, run the migration, then `EmbeddableHost.host_allowed?('http://eviltrout.com/x')` returns false.

3. **app/models/topic_embed.rb:43 — Important (behaviour change).** Topics imported from the RSS/Atom feed (`feed_polling_url`) used to go to `SiteSetting.embed_category`. Now the category comes from `EmbeddableHost.record_for_host(url)`. If the feed's article host is not in the allowed-hosts table, `eh` is false and the category is nil, so the topic lands in Uncategorized. The setting was deleted and nothing replaces it for feed imports, so admins lose the ability to choose that category.

4. **app/models/embeddable_host.rb:5-8 — Minor.** `self.host.sub!` throws `NoMethodError` when `host` is nil. The controller passes `params[:embeddable_host][:host]` straight through (app/controllers/admin/embeddable_hosts_controller.rb:22), so a request with no host returns a 500 instead of a validation error. Admin-only.

5. **app/models/embeddable_host.rb:2 vs :14-17 — Minor.** The validation regex allows a port (`:[0-9]{1,5}`), but `record_for_host` compares against `uri.host`, which has no port. A host saved as `example.com:8080` is accepted and never matches. The regex also rejects `localhost`, IP addresses and TLDs over 5 characters, so such hosts carried over by the migration can't be re-saved from the UI.

6. **app/models/embeddable_host.rb:17 — Minor.** The column side is lowercased, but `uri.host` is not. TopicRetriever passes the raw `embed_url`, so `http://EvilTrout.com/x` fails. TopicEmbed is unaffected because it calls `normalize_url` first.

7. **app/controllers/admin/embeddable_hosts_controller.rb:9-17 — Minor.** In `update` and `destroy`, `where(id:).first` followed by `host.destroy` or `save_host(host)` raises `NoMethodError` (a 500) for an unknown id, where a 404 would be expected.

8. **app/assets/javascripts/discourse/models/store.js.es6:197-201 — Minor.**
   - The new `_ids` branch always deletes `obj[k]`, even when `_lookupSubType` returns undefined (no sideloaded collection). The singular `_id` branch only does this when hydration succeeds.
   - Any future REST payload with a `foo_ids` array of unsideloaded ids would lose the ids and get an array of `undefined`. A null `_ids` value would throw on `.map`.
   - `hydrated || []` never does anything, because `.map` always returns an array.
   - No current `rest_serializer` endpoint sends `_ids` keys (I checked queued_posts and similar_topics), so this is not live yet.

9. **app/assets/javascripts/discourse/adapters/rest.js.es6:22 — Minor.** `type.replace('_', '-')` only replaces the first underscore. A future admin model with two underscores would resolve to the wrong base path.

10. **app/assets/javascripts/admin/components/embeddable-host.js.es6:9, :34, :38 — Minor.** For a new host, `categoryId` stays null unless the chooser is touched. The server then assigns uncategorized, but the client sets `category` to `Discourse.Category.findById(null)` (undefined), so the badge is blank until the page reloads. In `delete`, `destroyRecord()` has no `.catch(popupAjaxError)`, so errors are silently swallowed.

11. **app/controllers/admin/embedding_controller.rb:9-11 and app/assets/javascripts/admin/controllers/admin-embedding.js.es6:5 — Minor.** `update` changes nothing, and the `saveChanges` action is never used by any template. It is a dead PUT route plus dead client code.

12. **db/migrate/20150818190757_create_embeddable_hosts.rb:3 — Minor.**
    - There is no unique index on `host`, and the model has no uniqueness validation. With duplicate hosts, `.first` picks the category arbitrarily.
    - Nothing handles a deleted category: there is no FK or `dependent`, so the stale `category_id` makes imported topics silently uncategorized.
    - `change` uses irreversible `execute` calls and deletes the old settings. Rollback raises, and the old data is gone.

13. **spec/fabricators/category_fabricator.rb and spec/fabricators/embeddable_host_fabricator.rb — Minor.** The contents are swapped: `category_fabricator.rb` now defines `:embeddable_host`, and `embeddable_host_fabricator.rb` holds all the category fabricators. It works because Fabrication loads every file, but the git history and file layout are now wrong.

14. **test/javascripts/models/store-test.js.es6:111 — Minor.** The test calls `store.find('fruit', 2)`, but the pretender `/fruits/:id` handler always returns `fruits[0]` (apple, `color_ids: [1,2]`). The assertions about two colours with ids 1 and 2 pass only because of that; banana has `[3]`. The test is misleading.

15. **spec/models/topic_spec.rb:1397-1427 and app/models/topic.rb:869 — Minor.** The `embeddable_hosts.present?` guard was removed from `expandable_first_post?`. The spec "is false if embeddable_host is blank" now passes only because `embed_truncate` defaults to false, so it no longer tests what its name says.

16. **spec/controllers/admin/embeddable_hosts_controller_spec.rb and spec/controllers/admin/embedding_controller_spec.rb — Minor.** They only check the subclass. Nothing covers create, update or destroy, the scheme/path normalisation going through the controller, or show. Findings 1 and 2 are not covered by any test either.

## Files not reviewed

None — I reviewed all 33 files in the patch. Some got only a light read:
- config/locales/client.en.yml and config/locales/server.en.yml: string additions and removals. The removed `embeddable_hosts` and `embed_category` keys are still in about 20 other `server.*.yml` locales, which is harmless dead text.
- The rest are mechanical: app/assets/javascripts/admin/routes/admin-route-map.js.es6, app/assets/javascripts/admin/templates/customize.hbs, app/assets/javascripts/admin/adapters/embedding.js.es6, app/assets/javascripts/admin/routes/admin-embedding.js.es6, app/serializers/embeddable_host_serializer.rb, app/serializers/embedding_serializer.rb, the config/routes.rb route additions, and the spec/models/topic_spec.rb unused-variable cleanups.

I did not run the migration or any test suite, so finding 1 relies on pg 0.18's `IndexError` behaviour rather than a reproduction. Verifying it is the first thing to do before merging. A background `find` that looked for the pg gem source on disk timed out without a result.
