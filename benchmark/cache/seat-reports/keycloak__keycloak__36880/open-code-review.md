I reviewed the 5 production files in the patch and found 3 Important issues: a privilege escalation path, a null-pointer crash on realms set up before this change, and a case where one client-specific permission removes "all clients" access. There are also 5 Minor issues. I did not build or run anything (benchmark mode), so every claim below is reasoned from reading the code. Where I give a test, it is a sketch I expect to fail on the patched code; I have not run it.

The OCR delegate preview (range b7b84d75d1..1950a51102) listed 10 files. It marked 5 as reviewable and filtered the 5 test files out with `default_path`. I reported only and applied no fixes, as the caller asked, even though the skill says to auto-fix.

## Findings

**1. services/src/main/java/org/keycloak/services/resources/admin/permissions/ClientPermissionsV2.java:91 (canMapRoles), also :96 (canMapCompositeRoles) — Important, security**
- **Claim:** A permission to map roles on "all clients" also covers the `realm-management` client, whose roles are the realm's admin roles. The admin-role check (`checkAdminRoles`) is skipped on this path. So an admin with all-clients `map-roles` plus users `map-roles` on any user (themselves included) can give that user `realm-management/realm-admin`.
- **Evidence:**
  - `RolePermissions.canMapRole` (RolePermissions.java:308) and `canMapComposite` (:398) do `if (root.clients().canMapRoles/canMapCompositeRoles(container)) return true;`, which never calls `checkAdminRoles(role)`.
  - `ClientPermissionsV2.hasPermission(client, …)` (:214-221) falls back to the all-clients `Clients` resource when the client has no resource of its own. Nothing excludes system clients such as `realm-management` or the admin-permissions client.
  - `ClientRoleMappingsResource.addClientRoleMapping` (:166-176) only requires `users().requireMapRoles(user)` and `roles().requireMapRole(role)`.
  - In V1 you had to grant map-roles on `realm-management` explicitly. In V2 the "all clients" grant includes it silently.
  - The same applies to composites: all-clients `configure` + `map-roles-composite` lets the admin add `realm-admin` as a composite of a role they already hold (RoleContainerResource.java:217).
- **Failing test (sketch, not run):** in `PermissionClientTest`:
  - `createAllPermission(client, clientsType, onlyMyAdminUserPolicy, Set.of(MAP_ROLES))`
  - `createPermission(client, myadmin.getId(), USERS_RESOURCE_TYPE, Set.of(MAP_ROLES), onlyMyAdminUserPolicy)`
  - As myadmin: `realm.users().get(myadminId).roles().clientLevel(realmManagementId).add(List.of(realmAdminRoleRep))`
  - Expected `ForbiddenException`; with this patch I expect the call to succeed.

**2. services/src/main/java/org/keycloak/services/resources/admin/permissions/ClientPermissionsV2.java:217-219 — Important, crash (NPE → HTTP 500)**
- **Claim:** On a realm whose admin-permissions client was created before this change, `getResourceTypeResource(..., CLIENTS_RESOURCE_TYPE)` returns null. The next call, `getPolicyStore().findByResource(server, null)`, then throws a NullPointerException.
- **Evidence:**
  - `AdminPermissionsSchema.init` (AdminPermissionsSchema.java:222-228) returns early when `realm.getAdminPermissionsClient() != null`. So the new `Clients` resource and the new scopes (`configure`, `map-roles-client-scope`, `map-roles-composite`) are never added to existing realms.
  - Realm import with an exported `adminPermissionsClient` (RealmManager.java:567-570) also skips `init`.
  - `JPAPolicyStore.findByResource` (:215) calls `resource.getId()` unconditionally.
  - No migration is added. Any admin without `manage-clients` who triggers `canView(client)`, `canConfigure(client)` or `canMapRoles(client)` on such a realm gets a 500.
  - The same missing data makes creating a per-client permission fail: `getOrCreateResource` throws `ModelException("No scopes found.")` for the `configure` scope.
  - **Fix direction:** null-guard the resource as `hasPermission(String)` (:244-247) already does, and add a migration or make `init` idempotent for missing types and scopes.

**3. services/src/main/java/org/keycloak/services/resources/admin/permissions/ClientPermissionsV2.java:214-221 — Important, authorization logic (denial, not escalation)**
- **Claim:** Once any permission targets client X, X gets its own resource. From then on only that resource is evaluated, so "all clients" permissions no longer apply to X. Example: admin A has all-clients `manage`, someone adds a VIEW-only permission on X for admin B, and A loses manage on X.
- **Evidence:**
  - Per-client resources are created by `getOrCreateResource` via `resourceStore.create(server, name, owner)` with no type.
  - `DefaultPolicyEvaluator` (:70-81) only adds type-level policies when `resource.getType() != null`. Its `findByScopes(resourceServer, null, …)` only matches policies that have no resource, and all-clients permissions are bound to the `Clients` resource.
  - `UserPermissionsV2.hasPermission` uses the same pattern, so this is inherited. The patch does not fix it, and no test combines an all-clients grant with a per-client grant on the same client.
  - **Failing test (sketch, not run):** `createAllPermission(clientsType, policyA, Set.of(MANAGE))`, then `createPermission(myclient.getId(), clientsType, Set.of(VIEW), policyB)`, then admin A updates myclient. Expected success; I expect 403.

**4. services/src/main/java/org/keycloak/services/resources/admin/permissions/ClientPermissionsV2.java:148 (canExchangeTo) — Minor, error handling regression**
- **Claim:** With `token-exchange` (V1, preview) and `admin-fine-grained-authz:v2` both enabled, token exchange to a different audience now fails with a 500 instead of a clean 403.
- **Evidence:**
  - `AbstractTokenExchangeProvider:276` calls `AdminPermissions.management(...).clients().canExchangeTo(...)`. `management()` returns `MgmtPermissionsV2` when V2 is on.
  - Before the patch, `clients()` returned V1 `ClientPermissions`, which returned false (403). Now it throws `UnsupportedOperationException`.
  - `TOKEN_EXCHANGE` does not depend on FGAP V1 (Profile.java:76), so this combination is allowed.

**5. services/src/main/java/org/keycloak/services/resources/admin/permissions/ClientPermissionsV2.java:138-140 (getClientsWithPermission) — Minor, logic (latent)**
- **Claim:** The method returns wrong results.
  - `findByType(server, "Clients")` only finds the typed `Clients` resource, because per-client resources have no type. So specific clients are never returned.
  - When an all-clients permission grants the scope, it adds the literal string `"Clients"` instead of a client id.
- **Evidence:** The caller `AvailableRoleMappingResource:229-230` does `realm.getClientById(cid).getRolesStream()`, which would throw a NullPointerException on `"Clients"`. It can't happen today only because that branch is gated on the V1 feature (`!isFeatureEnabled(ADMIN_FINE_GRAINED_AUTHZ)`).

**6. services/src/main/java/org/keycloak/services/resources/admin/permissions/AdminPermissions.java:77 — Minor, orphaned data**
- **Claim:** The removal listener now runs only when FGAP V1 is on. Under V2, deleting a client leaves its per-client resource and the permissions that reference it in the admin-permissions resource server.
- **Evidence:** No V2 cleanup exists in `ClientApplicationSynchronizer`, which only deletes the client's own resource server and updates client policies.
- **Side effect:** Data left from a previous V1 enablement is also no longer cleaned up once V1 is turned off.
- **Note:** The gate itself is needed; without it, V2's `setPermissionsEnabled` would throw on every client delete.

**7. services/src/main/java/org/keycloak/services/resources/admin/permissions/ClientPermissionsV2.java:46, :51, :262-271 — Minor, dead code**
- The import of `TOKEN_EXCHANGE`, the `logger` field and the private `getEvaluationContext(...)` are never used.

**8. services/src/main/java/org/keycloak/services/resources/admin/permissions/ClientPermissionEvaluator.java:98, :103 — Minor, wrong documentation**
- The Javadoc on the void methods `requireView()` and `requireViewClientScopes()` says "Returns true if…". These methods throw `ForbiddenException`.

**Context, not changed by this patch:** `RolePermissions.checkAdminRoles` (RolePermissions.java:153-155) compares against `root.getRealmPermissionsClient()`. `MgmtPermissionsV2` overrides that to return the admin-permissions client, not `realm-management`. So the new V2-aware `clients().canManage()`/`canView()` calls inside it never run for real admin roles under V2. This makes finding 1 worse.

## Files not reviewed
OCR excluded these 5 test files from line-by-line review (`default_path`). I only grepped `PermissionClientTest` to see which scenarios it covers:
- tests/base/src/test/java/org/keycloak/tests/admin/authz/fgap/AbstractPermissionTest.java
- tests/base/src/test/java/org/keycloak/tests/admin/authz/fgap/PermissionClientTest.java
- tests/base/src/test/java/org/keycloak/tests/admin/authz/fgap/PermissionRESTTest.java
- tests/base/src/test/java/org/keycloak/tests/admin/authz/fgap/UserResourceTypeEvaluationTest.java
- tests/base/src/test/java/org/keycloak/tests/admin/authz/fgap/UserResourceTypePermissionTest.java

Coverage: 10 files in total, 5 reviewed, 5 skipped (50%).

I did not check whether the code compiles, and no spec was provided. Findings 1 and 2 are the ones to settle before merge.
