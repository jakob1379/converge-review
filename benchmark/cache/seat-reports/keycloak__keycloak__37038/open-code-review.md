## Review of pinned.patch (7ea067aae9..7355f05e6a, FGAP v2 Groups resource type)

I followed the OCR delegate flow: `ocr delegate preview --from 7ea067aae9 --to HEAD`, then `ocr delegate rule`, which returned only generic Java rules. `git diff 7ea067aae9` matches pinned.patch byte for byte. There was no spec, so I judged the patch against its own javadoc and the head commit message. I didn't build or run anything, so every claim below is reasoned from source, and I've given a test sketch for each Critical and Important finding.

### Findings

**1. Critical: a VIEW permission on all groups also grants the global "manage groups" check**
- **Where:** `services/src/main/java/org/keycloak/services/resources/admin/permissions/GroupPermissionsV2.java:70`, inside `canManage()`. The same behaviour is documented in `GroupPermissionEvaluator.java:75-76`.
- **Claim:** `canManage()` returns `hasPermission(null, VIEW, MANAGE)`, so an admin who only has an all-groups VIEW permission passes it.
- **Evidence:**
  - `GroupsResource.addTopLevelGroup` (`GroupsResource.java:181`) gates only on `auth.groups().requireManage()`.
  - That endpoint can create top-level groups, and when `rep.id` is set it can move any existing subgroup to top level (`realm.moveGroup(child, null)`). Neither path checks per-group manage.
  - In V1, `canManage()` means MANAGE_USERS only, so this is a VIEW-to-write escalation that V1 does not have. The interface javadoc copies the same VIEW-or-MANAGE wording, so the doc repeats the bug.
- **Failing test sketch** (`GroupResourceTypeEvaluationTest` style):
  1. `createAllGroupsPermission(policy, Set.of(VIEW))`
  2. `realmAdminClient.realm(r).groups().add(new GroupRepresentation(){{setName("x");}})`
  3. Expected 403. On the patched code this returns 201.

**2. Important: `getGroupIdsWithViewPermission()` collects authz resource IDs, not group IDs, and misses per-group grants**
- **Where:** `GroupPermissionsV2.java:121-123`. Consumed at `UsersResource.java:398, 425, 430, 448` and `BruteForceUsersResource.java:147`.
- **Claim:** `resourceStore.findByType(server, "Groups", …)` only ever returns the "Groups" type resource. The ID it adds is `groupResource.getId()`, which is an authz resource ID, and it is passed as the `groupId` argument to `hasPermission`, which looks it up with `findByName`.
- **Evidence:**
  - Per-group resources are created with `resourceStore.create(server, name, owner)` in `AdminPermissionsSchema.getOrCreateResource` and never get a type. Only `init()` sets `type` (`AdminPermissionsSchema.java:274`).
  - `findResourceIdByType` filters on `r.type = :type` (`ResourceEntity.java:64`), so per-group resources never match.
- **Result A, all-groups VIEW_MEMBERS/MANAGE_MEMBERS:**
  - The method returns `{<"Groups" resource id>}`.
  - `UsersResource.searchForUser` stores that set as `UserModel.GROUPS`, and `JpaUserProvider` (lines 762-765) then restricts the query to members of a group that does not exist.
  - The user list and user count both come back empty for an admin who is supposed to see all group members.
- **Result B, per-group VIEW_MEMBERS only:**
  - The method returns an empty set.
  - `getUsersCount(realm, Set.of())` returns 0 (`JpaUserProvider.java:600`), while `/users` returns the users through the per-user `canView` filter. The count and the list disagree, which breaks admin-UI paging.
- **Failing test sketch:**
  1. `createAllGroupsPermission(policy, Set.of(VIEW_MEMBERS))`
  2. `realmAdminClient.realm(r).users().search(null,-1,-1)` should contain alice. On the patched code it is empty.
  3. Separately: with a per-group VIEW_MEMBERS permission on topGroup, `users().count()` should be 1. On the patched code it is 0.
- **Coverage gap:** the shipped test `testCanViewUserByViewGroupMembers` passes only because of the fallback in Result B, and it never asserts the count.

**3. Important: `hasPermission` checks either the group resource or the type resource, never both**
- **Where:** `GroupPermissionsV2.java:141-152`.
- **Claim:** The method evaluates exactly one resource, the per-group one if it exists and otherwise the "Groups" type resource. That gives two failure modes.
- **Failure mode (a), all-groups grants silently dropped:**
  - If group G has any per-group resource (for example, someone else's MANAGE_MEMBERSHIP permission on G), only that resource is evaluated.
  - `DefaultPolicyEvaluator` runs `findByResourceType` only when `resource.getType() != null`, and per-group resources have no type.
  - `findPolicyIdByNullResourceScope` excludes policies that carry `defaultResourceType`.
  - So all-groups permissions are not considered for G. Adding a narrow per-group permission removes the all-groups grants for that group.
- **Failure mode (b), per-group grants leak to every group:**
  - If G has no per-group resource and any all-groups permission exists (for any user, any scope), the type resource is evaluated.
  - That type resource has `type="Groups"`, so `findByResourceType(server,"Groups")` (`PolicyEntity.java:64`, matching `defaultResourceType`) also pulls in every per-group permission.
  - `DecisionPermissionCollector.onComplete` grants a scope permission's scopes without checking `containsResource`.
  - So a VIEW permission on group A also grants VIEW on every group with no per-group resource.
- **Note:** `UserPermissionsV2.hasPermission` has the same pattern. That code predates this patch, but this patch copies it into the new Groups type.
- **Test sketch for (b):**
  1. Per-group VIEW on myGroup for myadmin.
  2. All-groups MANAGE_MEMBERSHIP for a different user.
  3. `realmAdminClient…groups().groups()` should have size 1. By this reasoning it returns 2.
- **Test sketch for (a):**
  1. All-groups VIEW for myadmin.
  2. Per-group MANAGE_MEMBERSHIP on topGroup for another user.
  3. `groups().group(topGroup).toRepresentation()` should succeed. By this reasoning it returns 403.

**4. Minor: a null resource type now throws NPE instead of `IllegalStateException`**
- **Where:** `server-spi-private/src/main/java/org/keycloak/authorization/AdminPermissionsSchema.java:107`.
- **Evidence:** `switch (resourceType)` throws NPE when `resourceType` is null. Before the patch, a null type fell through to `IllegalStateException("Could not map resource object…")`. `updateResources` (`RepresentationToModel.java:1423`) calls this for any policy on the admin-permissions client that has `resources` set. Only `ScopePermissionRepresentation` is validated to carry a resource type.

**5. Minor: the cleanup listener is now registered only if V1 is enabled at boot**
- **Where:** `services/src/main/java/org/keycloak/services/resources/admin/permissions/AdminPermissions.java:74`.
- **Claim:** The feature check moved from event time to registration time.
- **Evidence:** The legacy testsuite turns V1 on at runtime with `@EnableFeature(value = ADMIN_FINE_GRAINED_AUTHZ, skipRestart = true)` (for example `UsersTest.java:228/235/258/295` and the token-exchange tests). In those runs the role/client/group-removed listener is never registered, so V1 permission resources are left orphaned. Production is unaffected, because Profile is fixed at boot and V1 and V2 cannot both be enabled.

**6. Minor: one javadoc describes the wrong check**
- **Where:** `services/src/main/java/org/keycloak/services/resources/admin/permissions/GroupPermissionEvaluator.java:133`.
- **Evidence:** The javadoc for `requireManageMembers` says it throws if `canManageMembership` is false. The implementation (`GroupPermissions.requireManageMembers`) checks `canManageMembers`.

### Coverage

- **OCR-reviewable files:** 16 of 16 reviewed, 0 skipped.
- **Files in the patch:** all 19 read. OCR excluded three test files by `default_path`:
  - `tests/base/src/test/java/org/keycloak/tests/admin/authz/fgap/GroupResourceTypeEvaluationTest.java`
  - `tests/base/src/test/java/org/keycloak/tests/admin/authz/fgap/RealmAdminPermissionsConfig.java`
  - `tests/base/src/test/java/org/keycloak/tests/admin/authz/fgap/UserResourceTypeEvaluationTest.java`

  I read these as test-coverage context. They produced no findings of their own; the gaps they leave are listed under findings 1-3.
- **Unreviewed files:** none.

I didn't run any test, so findings 1-3 are unconfirmed until someone runs those sketches. Finding 3 rests on my reading of `DefaultPolicyEvaluator`, `DecisionPermissionCollector` and the JPA named queries.
