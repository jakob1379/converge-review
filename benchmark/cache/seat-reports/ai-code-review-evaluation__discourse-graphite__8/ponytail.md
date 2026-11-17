What this change does: it moves group membership editing off the "save the whole username list" path. The new path has its own add-members (PUT) and remove-member (DELETE) endpoints, and the public members endpoint is paginated and returns `{members, meta}`. The admin UI now shows one page of 50 members, with prev/next, a remove link on each member, and an add box.

Lens: over-engineering only (unneeded code, duplication, things to delete or simplify). Load assumed: a normal Discourse forum where a few admins edit groups, so scale is not a concern here.

**Should fix**

1. **Dead `usernames=` setter and `destroy_deletions` hack left behind** (`app/models/group.rb:244-266`, `:287-296`, `after_save :destroy_deletions` at `:10`). Severity: Important (lean).
   - What this is: the old bulk-replace setter computes adds and deletes, then deletes join rows in an `after_save` hook marked "hack around AR".
   - Problem: the patch removed the only production callers: `Admin::GroupsController#create/#update_put` and the JS `saveWithUsernames`/`createWithUsernames`. Now `grep -rn "\.usernames *=" --include=*.rb .` finds hits only in `spec/models/group_spec.rb:149,153` and `spec/models/user_spec.rb:1011,1022`. The getter `usernames` is still used by `users_controller.rb:430`, so keep that.
   - Fix: delete the setter, `destroy_deletions`, the `after_save` line, and the spec cases that test only the setter. About 35 lines.
   - Caveat: `destroy_deletions` also cleared `primary_group_id` when a member was removed. The new `remove_member` does not do that (see 3). If you delete the hook, move that one line into `Group#remove`. Do not keep the hack for it.

2. **`group.save` plus error branch after membership writes is a no-op** (`app/controllers/admin/groups_controller.rb:77-81`, `:92-96`). Severity: Minor.
   - Problem: `group.add(user)` is `users.push(user)` on a saved group, and `group.users.delete(user_id)` writes at once. Both hit the database right away. The `group.save` that follows saves an unchanged record, so the `render_json_error` branch can only fire if the group's own data (such as its name) fails validation, which has nothing to do with the members.
   - Fix: replace both blocks with `render json: success_json`. That is 8 lines less.

3. **`remove_member` skips the existing helper** (`app/controllers/admin/groups_controller.rb:90`). Severity: Minor.
   - Problem: `Group#remove(user)` (`app/models/group.rb:276`) already exists, and `add_members` uses its twin `group.add`. `remove_member` uses `group.users.delete(user_id)` instead, so the two endpoints work differently. Fixing primary-group cleanup now means touching two places.
   - Fix: `group.remove(User.find(user_id))`, or make `remove` take an id. Put the `primary_group_id` reset (from 1) inside `remove`.

**Nice to have**

4. **Offset clamped three times** (`app/assets/javascripts/admin/controllers/admin-group.js.es6:30,33,41,44` and `app/assets/javascripts/discourse/models/group.js:23`). Severity: Minor.
   - Problem: `next`/`previous` return early on `showingLast`/`showingFirst`, then clamp with `Math.min`/`Math.max`. `findMembers` then clamps the same value again with `Math.min(user_count, Math.max(offset, 0))`. The server echoes the offset it used.
   - Fix: keep the guard in the actions and pass the plain offset. Drop either the action clamps or the model clamp, and the second set is just dead weight. About 2 lines less, and the code is easier to read.

5. **`totalPages` needs a special case only because it uses the wrong formula** (`app/assets/javascripts/admin/controllers/admin-group.js.es6:11-14`). Severity: Minor (simpler and more correct).
   - Problem: `Math.floor(count/limit) + 1` needs the `== 0` guard. It is also off by one when count is an exact multiple of limit: 50 members gives "1/2" and an empty page 2.
   - Fix: `return Math.ceil(this.get("user_count") / this.get("limit"));` gives 0 for 0 members, so the guard line goes away. Reasoned from the arithmetic, not run.

6. **Unrelated formatting churn in a FIX commit** (`app/assets/javascripts/discourse/templates/user-selector-autocomplete.raw.hbs`, `app/assets/javascripts/discourse/templates/components/admin-group-selector.hbs`, the re-indented `protected`/`private` methods at `app/controllers/admin/groups_controller.rb:99-102` and `app/controllers/groups_controller.rb:38-44`, the `ilike`→`ILIKE` change at `admin/groups_controller.rb:8`, and the brace spacing in `aliasLevelOptions`). Severity: Minor.
   - Problem: these files and hunks change whitespace or case only and do nothing for group membership. They make the diff noisier and invite blame and merge conflicts.
   - Fix: drop them from this commit.

**Outside my lens, one line each (reasoned, not run):**
- `group_member.hbs:1` uses `{{#unless automatic}}` inside an `itemView`. In Ember 1.x that probably resolves against the member, not the group, so the remove link would show on automatic groups too (the server returns 422).
- `addMembers` leaves a `// TODO: should clear the input` (`admin-group.js.es6:62`). That breaks the user's "no comments" rule and marks unfinished work.

**Good deletions in this patch:** the dead `get "users"` admin route (no action existed), the `update_patch`/`update_put` split on HTTP method, and the old "more than 200" TODO workaround in `GroupsController#members`. The `.form-horizontal` CSS move to `.groups, .badges` is a real dedupe; `badges-show.hbs` uses that class too. The separate `group-member` view file follows the house pattern (`share.hbs`, `topic-list.hbs` use `{{each x in y itemView=...}}`), so I did not flag it.

Verdict: none of these block shipping on lean grounds. Do 1 and 2 before merge, the rest whenever.
Lean: about -45 lines possible.

Files not reviewed in depth: `config/locales/client.en.yml` (only new i18n strings, no logic) and `spec/controllers/admin/groups_controller_spec.rb` (I only skimmed it for setter usage; test quality is outside the over-engineering lens). I reviewed every other file in the patch.
Not checked: nothing was run; no specs and no Ember render. The `group.save` no-op claim (2) depends on Rails `has_many :through` push/delete writing at once on a saved owner, which is standard Rails 4 behavior but I did not run it.
