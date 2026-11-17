Review of 4975fc28..060cda77, "FIX: proper handling of group memberships". There was no spec, so I judged the change against its commit message and against how it behaved before. I did not dispatch a subagent. I ran no tests, as instructed, so every "fails on" command below is reasoned and has not been run. Rails is 4.1.8 (Gemfile.lock), and automatic groups 0–14 are seeded in the test DB through SeedFu in spec/spec_helper.rb.

**Findings**

1. **app/controllers/admin/groups_controller.rb:90 — Important.** `remove_member` calls `group.users.delete(user_id)`, which skips the bookkeeping that every other removal path does.
   - **What goes wrong:** The cached `groups.user_count` is not decremented, and the removed user's `primary_group_id` is not cleared.
   - **Why:**
     - `users` is a has_many :through. In Rails 4.1, `delete` on it removes the `group_users` rows with `delete_all`, so no callbacks run. That means the `counter_cache: "user_count"` on `GroupUser` (app/models/group_user.rb) never fires.
     - The through-counter fallback looks for a `group_users_count` column, which does not exist.
     - Before this change, the admin UI went through `Group#usernames=`, and `destroy_deletions` (app/models/group.rb:285-293) destroyed each GroupUser (so the counter was decremented) and nulled `primary_group_id`. `Group#remove` also uses `destroy`.
   - **Effect:** The group list (BasicGroupSerializer `user_count`) shows a stale count. Removed users keep the group as their primary group, so it still shows as their post flair.
   - **Fails on head (reasoned):** add to the existing "is able to remove a member" spec: `group.reload.user_count.should == 0` and `user.reload.primary_group_id.should be_nil` after setting `user.update_columns(primary_group_id: group.id)` beforehand. The spec as written only checks `group.users.count`, which hides this.

2. **app/controllers/admin/groups_controller.rb:72-75 — Important.** `add_members` calls `group.add(user)` (`users.push`, which inserts at once on a persisted group) with no membership check.
   - **What goes wrong:** Adding a user who is already a member breaks the unique index `index_group_users_on_group_id_and_user_id`. That raises `ActiveRecord::RecordNotUnique`, the request returns 500, and any users earlier in the list stay added.
   - **Why it matters now:** The new UI makes this easy to hit. The input is never cleared after Add (the author's own `// TODO: should clear the input` at admin-group.js.es6:62), so clicking Add twice, or typing an existing member, gives a 500.
   - **Fails on head (reasoned):** `group = Fabricate(:group); u = Fabricate(:user); group.add(u); xhr :put, :add_members, group_id: group.id, usernames: u.username; response.should be_success` raises RecordNotUnique.

3. **app/assets/javascripts/discourse/routes/group-members.js.es6:11 and discourse/templates/group/members.hbs:6 — Important.** The public `/groups/:name/members` page now shows only the first 50 members and has no way to page further.
   - **Why:** The server default became `limit = 50` (groups_controller.rb:22), but only the admin template got next/previous controls.
   - **Before:** Non-automatic groups returned all members, and automatic groups returned 200.
   - **Effect:** This is a user-visible regression for any group with more than 50 members, which undercuts the commit's own "proper handling of group memberships" claim.
   - **Evidence:** reasoned, from the template and route (no pagination actions or controller exist under discourse/controllers/group/).

4. **app/controllers/admin/groups_controller.rb:22-41 and 65-99, app/controllers/groups_controller.rb:28-35, config/routes.rb:49-50 — Important.** The public API changes in four breaking ways with no deprecation path.
   - `POST/PUT /admin/groups` no longer reads `group[...]` params. A legacy create gets a blank name and fails validation. A legacy update silently sets `visible=false`, because `params[:visible]` is nil.
   - `group[usernames]` is ignored entirely.
   - `PATCH /admin/groups/:id` with `changes[add|delete]` is gone, because `update` no longer branches on `request.patch?`.
   - `GET /groups/:name/members` now returns `{members:, meta:}` instead of an array.
   - **Effect:** Outside scripts and SSO sync tools that manage group membership through these endpoints break. The old PATCH path was the documented incremental API, and the old specs covered it.
   - **Evidence:** reasoned. Fails on head: the old spec `xhr :patch, :update, id: group.id, changes: {add: user2.username}` now hits `update` and does not add the user.

5. **app/assets/javascripts/admin/controllers/admin-group.js.es6:13 — Minor.** `totalPages` uses `floor(user_count/limit)+1`, which is off by one whenever `user_count` is an exact multiple of `limit`.
   - For example, 50 members gives "1/2". Clicking next requests offset 50 and shows an empty page.
   - It should be `Math.ceil(user_count/limit)`.
   - Evidence: arithmetic.

6. **app/controllers/groups_controller.rb:22-23 — Minor.** `limit` and `offset` are not validated.
   - A negative value produces `LIMIT -1` or `OFFSET -1`, which PostgreSQL rejects, so the request returns 500.
   - There is no upper cap on `limit`, which a public endpoint should have.
   - Evidence: reasoned. Fails on head: `xhr :get, :members, group_id: group.name, limit: -1`.

7. **app/assets/javascripts/discourse/models/group.js:25 — Minor.** `findMembers` builds the URL from the current `name`.
   - In the admin form the name field is bound to the same model. If an admin edits the name and then clicks next, previous, add or remove before saving, `/groups/<unsaved-name>/members.json` is requested and returns 404.
   - Evidence: reasoned.

8. **spec/controllers/admin/groups_controller_spec.rb:115 — Minor.** The "cannot remove members from automatic groups" spec uses `xhr :put, :remove_member`, but the route is DELETE.
   - It passes only because controller specs skip routing.
   - Evidence: config/routes.rb:49.

9. **spec/controllers/groups_controller_spec.rb:72-85 (not in the patch) — Minor.** The `pending "ensures that membership can be paginated"` spec was left in place.
   - The patch implements pagination but neither enables nor updates this spec, and the spec still parses the old array shape.
   - So the new `members`/`meta` response contract has no test at all.

**Files in the patch I did not review in depth**
- `discourse/templates/user-selector-autocomplete.raw.hbs` and `discourse/templates/components/admin-group-selector.hbs`: whitespace and indentation only.
- `common/admin/admin_base.scss`: style moves only. I checked that the `.form-horizontal` rules moved to `.groups, .badges` keep the badges styling, but did no visual check.
- Every other file in the patch was reviewed.

I did not run any specs and did not check the new Ember templates in a browser. The has_many :through `delete` counter behaviour in finding 1 comes from my knowledge of Rails 4.1.8. I did not confirm it against the gem source on this machine.
