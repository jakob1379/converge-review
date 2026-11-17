Review of pinned.patch (`git diff 7ea067aae9..7355f05e6a`, one commit, 19 files, +831/−126). I confirmed the patch file is byte-identical to the live `git diff 7ea067aae9`.

**Spec source:** none was supplied. The commit says "Closes #35562", but I did not fetch that issue because you said there is no spec. As a stand-in spec I used the commit subject plus the new Javadoc contracts the patch adds to `GroupPermissionEvaluator` and `UserPermissionEvaluator`.

**Standards sources:** `CONTRIBUTING.md`, `PR-CHECKLIST.md`, `docs/tests-development.md`, `tests/MIGRATING_TESTS.md` and `test-framework/README.md`. The hamcrest-preference rule in tests-development.md applies to the legacy testsuite. The new framework docs use JUnit `Assertions`, so I did not flag the new test for that.

Nothing was built or run. Every failing-test claim below is reasoned from source, and each one gives a test to run.

## Spec axis

**1. Important (possibly Critical for v2 users): FGAP v2 `getGroupIdsWithViewPermission()` never returns group IDs, which breaks user search and count**
- **Where:** `services/src/main/java/org/keycloak/services/resources/admin/permissions/GroupPermissionsV2.java:106-128`, mainly lines 121 and 123. It is used at `services/src/main/java/org/keycloak/services/resources/admin/UsersResource.java:398, 425, 430, 448`.
- **Claim:** The Javadoc (`GroupPermissionEvaluator.java:~140-146`) promises "IDs of groups with view permission". The implementation cannot produce them.
- **Evidence:**
  - Per-group v2 resources are created with `resourceStore.create(resourceServer, name, owner)` (`AdminPermissionsSchema.java:121`). That call sets no type, and the name is the bare group id.
  - So `resourceStore.findByType(server, "Groups", ...)` only matches the all-groups type resource, which gets its type at `AdminPermissionsSchema.java:271-274`. The JPA query `findResourceIdByType` filters on `r.type = :type`.
  - For that one resource the code calls `hasPermission(groupResource.getId(), ...)`. `findByName` with a resource UUID returns null, so it falls back to the type resource. On a grant it adds the resource's UUID (line 123), not a group id.
  - **Effect A, all-groups `view-members`:** the set is `{typeResourceUUID}`. That set becomes the `UserModel.GROUPS` filter in `UsersResource.searchForUser`. `JpaUserProvider.groupsWithPermissionsSubquery` (model/jpa `JpaUserProvider.java:1059-1089`) needs `groupId IN set` and also a resource named `"group.resource." + groupId`, which is the v1 naming. Nothing matches, so `GET /users` returns empty even though `canView(user)` would allow every member.
  - **Effect B, per-group `view-members`:** the set is empty, so no DB filter is applied. `searchForUser` pages over all users and then post-filters with `canView`, so pagination is wrong: a page can come back short or empty while visible users exist. `GET /users/count` goes to `getUsersCount(realm, emptySet)`, which returns 0 at `JpaUserProvider.java:599-602`, while search returns 1.
  - `testCanViewUserByViewGroupMembers` passes only through the post-filter path. Neither effect is tested.
- **Failing tests** (add to `GroupResourceTypeEvaluationTest`, reasoned):
  ```java
  @Test public void allGroupsViewMembers() {
    var p = createUserPolicy(realm, client, "p", realm.admin().users().search("myadmin").get(0).getId());
    createAllPermission(client, AdminPermissionsSchema.GROUPS_RESOURCE_TYPE, p, Set.of(VIEW_MEMBERS));
    assertEquals(1, realmAdminClient.realm(realm.getName()).users().search(null, -1, -1).size()); // gets 0
  }
  @Test public void countByGroupViewMembers() {
    var p = createUserPolicy(realm, client, "p", realm.admin().users().search("myadmin").get(0).getId());
    createPermission(client, topGroup.getId(), AdminPermissionsSchema.GROUPS_RESOURCE_TYPE, Set.of(VIEW_MEMBERS), p);
    assertEquals(1, realmAdminClient.realm(realm.getName()).users().count()); // gets 0
  }
  ```

**2. Important: in v2, `canManage()` is granted by the `view` scope (privilege escalation)**
- **Where:** `services/src/main/java/org/keycloak/services/resources/admin/permissions/GroupPermissionsV2.java:65-71`, line 70 being `hasPermission(null, VIEW, MANAGE)`. The interface Javadoc at `GroupPermissionEvaluator.java:~72-78` repeats it ("VIEW or MANAGE groups").
- **Claim:** An admin with only all-groups `view` passes `requireManage()`. That check is the only guard on `GroupsResource.addTopLevelGroup` (`GroupsResource.java:181`). So that admin can create top-level groups, and can move any existing group to top level via `rep.id` and `realm.moveGroup`. By contrast `canManage(GroupModel)` (line 78) correctly requires `MANAGE` only. This looks like canView copied into canManage, and the Javadoc copies the same mistake, so the Javadoc cannot count as intent.
- **Failing test** (reasoned): grant `createAllPermission(client, GROUPS_RESOURCE_TYPE, policy, Set.of(VIEW))`. Then `realmAdminClient.realm(..).groups().add(new GroupRepresentation(){{setName("x");}})` should return 403. On the patched code it returns 201.

**3. Minor: Javadoc contradicts the implementation in `GroupPermissionEvaluator`**
- **Where:** `services/src/main/java/org/keycloak/services/resources/admin/permissions/GroupPermissionEvaluator.java:132-135` and `:145`.
- **Evidence:**
  - The `requireManageMembers` Javadoc says it throws when `canManageMembership(GroupModel)` is false. The real check is `canManageMembers` (`GroupPermissions.java:376-379`).
  - The `getGroupIdsWithViewPermission` Javadoc says "@return Stream of IDs", but the return type is `Set<String>`.
  - The `canView()` Javadoc says "Or if it has a permission to VIEW or MANAGE groups" without the "For V2 only" qualifier that `canList`/`canManage` carry. v1 `canView()` checks roles only.

**4. Minor: removing a v2 group leaves its FGAP resource and permissions behind**
- **Where:** `services/src/main/java/org/keycloak/services/resources/admin/permissions/AdminPermissions.java:73-98`, plus `GroupPermissionsV2` `setPermissionsEnabled`, which throws.
- **Claim:** The `GroupRemovedEvent` cleanup only runs for v1, and nothing replaces it for v2. `AuthorizationStoreFactory` synchronizers cover clients, realms and users only. A per-group resource named after the deleted group's id, and its permissions, stay behind. This is reasoned. It may be planned for a later issue, but the commit does not say so.

## Standards axis (CONTRIBUTING.md / PR-CHECKLIST.md)

**5. Minor: changes not related to the feature**
- **Rule:** CONTRIBUTING.md says "No changes to code not directly related to your PR" and "Do not format or refactor code that is not directly related… submit a separate PR". PR-CHECKLIST.md says "The PR does not contain changes not relevant to the GitHub Issue".
- **Examples:**
  - `services/.../permissions/AdminPermissions.java:74-97`: the v1 listener is restructured, and the feature check moves from event time to registration time. That is a behaviour change, and it is v1-only, because v1 and v2 share a feature key and cannot both be on.
  - `test-framework/core/src/main/java/org/keycloak/testframework/util/ApiUtil.java:8-14`: rewritten as try-with-resources.
  - `server-spi-private/src/main/java/org/keycloak/models/utils/ModelToRepresentation.java:~176`: the public static `searchGroupModelsByAttributes` is removed.
  - `services/.../permissions/UserPermissions.java:~229-299, 580-591`: `canManageDefault`/`canViewDefault` are deleted and inlined, which forces the change in `RolePermissions.java:302`.
  - `server-spi-private/src/main/java/org/keycloak/authorization/AdminPermissionsSchema.java:54-76`: constants reordered, and the if-chain replaced with a switch.
  - `services/.../admin/GroupResource.java:206`: `child = null` changed to `child`.
  - `tests/base/.../UserResourceTypeEvaluationTest.java:32`: an unused import removed.

**6. Minor: no documentation**
- **Rule:** CONTRIBUTING.md says "Includes documentation", and PR-CHECKLIST.md says "Required documentation is included in the PR or an associated PR".
- **Evidence:** A new "Groups" resource type and three new scopes (`manage-membership`, `manage-members`, `view-members`) are added with no docs change. `docs/documentation/server_admin/topics/admin-console-permissions/fine-grain.adoc` covers v1 only. v2 is EXPERIMENTAL and the earlier Users/Clients v2 work is also undocumented, so this is low severity.

**7. Minor: nits in the new test**
- **Where:** `tests/base/src/test/java/org/keycloak/tests/admin/authz/fgap/GroupResourceTypeEvaluationTest.java`.
- **Evidence:** line 2 has the copyright year 2024 on a new 2025 file (the sibling `GroupPermissionsV2` says 2025). Line 68 has a stray `;;`. The `@BeforeEach` comment at ~line 70 has a typo ("initializaed"). These are cosmetic and break no documented rule.

The commit message follows the documented format: summary, then `Closes #35562`, then `Signed-off-by`. No finding there.

## Unreviewed files / axes
- All 19 files in the patch were reviewed.
- I read the test files (`GroupResourceTypeEvaluationTest`, `RealmAdminPermissionsConfig`, `UserResourceTypeEvaluationTest`, `ApiUtil`) for coverage and standards, but did not run them.
- **Spec axis:** partially run. Issue #35562 was not fetched, so the checks are against the commit subject and the patch's own Javadoc contracts, not the issue text.
- **Standards axis:** ran fully against the docs listed at the top.

Not checked: whether the inherited no-arg `UserPermissionsV2.canView()`/`canManage()` (which this patch does not change) behave correctly for v2. Findings 1 and 2 are the ones that matter. Finding 2 is an authorization hole in an experimental feature.
