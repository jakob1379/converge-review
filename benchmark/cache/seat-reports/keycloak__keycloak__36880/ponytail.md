## Over-engineering review: keycloak PR 36880 (patch at 1950a511)

**What the change does:** It adds a "Clients" resource type with six scopes (configure, manage, map-roles, map-roles-client-scope, map-roles-composite, view) to the FGAP v2 admin permission schema. It adds `ClientPermissionsV2`, which `MgmtPermissionsV2.clients()` returns. It also moves the policy and permission test helpers into `AbstractPermissionTest` and adds `PermissionClientTest` cases.

I looked only at over-engineering. Nothing was run (benchmark mode). Every claim below comes from reading the code. Line numbers are in the patched files.

### Findings

1. **Unused method, field and imports in ClientPermissionsV2** — Important
   - Where: `services/src/main/java/org/keycloak/services/resources/admin/permissions/ClientPermissionsV2.java`, L262-272. The unused imports and field are at L22, L23, L27, L29, L46 and L51.
   - Claim: `private EvaluationContext getEvaluationContext(...)` is never called. It looks copied from V1's `canExchangeTo`, which V2 turns off (it throws `UnsupportedOperationException`). Because of it, the class also imports `ClientModelIdentity`, `DefaultEvaluationContext` and `EvaluationContext`. Three more things are unused even with it: `Scope`, the static `TOKEN_EXCHANGE` import and the `logger` field.
   - Evidence: `grep -c getEvaluationContext ClientPermissionsV2.java` returns 1, which is only the declaration. `logger`, `TOKEN_EXCHANGE` and the `Scope` import each appear once, also only at the declaration.
   - Fix: delete them all, about 18 lines. Behavior does not change.

2. **The same "evaluate and match scope" loop is written three times, and one copy duplicates the parent class** — Important
   - Where: `ClientPermissionsV2.java` L207-235 `hasPermission(ClientModel, String)`, L237-260 `hasPermission(String)`, and L274-286 `hasGrantedPermission(Resource, String)`.
   - Claim, part 1: `hasGrantedPermission` is identical to the parent's `private boolean hasPermission(Resource resource, String scope)` at `ClientPermissions.java:689`. Making the parent's method `protected` removes it.
   - Claim, part 2: the two `hasPermission` overloads repeat the same evaluate-and-loop body.
     - `hasPermission(String)` only differs by looking up the type resource with `resourceStore.findByName(server, CLIENTS_RESOURCE_TYPE, ...)`. That is what `AdminPermissionsSchema.SCHEMA.getResourceTypeResource(...)` already returns, and the other overload already calls it.
     - `UserPermissionsV2.hasPermission(UserModel user, EvaluationContext, String... scopes)` handles both cases with one method: `user == null` falls back to the type resource.
     - The ClientModel overload should copy that: `hasPermission(ClientModel client, String... scopes)`, with `null` meaning all clients.
   - Claim, part 3: with a varargs signature, `canView(ClientScopeModel)` at L121 becomes `hasPermission(null, VIEW, MANAGE)`, so one call instead of two. `Arrays.asList(scope)` on a single string, followed by `contains`, is just `scope.equals(s)`.
   - Fix: about 30 fewer lines, and one place to fix the scope-matching logic later.

3. **Methods that already exist on the parent class are written out again** — Minor
   - Where: `ClientPermissionsV2.java` L66, L106-110 and L119.
   - Claim: `root.hasOneAdminRole(AdminRoles.MANAGE_CLIENTS)` is the parent's `canManageClientsDefault()`. `hasOneAdminRole(VIEW_CLIENTS, MANAGE_CLIENTS)` is `canViewClientDefault()`. The V2 class already uses `canViewClientDefault()` at L86 but not at L119.
   - Claim: `canManageClientScopes()` (L106-110) has the same body as `canManage()` (`super.canManage() || hasPermission(MANAGE)`), so it can be `return canManage();`.
   - Fix: reuse the existing helpers. Saves about 3 lines.

4. **Test helpers made static only to take `client` and `realm` arguments the base class already holds** — Minor
   - Where: `tests/base/src/test/java/org/keycloak/tests/admin/authz/fgap/AbstractPermissionTest.java` L54, L62, L66, L70, L117, L121, L136 and L151.
   - Claim: `getPermissionsResource`, `getScopePermissionsResource`, `createPermission`, `createUserPolicy` and `createAllPermission` became `static (ManagedClient client, ...)` or `static (ManagedRealm realm, ManagedClient client, ...)`.
     - Every caller passes the inherited `client` and `realm` fields (L48-52). No caller is static and none passes a different client.
     - The change forced about 40 call-site edits in `PermissionRESTTest`, `UserResourceTypePermissionTest` and `UserResourceTypeEvaluationTest`, and every new call in `PermissionClientTest` repeats `realm, client`.
     - The class is also inconsistent: the new `createPermission(ManagedClient, String resourceId, ...)` overloads at L163 and L167 are instance methods that still take `client`.
   - Fix: keep them as instance methods that use the fields. The `PermissionRESTTest` and `UserResourceTypePermissionTest` diffs then shrink to nothing.

5. **`createClientPolicy` is never used** — Minor
   - Where: `AbstractPermissionTest.java` L136-149.
   - Claim: no test calls it.
   - Evidence: `grep -rn createClientPolicy tests/base/src/test/java/org/keycloak/tests/admin/authz/fgap` matches only the declaration.
   - Fix: delete it, about 15 lines.

6. **A one-line feature guard re-indents the whole event listener** — Minor
   - Where: `services/src/main/java/org/keycloak/services/resources/admin/permissions/AdminPermissions.java` L77-97.
   - Claim: wrapping the listener body in `if (Profile.isFeatureEnabled(ADMIN_FINE_GRAINED_AUTHZ)) { ... }` re-indents and reformats about 18 lines that do not change.
   - Fix: an early `if (!Profile.isFeatureEnabled(Profile.Feature.ADMIN_FINE_GRAINED_AUTHZ)) return;` gives the same result with a one-line diff.

7. **MgmtPermissionsV2 adds a field that hides an inherited one** — Minor
   - Where: `services/src/main/java/org/keycloak/services/resources/admin/permissions/MgmtPermissionsV2.java` L29.
   - Claim: the parent already declares `protected ClientPermissions clientPermissions` (`MgmtPermissions.java:76`). The new `private ClientPermissionsV2 clientPermissions` hides it, so two fields now hold the same cache.
   - Fix: delete L29 and assign to the inherited field. This copies the existing `userPermissions` pattern, which has the same problem, so it is low priority.

8. **Two Javadoc comments say "Returns true" on methods that return nothing** — Minor
   - Where: `services/src/main/java/org/keycloak/services/resources/admin/permissions/ClientPermissionEvaluator.java` L95-98 (`requireView`) and L100-103 (`requireViewClientScopes`).
   - Claim: both methods are `void` and throw `ForbiddenException`. The comment should say "Throws ForbiddenException if ...", like every other `require*` comment in the file.

9. **Whitespace noise in AdminPermissionsSchema** — Minor
   - Where: `server-spi-private/src/main/java/org/keycloak/authorization/AdminPermissionsSchema.java` L53.
   - Claim: an empty line was replaced with a line holding four spaces. The diff gains a line of trailing whitespace and nothing else.

### Outside my focus, not checked further
`ClientPermissionsV2.hasPermission(ClientModel, String)` skips the `permission.getResourceId().equals(resource.getId())` check that `UserPermissionsV2` does. It also passes the result of `getResourceTypeResource` straight to `findByResource` without a null check, and that method can return null. Worth a look from the correctness seat.

**Verdict:** fix 1 and 2 first; the rest are cleanup.
**Lean:** about 70 lines can be removed (1: about 18, 2: about 30, 3: about 3, 5: about 15, plus the re-indent in 6). Fixing 4 also removes about 40 lines of call-site churn.

### Files not reviewed
None. All 10 files in the patch were read. For `PermissionClientTest.java` and `UserResourceTypeEvaluationTest.java`, I checked only the helper usage and leftover dead code, not whether each test scenario is correct, since that is outside the over-engineering focus.

**Not checked:** nothing was compiled or run. Findings 1 and 5 are confirmed by grep. The rest are reasoned from reading the code.
