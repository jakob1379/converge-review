Seat: open-code-review:delegate-review, run in range mode from 913c3d6f to d1c69189. OCR's preview listed 20 of the 36 patch files as reviewable and excluded the .es6 and spec files. The override says to review the whole patch, so I read all 987 lines and checked the surrounding source. I did not run tests or migrations. No files were written.

## Findings

1. **db/migrate/20150818190757_create_embeddable_hosts.rb:9-11 — Critical.**
   - **Claim:** The migration crashes on every site that never set `embed_category`. That includes fresh installs and the test database.
   - **Evidence:**
     - `execute("SELECT c.id FROM categories ... WHERE s.name = 'embed_category'")[0]['id']` reads row 0 without checking how many rows came back.
     - `embed_category` defaulted to `''`. A site_settings row exists only after an admin changed the setting, so the join usually returns 0 rows.
     - With pg 0.18.1 (Gemfile.lock:220), `PG::Result#[]` raises `IndexError: Index 0 is out of range` when the index is past the last row (`pgresult_aref`).
     - The `if category_id == 0` fallback on line 15 never runs. The `cmd_tuples > 0` guard used later on line 19 is missing here.
   - **Reproduce:** `RAILS_ENV=test bundle exec rake db:drop db:create db:migrate` on a database with no `embed_category` row should fail with IndexError. This is reasoned: I did not run it, per instructions.

2. **db/migrate/20150818190757_create_embeddable_hosts.rb:23-25 — Important.**
   - **Claim:** Migrated hosts that had a scheme or path no longer match, so embedding silently breaks after the upgrade.
   - **Evidence:**
     - The old `SiteSetting.allows_embeddable_host?` stripped `http(s)://` and accepted entries like `http://eviltrout.com` and `https://example.com/1234`. The removed specs in spec/models/site_setting_spec.rb ("works with a http host") and the old spec/controllers/embed_controller_spec.rb multi-host setup both used such entries.
     - The migration inserts each line with raw SQL, which skips the model's `before_validation` normalisation. A row is stored literally as `http://eviltrout.com`.
     - `EmbeddableHost.record_for_host` compares `lower(host) = 'eviltrout.com'`, so that row never matches. EmbedController and TopicRetriever then reject the site.
     - Trailing whitespace or `\r` in a line has the same effect.
   - **Status:** Reasoned.

3. **db/migrate/20150818190757_create_embeddable_hosts.rb:25 — Minor.**
   - **Claim:** Values are put into the SQL by string interpolation (`VALUES ('#{h}', ...)`) with no quoting. A host string containing `'` breaks the migration.
   - **Evidence:** The values come from an admin-only setting, so the injection risk is low. It is still unescaped database data inside SQL. `quote(h)` would fix it.

4. **db/migrate/20150818190757_create_embeddable_hosts.rb:2 — Minor.**
   - **Claim:** Rolling this migration back fails. It uses `def change` with raw `execute` data moves and a `DELETE` of site settings.
   - **Evidence:** A rollback raises `ActiveRecord::IrreversibleMigration`, and the deleted settings cannot be restored. It needs explicit `up`/`down` methods.

5. **app/models/embeddable_host.rb:5-8 — Minor.**
   - **Claim:** A request with no host value returns a 500 error instead of a validation error.
   - **Evidence:**
     - `self.host.sub!` runs on nil when no host is given. Admin::EmbeddableHostsController#save_host (line 23) passes `params[:embeddable_host][:host]` straight through.
     - So `POST /admin/embeddable_hosts` with only `category_id` raises NoMethodError.
     - If `params[:embeddable_host]` itself is missing, line 23 raises as well.

6. **app/models/embeddable_host.rb:2 together with :14 — Minor.**
   - **Claim:** A host saved with a port passes validation but can never match a request.
   - **Evidence:** The validation regex accepts `:port`, and `before_validation` does not strip it. `record_for_host` compares against `URI(...).host`, which has no port.
   - **Also:** The regex's `(\/.*)?` part can never apply, because paths are already stripped. `[a-z]{2,5}` rejects `localhost`, IP addresses and TLDs longer than 5 characters, all of which the old setting allowed. Such migrated rows then fail validation the next time they are edited.

7. **app/models/embeddable_host.rb:14 — Minor.**
   - **Claim:** The case-insensitive match only works when the incoming host is already lowercase.
   - **Evidence:** `where("lower(host) = ?", host)` lowercases the column but not `uri.host`, and `URI("http://EvilTrout.com").host` is `"EvilTrout.com"`. It needs `host.downcase`.
   - **Also:** There is no uniqueness check or index on `host`. If a host is entered twice, `.first` picks one category arbitrarily.

8. **app/models/topic_embed.rb:36,43 — Minor.**
   - **Claim:** Topics created by feed polling can now land in Uncategorized.
   - **Evidence:**
     - The category now comes from the host of each feed item's URL (`EmbeddableHost.record_for_host(url)`) instead of the global `embed_category` setting.
     - Topics imported via app/jobs/scheduled/poll_feed.rb:39 or lib/tasks/typepad.thor:63, whose host is not registered, get `category: nil`.
     - Previously every embedded topic went to `embed_category`. The patch removes that setting with no replacement for this path.
   - **Status:** Reasoned.

9. **app/controllers/admin/embeddable_hosts_controller.rb:10,15-16 — Minor.**
   - **Claim:** An unknown id on update or delete returns a 500 instead of a 404.
   - **Evidence:** `EmbeddableHost.where(id: params[:id]).first` returns nil, then `host.destroy` or `host.host=` raises NoMethodError. `find` would raise RecordNotFound and give a 404.
   - **Also:** `category_id` is not checked to be an existing category.

10. **app/assets/javascripts/discourse/models/store.js.es6:220-232 — Minor.**
    - **Claim:** The `_ids` handling is unsafe for some payloads.
    - **Evidence:**
      - The new `_ids` branch calls `obj[k].map` without checking the value. A `*_ids: null` in any `__rest_serializer` payload throws a TypeError.
      - It deletes the `_ids` key even when nothing is found, leaving an array of `undefined`.
      - `hydrated || []` never has an effect, because `map` always returns an array.

11. **test/javascripts/models/store-test.js.es6:111-115 — Minor (test validity).**
    - **Claim:** The test passes for the wrong reason.
    - **Evidence:** It calls `store.find('fruit', 2)` and asserts colours `[1,2]`, which are apple's (fruit 1). It passes only because the pretender handler for `/fruits/:id` (create-pretender.js.es6:226-228) ignores the id and always returns `fruits[0]`. Banana has `color_ids: [3]`.

12. **spec/fabricators/category_fabricator.rb and spec/fabricators/embeddable_host_fabricator.rb — Minor.**
    - **Claim:** The two files' contents are swapped.
    - **Evidence:** category_fabricator.rb now defines only `:embeddable_host`, and embeddable_host_fabricator.rb defines `:category`, `:diff_category`, `:happy_category` and `:private_category`. It works only because all fabricators are loaded. Anyone looking for the category fabricators will look in the wrong file.

13. **spec/models/topic_spec.rb:868-871 — Minor.**
    - **Claim:** The test "is false if embeddable_host is blank" no longer tests what its name says.
    - **Evidence:** `Topic#expandable_first_post?` (app/models/topic.rb:869) dropped the host-presence check. The test now passes only because a built topic has no topic_embed.

## Files not reviewed
None. I reviewed all 36 files in the patch, including the 16 that OCR excluded (`.es6` files as an unsupported extension, `spec/` files as a default-excluded path).

Not checked: I did not run the migration or the test suites. Findings 1, 2 and 8 are reasoned from code; finding 1 also relies on the pg gem's documented `IndexError` behaviour. I did not search plugins for remaining uses of `SiteSetting.embeddable_hosts` or `embed_category`; core has none.
