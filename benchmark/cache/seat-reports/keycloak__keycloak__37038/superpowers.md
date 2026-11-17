Review of pinned.patch (7ea067aae9 to 7355f05e6a, FGAP v2 Groups resource type). There was no spec, so I reviewed against the head commit's intent and the patch's own Javadoc contracts. I did not build or run anything. Every claim below comes from reading the code. The "failing test" items are test sketches I wrote but did not run.

## Findings

**1. services/src/main/java/org/keycloak/services/resources/admin/permissions/GroupPermissionsV2.java:70 — Critical**
- **Claim:** A VIEW-only permission grants global manage rights (privilege escalation). `canManage()` returns `hasPermission(null, VIEW, MANAGE)`, so an all-groups VIEW permission makes `canManage()` true.
- **Effect:** `GroupsResource.addTopLevelGroup` (GroupsResource.java:181) only calls `auth.groups().requireManage()`. A view-only admin can therefore create top-level groups. With `rep.id` set, they can also re-parent any existing group to top level (`realm.moveGroup(child, null)`, GroupsResource.java:198).
- **Evidence:** The interface Javadoc at GroupPermissionEvaluator.java:75 documents this V2 behaviour, so the contract itself is wrong as well as the code. In V1, `canManage()` means MANAGE_USERS only. The test `testViewGroups` grants all-groups VIEW but never tries a write.
- **Failing test (not run):** add to GroupResourceTypeEvaluationTest: `createAllGroupsPermission(policy, Set.of(VIEW));` then `realmAdminClient.realm(realm.getName()).groups().add(named("x"))`. Assert status 403. It returns 201 on the patched code.

**2. GroupPermissionsV2.java:121-123 (`getGroupIdsWithViewPermission`) — Critical**
- **Claim:** It returns authz resource IDs instead of group IDs, and only ever looks at the "Groups" type resource.
- **Evidence:**
  - Per-group resources are created without a type (`AdminPermissionsSchema.getOrCreateResource` calls `resourceStore.create(server, name, owner)` and never `setType`). So `findByType(server, "Groups")` yields only the all-groups type resource.
  - The code then calls `hasPermission(groupResource.getId(), …)`, which does `findByName` with an ID. That misses and falls back to the type resource. It then adds `groupResource.getId()`, the type resource's ID, not a group ID.
- **Consequences:**
  - (a) An admin with an all-groups VIEW_MEMBERS or MANAGE_MEMBERS permission gets `UserModel.GROUPS = {<Groups-resource-id>}`. `JpaUserProvider.searchForUserStream` (line 762) then filters by membership in a group with that ID, so `GET /users` returns nothing. `GET /users/count` also returns 0.
  - (b) An admin with only per-group VIEW_MEMBERS gets an empty set. `getUsersCount(realm, emptySet)` returns 0 (JpaUserProvider.java:600), while `GET /users` returns members through the post-filter. So count and list disagree.
  - (c) With an empty set there is no DB-side group filter, so `first`/`max` are applied before the `canView` post-filter, and pages come back short.
- **Affected callers:** UsersResource.java:398, 425, 430, 448 and BruteForceUsersResource.java:147.
- **Failing tests (not run):**
  - In `testCanViewUserByViewGroupMembers`, after granting, assert `realmAdminClient.realm(..).users().count() == 1`. It returns 0.
  - New test: `createAllGroupsPermission(policy, Set.of(VIEW_MEMBERS))`, then assert `users().search(null,-1,-1)` contains alice. It comes back empty.

**3. GroupPermissionsV2.java:138-150 (`hasPermission`) and GroupsResource.java:113 / GroupResource.java (getSubGroups filter) — Important (reasoned)**
- **Claim:** A per-group resource hides all-groups permissions. Once any permission targets group G, a resource named G.id exists, and the fallback to the "Groups" type resource no longer runs.
- **Evidence:**
  - `DefaultPolicyEvaluator` only adds type-level policies when `resource.getType() != null`, and per-object resources have no type.
  - `findByScopes(server, null, …)` matches only policies with no resources. All-groups permissions are attached to the type resource, so they don't match.
- **Effect:** An admin holding all-groups VIEW/MANAGE loses access to every group that has its own permission for someone else. This conflicts with the Javadoc contract ("permission to VIEW or MANAGE groups") and the test comment "fallback to all-groups permission". The patch also removed the `canViewGlobal` short-circuit in GroupsResource and GroupResource, so every listing is decided by `canView(g)` per group and hits this flaw.
- **Note:** The same pattern already exists in UserPermissionsV2; this patch carries it over to groups.
- **Suggested test (not run):** `createAllGroupsPermission(policyMyAdmin, Set.of(VIEW))` plus `createGroupPermission(topGroup, Set.of(VIEW_MEMBERS), otherUserPolicy)`. Then `groups().groups()` should contain top_group.

**4. GroupPermissionsV2.java:144-147 — Minor (reasoned; feature is EXPERIMENTAL)**
- **Claim:** Realms whose admin-permissions client was initialised before this patch have no "Groups" type resource and none of the new scopes. `AdminPermissionsSchema.init` returns early if the client exists, and no migration is added.
- **Effect:** `getResourceTypeResource` returns null, then `policyStore.findByResource(server, null)` throws an NPE (JPAPolicyStore.java:215 calls `resource.getId()`). Any group view or manage check by an admin without the MANAGE_USERS/VIEW_USERS roles returns HTTP 500. Creating group permissions there also fails with "Scope does not exist".

**5. server-spi-private/src/main/java/org/keycloak/authorization/AdminPermissionsSchema.java:328 (`getResourceName`) — Minor**
- **Claim:** It was not extended for GROUPS. Group permission resources therefore render `resource.getDisplayName()`, which is null (resources are created with only a name). There is also no "All groups" label for the type resource, unlike the USERS branch.
- **Evidence:** It is used by PolicyResourceService.java:218 when listing a permission's resources.

**6. GroupPermissionsV2 / AdminPermissions.java:73-99 — Minor (spec gap)**
- **Claim:** Nothing cleans up V2 group resources and permissions when a group is deleted. The `GroupRemovedEvent` listener is only registered under ADMIN_FINE_GRAINED_AUTHZ (v1). The v1 and v2 features are mutually exclusive (same unversioned key). There is no group synchronizer in AuthorizationStoreFactory.
- **Effect:** Orphaned resources whose names are stale group IDs remain. The `registerListener` refactor itself does not change behaviour.

**7. services/src/main/java/org/keycloak/services/resources/admin/permissions/GroupPermissionEvaluator.java:133 — Minor (doc breach)**
- The Javadoc for `requireManageMembers` says it throws if `canManageMembership(GroupModel)` is false. The implementation (GroupPermissions.java:376-380) checks `canManageMembers`.

**8. GroupPermissionEvaluator.java:145 — Minor (doc breach)**
- `@return Stream of IDs …` is wrong: the method returns `Set<String>`. The Javadoc also omits that V2 returns the type resource ID (finding 2).

**9. tests/base/src/test/java/org/keycloak/tests/admin/authz/fgap/GroupResourceTypeEvaluationTest.java — Minor (coverage gap)**
- No test covers:
  - all-groups VIEW_MEMBERS or MANAGE_MEMBERS (would catch finding 2)
  - `users().count()` (would catch finding 2b)
  - VIEW-only write attempts (would catch finding 1)
  - mixed all-groups and per-group permissions (would catch finding 3)
- `testManageGroupMembership` grants both the user-side and group-side scopes and asserts only the positive case, so it does not show that the group MANAGE_MEMBERSHIP check is enforced.

Checked and found equivalent to the old behaviour (no finding):
- V1 `GroupPermissions` `canList`/`canView`/`canManage` rewrites.
- Removing `|| users().canManage()` in V1 (`canView` already covers the MANAGE scope and the MANAGE_USERS role).
- `requireViewMembers` now delegating to `canViewMembers`.
- Removing the extra `.filter(canView)` in `UsersResource.searchForUser` (`toRepresentation` still filters).
- Dropping `AdminRoles.ADMIN` from `hasOneAdminRole` (it is a master realm role, not a realm-management client role, so it was dead).
- `canMapRoles`/`canManageGroupMembership` in V2.

## Unreviewed files
None. All 19 files in the patch were reviewed. These four got only a light read because they are mechanical: test-framework/core/.../ApiUtil.java, tests/base/.../RealmAdminPermissionsConfig.java, tests/base/.../UserResourceTypeEvaluationTest.java (an unused import removed), and server-spi-private/.../ModelToRepresentation.java (I grepped and found no remaining callers of the removed method).

No tests were run because Maven runs were excluded, so every "fails on the patched code" claim is a test sketch, not an observed failure.
