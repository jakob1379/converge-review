## Review: "FIX: proper handling of group memberships" (4975fc28..060cda77)

I ran `mattpocock-skills:code-review` myself and spawned no sub-agents. There is no spec, so I measured the change against what the commit title promises: membership changes that are correct and paginated. The documented standards are `CONTRIBUTING.md` (coding conventions, "Include tests", the commit-message rule), `.jshintrc` (`eqeqeq: true`, `lastsemic: true`) and `.editorconfig`. `.travis.yml:31-32` runs `jshint .` in CI. I could run nothing (no jshint, no gems, no test run), so every claim below is reasoned. Each failing test or command I name is a suggestion I have not executed.

### Findings

1. **app/controllers/admin/groups_controller.rb:90 — Important.**
   - **Claim:** `remove_member` calls `group.users.delete(user_id)`, which skips the existing `Group#remove` helper (app/models/group.rb:276). That causes two problems:
     - `groups.user_count` goes stale. A `has_many :through` delete removes the `group_users` rows with SQL delete and runs no callbacks, so the `counter_cache: "user_count"` on `GroupUser` (app/models/group_user.rb:2) never decrements. `Group#remove` calls `destroy` on each row, so it does decrement.
     - The user's `primary_group_id` is not cleared. The old full-replace path (`usernames=` → `destroy_deletions`, group.rb:285-293) cleared it.
   - **Standard:** this also goes against CONTRIBUTING "Adhere to common conventions you see in the existing code". `add_members` uses `group.add`, but `remove_member` does not use `group.remove`.
   - **Evidence:** the new spec at spec/controllers/admin/groups_controller_spec.rb:118-130 only checks `group.users.count`, a live COUNT, so it cannot catch this.
   - **Failing test (suggested, not run):** in that spec add `group.reload.user_count.should == 0`. Also set `user.update_column(:primary_group_id, group.id)` before the delete and assert `user.reload.primary_group_id.should be_nil` after it.

2. **app/controllers/groups_controller.rb:22 together with app/assets/javascripts/discourse/templates/group/members.hbs:6 and app/assets/javascripts/discourse/routes/group-members.js.es6 — Important.**
   - **Claim:** the public `/groups/:name/members` endpoint now defaults to `limit = 50` for every group. Before, it returned all members of non-automatic groups. The public group members page has no pagination UI, so any group with more than 50 members shows only the first 50 and the rest cannot be reached. That is a membership-display regression, the opposite of what the commit title claims.
   - **Evidence:** only the admin template (admin/templates/group.hbs:15-19) gets next/previous controls. `members.hbs` just switches `model` to `members`.

3. **app/assets/javascripts/admin/controllers/admin-group.js.es6:11-14 — Important.**
   - **Claim:** `totalPages` is off by one whenever `user_count` is an exact multiple of `limit`. It uses `Math.floor(user_count / limit) + 1`: with 50 members and limit 50 the pager shows "1/2", `showingLast` is false, and "next" sets `offset = min(50, 50) = 50` and loads an empty page that displays as "2/2". The correct formula is `Math.ceil(user_count / limit)`.
   - **Evidence:** reasoned arithmetic. The patch has no QUnit test for this.

4. **app/assets/javascripts/discourse/models/group.js:59 — Important (linter rule enforced by CI).**
   - **Claim:** `addMembers` ends with `})` and no semicolon. jshint reports W033 "Missing semicolon"; `lastsemic: true` only relaxes the last statement inside a one-line block. The file is `.js`, so `jshint .` in `.travis.yml:32` lints it and CI should fail.
   - **Command (suggested, not run):** `npx jshint app/assets/javascripts/discourse/models/group.js`.

5. **app/assets/javascripts/discourse/models/group.js:82 — Minor.**
   - **Claim:** `if (!this.get('id')) { return };` has a stray `;` after the block, which jshint reports as W032 "Unnecessary semicolon" (a warning).
   - **Also:** line 21 (`{ return ; }`) does not follow CONTRIBUTING's "no space … before `)`"-style spacing rules.

6. **app/assets/javascripts/admin/controllers/admin-group.js.es6:7 and :12 — Minor.**
   - **Claim:** both lines use `== 0`, which breaks `.jshintrc` `"eqeqeq": true`. `eqnull` only allows `== null`.
   - **Why Minor:** `jshint .` only lints `.js` files by default, so CI does not lint this `.es6` file and the rule is not enforced here.

7. **app/assets/javascripts/discourse/models/group.js:83 — Minor.**
   - **Claim:** `{type: "DELETE"}` on a moved line breaks CONTRIBUTING "use spaces … around `{` and before `}`". Every other ajax call in the same diff was reformatted to `{ type: ... }`.

8. **spec/controllers/groups_controller_spec.rb:72-85 (not in the patch) — Important.**
   - **Claim:** this is a gap against CONTRIBUTING "Include tests". The change implements pagination and changes the `members` response from a bare array to `{ members, meta: { total, limit, offset } }`. The existing `pending "ensures that membership can be paginated"` spec is left pending and still parses the old array shape.
   - **Evidence:** no test covers the new public response contract or the `meta` fields that the client depends on (group.js:31-35).

9. **spec/controllers/admin/groups_controller_spec.rb:115 — Minor.**
   - **Claim:** the "cannot remove members from automatic groups" spec sends `xhr :put, :remove_member`, but the route is `delete "members"` (config/routes.rb:49). Controller specs skip routing, so it passes while testing the wrong verb.

10. **spec/controllers/admin/groups_controller_spec.rb — Minor.**
    - **Claim:** coverage dropped with no replacement:
      - "succeeds silently when adding non-existent users" (still relevant to `add_members`, controller lines 70-74)
      - "is able to update group members/name" for a non-automatic group
      - "is able to create a group"
    - The new `.update` spec only covers the automatic-group branch.

11. **app/controllers/admin/groups_controller.rb:22-34 and app/assets/javascripts/discourse/models/group.js:62-68 — Minor.**
    - **Claim:** `asJSON` sends `alias_level`, and the form shows the alias combo box when creating a group, but `create` never reads `params[:alias_level]`. The value is silently dropped on create and only applied on a later save. This already happened before the patch, but the rewritten `create` kept it.

12. **Commit 060cda7772 — Minor.**
    - **Claim:** CONTRIBUTING §5 requires a summary line followed by "a detailed, clear, and complete description". The body is empty, yet the commit removes the admin `PATCH /admin/groups/:id` incremental API and the `group[usernames]` payload, a breaking change for admin API users that is documented nowhere.

### Files not reviewed in depth
- `app/assets/stylesheets/common/admin/admin_base.scss`: CSS layout move only. No standards apply beyond whitespace, and I saw no problem there.
- `app/assets/javascripts/discourse/templates/user-selector-autocomplete.raw.hbs` and `.../components/admin-group-selector.hbs`: whitespace and indentation only.
- `config/locales/client.en.yml`: checked that the new keys are used. Other locales are maintained through Transifex, per CONTRIBUTING.
- All other files in the patch I reviewed against the surrounding source.

**Summary:** 12 findings on the Standards/Spec axes: 5 Important (counter-cache and `primary_group_id` corruption in `remove_member`, public members page capped at 50 members, pager off by one, a jshint error in group.js that should fail CI, and the pending pagination spec left untouched) and 7 Minor. The worst is finding 1, `users.delete` in `remove_member`.

I did not run jshint or rspec because neither is installed and installing was out of bounds. Finding 1's counter-cache behaviour comes from my knowledge of Rails 4.1.8 `has_many :through` delete semantics, not from reading the gem source, so run the suggested assertion before acting on it.
