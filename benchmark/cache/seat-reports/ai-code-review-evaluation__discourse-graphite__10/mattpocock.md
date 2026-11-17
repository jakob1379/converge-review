Code review of d1c69189f3 against base 913c3d6f63 ("FEATURE: Can edit category/host relationships for embedding")

I reviewed both axes directly, as the override asked. There is no spec, so the Spec axis is checked against the commit message only. The documented standards come from CONTRIBUTING.md: two spaces, no trailing blank lines, Ruby 1.9 hash syntax, `class << self` preferred, "include tests", "adhere to common conventions", one feature per branch. I ran no tests (I was told not to), so every claim below is reasoned from the code.

## Standards

1. **db/migrate/20150818190757_create_embeddable_hosts.rb:9-11 — Critical.**
   - **Claim:** the migration crashes on any database that has no `embed_category` row in `site_settings`. That covers every fresh install and every site that never changed the setting from its default `''`. Defaults are not stored as rows.
   - **Evidence:** `execute("SELECT c.id FROM categories ... WHERE s.name = 'embed_category'")[0]['id']`. On pg 0.18.1 (Gemfile.lock:220), `PG::Result#[]` on an empty result raises `IndexError: Index 0 is out of range`. The `category_id == 0` fallback is never reached. The existing migration 20140711193923 uses `.first` with a nil check for this exact pattern, so this also breaks the "adhere to common conventions" rule.
   - **Failing command:** on an empty database, `RAILS_ENV=test bundle exec rake db:drop db:create db:migrate` should stop at CreateEmbeddableHosts with an IndexError. I did not run it.

2. **db/migrate/20150818190757_create_embeddable_hosts.rb:22-25 — Important.**
   - **Claim:** legacy hosts are copied over without being normalised. After upgrade, sites whose setting held entries like `http://eviltrout.com` or `https://example.com/1234` stop matching, and embedding breaks.
   - **Evidence:** the old `allows_embeddable_host?` deliberately accepted scheme and path forms. The removed specs "works with a http host" and "works with a https host" tested this. The migration inserts `h` raw by raw SQL, which skips the model's `before_validation` stripping. `record_for_host` then compares `lower(host) = uri.host`, so `'http://eviltrout.com'` never equals `'eviltrout.com'`.
   - **Second problem:** `'#{h}'` is put straight into the SQL string. A value containing `'` breaks the migration, and `\r` or whitespace in the value is kept.
   - **Status:** reasoned.

3. **spec/controllers/admin/embeddable_hosts_controller_spec.rb:5 and spec/controllers/admin/embedding_controller_spec.rb:5 — Important.**
   - **Claim:** this breaks CONTRIBUTING's "Include tests". The new create, update and destroy endpoints have no behavioural tests. The only specs check that each controller subclasses AdminController.
   - **What that misses:** a nil record on `update`/`destroy` (controller lines 10 and 15, `where(id:).first` followed by `host.destroy`) gives a 500 instead of a 404. A missing `host` param also gives a 500, because embeddable_host.rb:6 calls `self.host.sub!` on nil.
   - **Status:** reasoned.

4. **app/models/embeddable_host.rb:2 — Minor (hard breach).** `:with =>` uses the hash-rocket syntax that CONTRIBUTING rules out ("use Ruby 1.9 hash syntax").

5. **app/models/embeddable_host.rb:10,20 — Minor (hard breach).** It uses `def self.record_for_host` and `def self.host_allowed?`, but CONTRIBUTING says "prefer `class << self; def method; end` over `def self.method`".

6. **app/serializers/embeddable_host_serializer.rb:16 and app/assets/javascripts/admin/templates/embedding.hbs:15 — Minor.** Both files end with an extra blank line, against "no trailing whitespaces, blank lines".

7. **spec/fabricators/category_fabricator.rb:1-4 and spec/fabricators/embeddable_host_fabricator.rb:1-27 — Minor.**
   - **Claim:** the contents of the two files are swapped. The category fabricators now live in `embeddable_host_fabricator.rb`, and `:embeddable_host` lives in `category_fabricator.rb`.
   - **Evidence:** it works only because Fabrication loads every file. It breaks the one-fabricator-per-file naming convention used elsewhere in spec/fabricators.

8. **test/javascripts/models/store-test.js.es6:111 — Minor.**
   - **Claim:** `store.find('fruit', 2)` is misleading.
   - **Evidence:** the pretender route `/fruits/:id` always returns `fruits[0]` (apple, `color_ids: [1,2]`). The assertions pass for apple, not banana, which has `color_ids: [3]`.

9. **spec/models/topic_spec.rb:1403 — Minor.**
   - **Claim:** the test "is false if embeddable_host is blank" no longer tests anything about hosts.
   - **Evidence:** `expandable_first_post?` no longer reads hosts. The test passes only because `embed_truncate` defaults to false.

10. **app/assets/javascripts/discourse/models/store.js.es6:192-201 — Minor.**
    - **Claim:** the new `_ids` branch applies to every model built from a REST-serializer payload.
    - **Evidence:** it deletes `*_ids` keys even when the sub-collection isn't side-loaded, which leaves arrays of `undefined`. Unlike the single-id branch, there is no "only if hydrated" guard. `hydrated || []` is dead code because `.map` never returns a falsy value. If `obj[k]` is null, it throws a TypeError.

11. **app/assets/javascripts/discourse/adapters/rest.js.es6:21 — Minor.** `type.replace('_', '-')` replaces only the first underscore. A future admin model like `foo_bar_baz` would get the wrong base path.

12. **app/controllers/admin/embedding_controller.rb:9-11, app/assets/javascripts/admin/controllers/admin-embedding.js.es6:5-7, config/locales/client.en.yml (`admin.embedding.edit`) — Minor (judgement call, possible Speculative Generality).**
    - **Evidence:** `update` does nothing but re-render. The `saveChanges` action and the `edit` locale key are never referenced from any template.

13. **app/controllers/admin/embeddable_hosts_controller.rb:3 and embedding_controller.rb:3 — Minor (possible Duplicated Code).** `before_filter :ensure_logged_in, :ensure_staff` repeats filters that `Admin::AdminController` already declares (admin_controller.rb:3-4).

## Spec (no spec, so checked against the commit message)

14. **Scope — Minor.**
    - **What is done:** "edit category/host relationships" is implemented through the admin UI, the `EmbeddableHost` model and `TopicEmbed` using the per-host category.
    - **What the commit message doesn't mention:**
      - The `embeddable_hosts` and `embed_category` site settings are removed. That breaks anything (API scripts, provisioning) that sets them.
      - `Topic#expandable_first_post?` changes meaning (app/models/topic.rb:869). It no longer requires any hosts to be configured.
      - Unrelated cleanup in spec/models/topic_spec.rb:1241,1250 removes unused `topic =` assignments, against CONTRIBUTING's "one feature or bug-fix per branch". This is trivial.

15. **app/models/embeddable_host.rb:2 vs :10-17 — Minor.**
    - **Claim:** validation and lookup disagree on ports.
    - **Evidence:** the format regex accepts `example.com:8080`, and `before_validation` only strips the path. `record_for_host` matches on `uri.host`, which has no port, so a host saved with a port can never match.
    - **Related:** the TLD rule `[a-z]{2,5}` rejects `localhost`, IP addresses and longer TLDs that the old `host_list` setting allowed. Migrated rows skip validation, so editing them later in the admin UI fails.

16. **app/assets/javascripts/admin/components/embeddable-host.js.es6:39 — Minor.**
    - **Claim:** a new host saved without picking a category shows a blank category badge until the page is reloaded.
    - **Evidence:** the client sets `category = Category.findById(null)`, while the server substitutes `uncategorized_category_id` (embeddable_hosts_controller.rb:26).

17. **db/migrate/20150818190757_create_embeddable_hosts.rb:6 and app/models/topic_embed.rb:43 — Minor.**
    - **Claim:** `category_id` is NOT NULL but has no foreign key and no `dependent` handling, so deleting a category leaves orphaned host rows.
    - **Evidence:** `TopicEmbed.import` then passes a missing id, and TopicCreator quietly falls back to no category. The admin badge renders empty.

**Summary:** Standards has 13 findings; the worst is #1, a Critical migration crash on any database without an `embed_category` row, which includes fresh installs. Spec has 4 findings, all Minor; the worst is #14, the removed site settings and the changed `expandable_first_post?` behaviour.

## Unreviewed files

None. I reviewed all 36 files in the patch. The non-English locale files (config/locales/server.*.yml) still contain the removed `embeddable_hosts` and `embed_category` keys. They are outside the patch and appear to be managed through Transifex, so I did not flag them.

I did not run the migration or any tests (as instructed), so #1 depends on how pg 0.18 handles `PG::Result#[]` on an empty result, which I'm confident of but did not check by running it.
