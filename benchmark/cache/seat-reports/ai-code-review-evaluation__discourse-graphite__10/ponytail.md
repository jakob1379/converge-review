## Over-engineering review: discourse-graphite__10 (base 913c3d6f63, head d1c69189f3)

**What this change does:** It moves the embed allow-list out of two site settings (`embeddable_hosts`, `embed_category`) into a new `embeddable_hosts` table, with one category per host. It adds an admin page at Customize > Embedding where staff can add, edit and delete hosts. It also adds a migration that copies the old settings into the table, and it teaches the JS store to load `*_ids` arrays.

Load assumed: admin-only CRUD with a handful of rows. Embed requests check the referer with one indexed-size query per request. Nothing in this patch is a scale concern.

### Findings

1. `app/controllers/admin/embedding_controller.rb:1-21`, `app/serializers/embedding_serializer.rb:1-8`, `app/assets/javascripts/admin/adapters/embedding.js.es6:1-7`, `app/assets/javascripts/discourse/models/store.js.es6:192-209`. **Important (yagni).**
   - **Claim:** The "Embedding" object exists only to wrap a list of hosts. It is an `OpenStruct` with a fixed `id: 'default'`, its own controller, its own serializer and a custom adapter. The new plural `_ids` hydration in the store, plus its fixture and test changes, exists only to unpack that wrapper.
   - **Simpler approach:** The repo already has the pattern. `app/assets/javascripts/admin/routes/admin-plugins.js.es6:3` does `this.store.findAll('plugin')` for an admin model. Add `index` to `Admin::EmbeddableHostsController` (the route `resources :embeddable_hosts` at `config/routes.rb:153` already exists) and have the route call `this.store.findAll('embeddable-host')`.
   - **What it removes:** About 60 lines: EmbeddingController, EmbeddingSerializer, the embedding adapter, the two `customize/embedding` routes, the `_ids` branch in `_hydrateEmbedded`, and the pretender/store-test changes.
   - **Caveat:** If the author plans to put embed settings on this object later, the wrapper is speculative today. Nothing in this patch uses it.
   - **Evidence:** Reasoned, no failing test (this is design, not behaviour).

2. `app/controllers/admin/embedding_controller.rb:9-11`, `config/routes.rb:139`, `app/assets/javascripts/admin/controllers/admin-embedding.js.es6:5-7`. **Important (dead code).**
   - **Claim:** `update` saves nothing. It renders exactly what `show` renders. Its only client caller, the `saveChanges` action, is never triggered: `embedding.hbs` has no element that sends `saveChanges`.
   - **Evidence:** `grep -rn saveChanges app/assets/javascripts/admin` matches the new controller but no template under `admin/templates/embedding*`.
   - **Fix:** Delete the `update` action, the `put "customize/embedding"` route and `saveChanges` (-7 lines). This is a no-op endpoint that looks like it persists data.

3. `app/serializers/embeddable_host_serializer.rb:4-15`. **Minor (delete).**
   - **Claim:** The `id`, `host` and `category_id` methods just return `object.<attr>`. `attributes :id, :host, :category_id` already does that for an ActiveRecord object.
   - **Evidence:** `app/serializers/permalink_serializer.rb:2` declares `:id`, `:url`, `:category_id` with no pass-through methods.
   - **Fix:** Keep line 2 and delete the rest (-12 lines).

4. `app/controllers/admin/embeddable_hosts_controller.rb:3` and `app/controllers/admin/embedding_controller.rb:3`. **Minor (duplicate).**
   - **Claim:** `before_filter :ensure_logged_in, :ensure_staff` repeats filters that `Admin::AdminController` (the parent class) already declares.
   - **Evidence:** `app/controllers/admin/admin_controller.rb:3-4`.
   - **Fix:** Drop them from the first controller. Keep only `before_filter :fetch_embedding` in the second.

5. `app/assets/javascripts/discourse/models/store.js.es6:200`. **Minor.**
   - **Claim:** In `obj[self.pluralize(subType)] = hydrated || []`, the `|| []` can never apply. `Array#map` always returns an array.
   - **Fix:** Delete the `|| []`. Note that `map` keeps `undefined` entries for ids it cannot find, unlike the singular branch, which skips misses. That difference is not over-engineering, but the `|| []` suggests the author thought it handled misses.

6. `app/models/embeddable_host.rb:2`. **Minor (dead branch).**
   - **Claim:** The `(\/.*)?` path group in the validation regex can never match. The `before_validation` block at lines 5-8 strips everything from the first `/` before validation runs.
   - **Fix:** Drop the group.

7. `db/migrate/20150818190757_create_embeddable_hosts.rb:21-27`. **Minor.**
   - **Claim:** `if records.present?` after `val.split("\n")` is redundant. `val.present?` already guarantees at least one element.
   - **Fix:** Drop the inner `if` (-2 lines).

8. `config/locales/client.en.yml:2498`. **Minor (unused).**
   - **Claim:** `admin.embedding.edit` is never referenced. The component uses a pencil icon with no label.
   - **Evidence:** `grep -rn "embedding.edit" app/assets` finds nothing.
   - **Fix:** Delete the key.

9. `spec/fabricators/category_fabricator.rb:1-4` and `spec/fabricators/embeddable_host_fabricator.rb:1-27`. **Minor (churn and misnamed files).**
   - **Claim:** The file contents are swapped. `category_fabricator.rb` now holds the `:embeddable_host` fabricator, and `embeddable_host_fabricator.rb` holds all the category fabricators.
   - **Evidence:** The patch's index lines show the new `embeddable_host_fabricator.rb` blob (`a37f5b4c8b`) is identical to the old `category_fabricator.rb`.
   - **Effect:** A 4-line addition became a 54-line move, and the next person to grep for `Fabricator(:category)` lands in the wrong file.
   - **Fix:** Restore `category_fabricator.rb` and put only the 4-line `:embeddable_host` fabricator in the new file.

### Outside this seat (reported because they are severe; reasoned, not run)

- **Critical:** `db/migrate/20150818190757_create_embeddable_hosts.rb:9-11`. `execute(...)[0]['id']` assumes a `site_settings` row named `embed_category` matches a category. On a fresh install, or any site that never set `embed_category`, the result is empty, and `[0]` raises or returns nil, so the migration aborts. The `category_id == 0` fallback at line 14 is never reached.
- **Important:** Same migration, line 25. Hosts are interpolated straight into SQL (`'#{h}'`), so a stored host containing a `'` breaks the migration.
- **Minor:** `app/models/embeddable_host.rb:6-7`. `self.host.sub!` raises `NoMethodError` when `host` is nil, so creating a host with an empty host field returns a 500 instead of a validation error.

Verdict: from the over-engineering seat, fix 2 first, and treat 1 as a design call worth raising. The Critical migration bug above belongs to the correctness seat but blocks shipping.
Lean: about -95 lines possible (about 60 from finding 1, 7 from 2, 12 from 3, plus small deletions from 4-8, and the 27-line fabricator churn in 9).
Not checked: whether AMS 0.8.3 needs the `EmbeddingSerializer#id` override for an `OpenStruct` (the gem source lookup did not finish). It only matters if finding 1 is not taken.

### Unreviewed files

None. I read every file in the patch. These got only a quick pass, because they are tests, fixtures or locale data with no over-engineering surface beyond what is listed above:
- `spec/controllers/admin/embeddable_hosts_controller_spec.rb`
- `spec/controllers/admin/embedding_controller_spec.rb`
- `spec/controllers/embed_controller_spec.rb`
- `spec/models/embeddable_host_spec.rb`
- `spec/models/site_setting_spec.rb`
- `spec/models/topic_embed_spec.rb`
- `spec/models/topic_spec.rb` (it also carries unrelated unused-variable cleanups at lines 1241 and 1250)
- `test/javascripts/helpers/create-pretender.js.es6`
- `test/javascripts/models/store-test.js.es6`
- `config/locales/server.en.yml`
- `config/site_settings.yml`

No code was run. Every claim is from reading the code.
