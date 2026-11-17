I reviewed the change with the `open-code-review:delegate-review` skill in range mode, from 4975fc28 to 060cda77. I did not edit anything. I skipped the skill's auto-fix step because the brief says report only. I ran no tests, so every finding below is reasoned from the source rather than from a failing run. Where it helps, I sketch a test that should fail on the patched code.

## Findings

**1. app/controllers/admin/groups_controller.rb:71-74 — Important. Adding a user who is already a member causes a 500, and some users may already have been added when it does.**
- `group.add(user)` is `self.users.push(user)` (app/models/group.rb:272). On a group that is already saved, push inserts the `group_users` row immediately.
- `group_users` has a unique index on `(group_id, user_id)` (db/migrate/20130416004933_group_users.rb:9). Pushing a user who is already in the group therefore raises `ActiveRecord::RecordNotUnique`.
- The loop is not in a transaction. Users earlier in the list are already committed when the error is raised.
- The old path used `group.usernames=`, which compared the request against current members and only added new ones. The UI makes this easy to hit: the input is never cleared after an add (see the TODO at admin-group.js.es6:62).
- Test that should fail: `group = Fabricate(:group); u = Fabricate(:user); group.add(u); xhr :put, :add_members, group_id: group.id, usernames: u.username; response.should be_success`. It should raise `RecordNotUnique` or return a 500.

**2. app/controllers/admin/groups_controller.rb:90 — Important. Removing a member skips the cleanup the old code did.**
- `group.users.delete(user_id)` on a has_many `:through` association uses `delete_all` on the join rows, so no callbacks run on `GroupUser`.
- **Primary group not cleared (certain).** The old path went through `destroy_deletions` (group.rb), which set `primary_group_id = NULL` on the removed user. The new path never does. A removed user keeps the group as their primary group, and post_serializer.rb:96-102 still shows that group's name on their posts.
- **Member count may not drop (less certain).** `GroupUser belongs_to :group, counter_cache: "user_count"` should decrement `groups.user_count` when the row is destroyed. I believe Rails 4.1.8 skips this for a `delete_all` on a through association: the counter name it looks for is `group_users_count`, not `user_count`. This comes from my memory of the 4.1 code; I did not read the gem source here.
- Nothing in app/jobs or lib recalculates `user_count`, so the count shown in the admin group list would drift.
- Test that should fail: give a member `primary_group_id = group.id`, call `remove_member`, then expect `user.reload.primary_group_id` to be nil. A second test would expect `group.reload.user_count == 0`.
- Fix: `group.remove(user)` destroys the join rows, so callbacks run. The `primary_group_id` reset still has to be added.

**3. app/controllers/admin/groups_controller.rb:22-24, 40 and config/routes.rb:50-51 — Important. Breaking change to the admin API with no compatibility path.**
- `create` and `update` now read top-level `params[:name]`, `params[:visible]` and `params[:alias_level]` instead of `params[:group][...]`.
- `PATCH /admin/groups/:id` with `changes[add]` / `changes[delete]` (`update_patch`) has been removed.
- `group[usernames]` on create and update is silently ignored.
- Any API client using the old shape breaks:
  - Create sends `group[name]`, so `params[:name]` is nil, the name becomes `""` and validation fails with a 422.
  - Update silently does nothing to membership.
  - PATCH now replaces only the settings, with nothing in `params[:visible]`, so `group.visible = (nil == "true")` silently sets the group to not visible.
- I believe the discourse_api gem used the PATCH `changes` shape, but I did not check that.
- The commit message does not mention this API change. The removed `get "users"` route had no matching action, so dropping it is fine.

**4. app/assets/javascripts/admin/controllers/admin-group.js.es6:13 — Important. The page count is one too high whenever the member count is an exact multiple of the page size.**
- The code is `Math.floor(user_count / limit) + 1`. With 50 users and limit 50 it shows "1/2", and Next fetches offset 50, which returns an empty page. 100 users show 3 pages.
- Fix: `Math.ceil(user_count / limit)`.
- Related: removing the last member on the last page leaves an empty page, because `findMembers` keeps the old offset.
- Check: `Math.floor(50/50)+1 === 2` while `Math.ceil(50/50) === 1`.

**5. app/assets/javascripts/discourse/routes/group-members.js.es6:11, app/assets/javascripts/discourse/templates/group/members.hbs:6 and app/controllers/groups_controller.rb:22 — Important. The public group members page now shows only the first 50 members, with no way to see the rest.**
- Before this change, non-automatic groups returned every member.
- `/groups/:name/members` now defaults to 50, and the public route and template have no next/previous controls.
- Members after the 50th cannot be reached from the public page. The pagination was only added to the admin UI.

**6. app/controllers/groups_controller.rb:22-23 — Minor. `limit` and `offset` are not checked.**
- A negative value goes straight to SQL, and PostgreSQL rejects it ("LIMIT must not be negative"), which gives a 500.
- There is no upper cap, so `limit=1000000` returns the whole trust_level_0 group in one request.
- The old code also took `limit` from the user for automatic groups, so this is not a new problem. The change now applies it to every group.

**7. app/controllers/admin/groups_controller.rb:71 — Minor.** `usernames.split(",")` assumes a string. If a client sends `usernames[]=a&usernames[]=b`, `params.require` returns an array and you get a NoMethodError, which is a 500.

**8. app/assets/javascripts/discourse/models/group.js:40-59 and admin-group.js.es6:51-64 — Minor.**
- `removeMember` and `addMembers` have no rejection handler, so a 422 (automatic group) or a 500 (finding 1) gives the admin no feedback.
- The username input is never cleared after an add. The patch itself leaves a TODO for this.
- Fast Next/Previous clicks can let an older `findMembers` response overwrite a newer one.

**9. spec/controllers/admin/groups_controller_spec.rb:115 — Minor.**
- The "cannot remove members from automatic groups" test calls `remove_member` with `:put`, but the route is `DELETE`. It only passes because controller specs skip routing.
- Lines 55, 94 and 115 hardcode group id 1 (the built-in admins group) instead of creating an automatic group with `Fabricate(:group, automatic: true)`.
- There is no spec for:
  - the new `{members, meta}` response from `GroupsController#members`;
  - adding a user who is already a member (finding 1);
  - clearing `primary_group_id` or decrementing `user_count` on removal (finding 2).

I left out OCR's generic JS rules (`var`, `==`, React). This codebase is ES5 / Ember 1.x, and those rules are not its documented standards.

## Coverage
All 16 files in the patch were reviewed against their diff and surrounding source; none were skipped.
- OCR's preview excluded 4 of them (the three `.es6` files as unsupported extension, the spec as default path); I reviewed those manually.
- The remaining 12 were reviewed with OCR rules: routes/admin_group_route.js, templates/group.hbs, group_member.hbs, models/group.js, admin-group-selector.hbs (whitespace only), group/members.hbs, user-selector-autocomplete.raw.hbs (whitespace only), admin_base.scss, admin/groups_controller.rb, groups_controller.rb, client.en.yml, routes.rb.
- Totals: total_files=16, reviewed_files=16, skipped_files=0, coverage_rate=100%.

Not checked: the Rails 4.1.8 counter-cache behaviour in finding 2 is from memory (the gem source is not installed here), and I did not confirm which request shape the discourse_api gem used.
