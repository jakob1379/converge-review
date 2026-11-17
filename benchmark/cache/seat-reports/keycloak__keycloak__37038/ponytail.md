**Over-engineering review: pinned.patch (head 7355f05e6a, FGAP v2 Groups resource type)**

The patch adds a Groups resource type with five scopes to `AdminPermissionsSchema` and a new `GroupPermissionsV2` evaluator, wired in through `MgmtPermissionsV2.groups()`. It also tidies V1: it removes `canManageDefault`/`canViewDefault`, `getGroupsWithViewPermission(GroupModel)`, `ModelToRepresentation.searchGroupModelsByAttributes` and a duplicate `.filter(canView)` in `UsersResource`.

Those deletions are correct. A grep finds no remaining callers of any removed method. The `UsersResource.searchForUser` filter really was a duplicate, because `toRepresentation` already filters by `canView`. The `AdminPermissions.registerListener` change keeps the same behaviour: V1 and V2 are two versions of one feature, so they are never on at the same time.

No Maven build or test was run, as instructed. Every claim below is reasoned from the source.

### Findings

1. **`services/src/main/java/org/keycloak/services/resources/admin/permissions/GroupPermissionsV2.java:120-125` — Important**
   - **Claim:** `getGroupIdsWithViewPermission()` already holds each group `Resource`. It then passes `groupResource.getId()` to `hasPermission(String groupId, …)`, which looks the resource up again by name, and it adds `groupResource.getId()` to the result. That ID is the authz resource UUID, not the group ID. The extra lookup is the over-engineering, and it causes two failures:
     - The name lookup always misses, because `getOrCreateResource` names the resource after the group ID (`AdminPermissionsSchema.java:102-118`). So `hasPermission` falls back to the all-groups resource. With only per-group VIEW_MEMBERS permissions the set is always empty. Users are then found by a full scan, with a group-hierarchy check per user, which is slow.
     - With an all-groups VIEW_MEMBERS or MANAGE_MEMBERS permission, every group resource passes. The method returns resource UUIDs, and `UsersResource.searchForUser:448-451` (also `BruteForceUsersResource:147`) puts them in `UserModel.GROUPS` as group IDs. No user matches, so user search comes back empty.
   - **Evidence:** V1 does this correctly. It calls `hasPermission(resource, …)` and adds `resource.getName().substring(prefix)` (`GroupPermissions.java:313-315`).
   - **Fix:** Evaluate the `Resource` you already have, and add `groupResource.getName()`. That is fewer lines.
   - **Missing test (not run):** in `GroupResourceTypeEvaluationTest`, call `createAllGroupsPermission(policy, Set.of(VIEW_MEMBERS))`, then `realmAdminClient.realm(..).users().search(null,-1,-1)`. Expect Alice. This fix is reasoned to return an empty list. The existing tests use only per-group permissions, so they pass by the fallback path.

2. **`GroupPermissionsV2.java:65-71` — Important (copy-paste artefact)**
   - **Claim:** `canManage()` repeats the body of `canView()`, including the scope set: `hasPermission(null, VIEW, MANAGE)`. So an all-groups VIEW permission also grants manage-all.
   - **Evidence:** `GroupsResource.addTopLevelGroup:181` uses `auth.groups().requireManage()`, so a view-only admin can create or re-parent top-level groups. The `GroupPermissionEvaluator` javadoc for `canManage()` (around line 86) repeats the same "VIEW or MANAGE" text, so the doc carries the mistake too.
   - **Fix:** Use `hasPermission(null, MANAGE)`.
   - **Missing test (not run):** in `testViewGroups`, after `createAllGroupsPermission(policy, Set.of(VIEW))`, assert that `realmAdminClient.realm(..).groups().add(new GroupRepresentation())` returns 403. On the patched code it is reasoned to succeed.

3. **`GroupPermissionsV2.java:130-165` — Minor (merge)**
   - **Claim:** `hasPermission` is a third near-copy of the same evaluator. The other two are `UserPermissionsV2.java:94-133` and `ClientPermissionsV2.java:207-235`. Each copy does the same steps: same-realm check, server null check, find by name, fall back to the type resource when it has policies, evaluate, then match scopes.
   - **Evidence:** The copies already differ. The Users copy filters with `permission.getResourceId().equals(resource.getId())`, which an earlier commit (c2acddc7ca) added to stop a single-user grant from granting all users. The Groups copy leaves that filter out and gives no reason.
   - **Fix:** Put one `hasPermission(resourceType, id, context, scopes...)` on `MgmtPermissionsV2` and delete the three copies, roughly 60 lines removed. Whether dropping the filter is exploitable for groups was not proven.

4. **`tests/base/src/test/java/org/keycloak/tests/admin/authz/fgap/GroupResourceTypeEvaluationTest.java:72-77, 194-199, 260-265` — Minor (delete)**
   - **Claim:** Each of these blocks wraps the response in `try (Response response = …)`, asserts the status is CREATED, and then calls `ApiUtil.handleCreatedResponse(response)`.
   - **Evidence:** This patch changes `handleCreatedResponse` (`test-framework/.../ApiUtil.java:8-14`) so that it asserts 201 itself and closes the response. The outer try and the extra assertion now do nothing.
   - **Fix:** Use a single `x.setId(ApiUtil.handleCreatedResponse(realm.admin().groups().add(x)))`, as line 165 already does. That saves about 9 lines.

5. **`services/src/main/java/org/keycloak/services/resources/admin/permissions/GroupPermissionEvaluator.java:133` and `:145` — Minor (doc accuracy)**
   - **Claim:** The new javadoc on `requireManageMembers` says it throws when `canManageMembership` is false. It should say `canManageMembers`, which is what V1 actually checks. The `@return` on `getGroupIdsWithViewPermission` says "Stream of IDs", but the method returns a `Set`.
   - **Evidence:** Both javadocs were added in this patch and contradict the code they describe.

### Not flagged
- `GroupPermissionsV2` throwing `UnsupportedOperationException` for the V1 management methods: `UserPermissionsV2` and `ClientPermissionsV2` already do this, so it follows house style.
- The `UserPermissionsV2.canMapRoles` / `canManageGroupMembership` rewrite: it saves one evaluation and behaves the same.
- The `canList`/`canQuery` reorderings: they behave the same.

### Unreviewed files
None. I read the diffs of all 19 files in the patch, plus the surrounding source for `GroupPermissions`, `UserPermissionsV2`, `ClientPermissionsV2`, `AdminPermissions`, `UsersResource`, `GroupsResource` and the new test.

Verdict: fix 1 and 2 first. Lean: about 70 lines can be removed (findings 1, 3 and 4).
Not checked: I could not read commit c2acddc7ca, because this is a partial clone and the network is blocked. So I could not confirm why the resource-ID filter exists or whether finding 3 is a real bug for groups.
