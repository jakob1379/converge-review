## Code review: PR head 1950a51102 vs base b7b84d75d1, spec and documented-standards axes only

I loaded `mattpocock-skills:code-review` and did both axes myself, with no sub-agents. Nothing was built or run, so every claim below is reasoned from the source.

**Assumptions**
- There is no spec. The spec axis checks the code against the PR's stated intent: "Add Client resource type and its scopes to authorization schema and evaluation implementation for ClientPermissionsV2".
- Standards sources used: `CONTRIBUTING.md`, `PR-CHECKLIST.md`, `docs/tests-development.md`, `tests/MIGRATING_TESTS.md` and `.editorconfig`.
- The commit message meets `CONTRIBUTING.md`: it has `Closes #35564` and a `Signed-off-by` line.

## Spec (internal consistency with the stated intent)

**1. `services/src/main/java/org/keycloak/services/resources/admin/permissions/AdminPermissions.java:77` — Important (reasoned)**
- **Claim:** The whole removal listener (roles, clients and groups) now runs only when the v1 flag `ADMIN_FINE_GRAINED_AUTHZ` is on. The PR's intent only needed one thing: skip the clients branch under v2, because `ClientPermissionsV2.setPermissionsEnabled` throws `UnsupportedOperationException` (`ClientPermissionsV2.java:193`).
- **Effect:** Behaviour changes for every deployment where v1 is off, including deployments with fine-grained admin permissions turned off entirely. Before this patch, deleting a role, client or group always called `setPermissionsEnabled(..., false)` to clean up leftover v1 permission resources and policies. That cleanup now never runs.
- **Under v2:** Deleting a client now triggers no cleanup at all. The new per-client resource (named by the client's UUID) and its scope permissions stay behind and point at a client that no longer exists.
- **Evidence:** The old code (`git show b7b84d75d1:.../AdminPermissions.java`, lines 74-93) had no gate. `Profile.java:56/58` defines v1 and v2 as versions of the same feature, so they are never on together and this gate means "only under v1".
- **Standards breached:** `PR-CHECKLIST.md` ("does not contain changes not relevant") and `CONTRIBUTING.md` ("No changes to code not directly related").
- **Narrower fix:** Gate on `!ADMIN_FINE_GRAINED_AUTHZ_V2`, or only around the `ClientRemovedEvent` branch.

**2. `services/src/main/java/org/keycloak/services/resources/admin/permissions/ClientPermissionsV2.java:138-140` — Minor (reasoned; the bug can't be reached today)**
- **Claim:** `getClientsWithPermission` can never return client IDs.
- **Why:**
  - Per-client resources are created by `AdminPermissionsSchema.getOrCreateResource`, which calls `resourceStore.create(...)` and never sets a type (`AdminPermissionsSchema.java:~102`).
  - `findByType(server, "Clients", ...)` therefore matches only the all-clients resource built in `init()`, the only place that sets a type (`AdminPermissionsSchema.java:~249`).
  - So the method returns either an empty set or the set `{"Clients"}`.
- **Consequence:** The only caller, `rest/admin-ui-ext/.../AvailableRoleMappingResource.java:229-230`, would hit a null pointer on `realm.getClientById("Clients").getRolesStream()`. That caller is only reached when the v1 flag is on, so under v2 the bug is latent. The override still does not implement what it claims to.

**3. `services/src/main/java/org/keycloak/services/resources/admin/permissions/ClientPermissionsV2.java:207-235` — Minor (reasoned)**
- **Claim:** `hasPermission(ClientModel, String)` departs from the existing v2 pattern it copies.
- **Evidence:** `UserPermissionsV2.java:135` only accepts permissions where `permission.getResourceId().equals(resource.getId())`. The client version accepts a granted scope from any returned permission. The client and user resource types now evaluate differently, and nothing in the PR explains why.

**4. `server-spi-private/src/main/java/org/keycloak/authorization/AdminPermissionsSchema.java:73` (with `:227` `init` and `ClientPermissionsV2.java:217-219`) — Minor (the feature is EXPERIMENTAL, `Profile.java:58`)**
- **Claim:** The schema gained a new resource type and three new scopes, but there is no upgrade path for realms that already have an admin-permissions client.
- **Evidence:**
  - `init()` returns early when the client already exists. Its only callers are `JpaClientProviderFactory.java:73` and `RealmManager.java:572`, so the `Clients` resource and the `configure`, `map-roles-client-scope` and `map-roles-composite` scopes never get created in those realms.
  - In such a realm, creating a Clients permission fails in `getScope` with "Scope [configure] does not exist".
  - `getResourceTypeResource` returns null, and `ClientPermissionsV2.java:219` then passes null into `findByResource(server, null)`, which reads `resource.getId()` (`JPAPolicyStore.java:215`). The admin gets a 500 instead of a 403.
  - The same null pointer also happens when realm admin permissions are switched off after the client was created, because `supportsAuthorizationSchema` returns false.

**5. `server-spi-private/src/main/java/org/keycloak/authorization/AdminPermissionsSchema.java:310` — Minor**
- **Claim:** `getResourceName` handles only the Users type: "All users" for the all-users resource, otherwise the username. Clients resources fall through to `resource.getDisplayName()`, which is never set for resources made by `getOrCreateResource`. Permission listings therefore show no name for client resources. The schema extension is incomplete here.

**6. `services/src/main/java/org/keycloak/services/resources/admin/permissions/ClientPermissionEvaluator.java:95-103` — Minor**
- **Claim:** The new Javadoc on the `void` methods `requireView()` and `requireViewClientScopes()` says "Returns {@code true} if…". It should say "Throws ForbiddenException if…", as the other `require*` docs added in the same hunk do.

**7. `services/src/main/java/org/keycloak/services/resources/admin/permissions/ClientPermissionEvaluator.java:~150-189` — Minor**
- **Claim:** The new Javadoc misdescribes v2 in two ways:
  - **"Also":** On `canManage(ClientModel)`, `canConfigure`, `canView(ClientModel)`, `canMapRoles`, `canMapCompositeRoles` and `canMapClientScopeRoles` it says "For V2 only: Also if … for all clients", implying an addition to the v1 check. For the three `canMap*` methods (`ClientPermissionsV2.java:91-103`), v2 replaces the v1 per-client check with `hasPermission` alone.
  - **"all clients":** v2 also honours per-client grants, and `PermissionClientTest#testMapRolesAndCompositesOnlyOneClient` and `#testManageOnlyOneClient` depend on that.

**8. `services/src/main/java/org/keycloak/services/resources/admin/permissions/ClientPermissionsV2.java:46, 51, 262-272` — Minor**
- **Claim:** The new class carries token-exchange code that is never used: the `TOKEN_EXCHANGE` import, a `logger`, and the private `getEvaluationContext(ClientModel, AccessToken)`. That contradicts its own `canExchangeTo`, which throws "Not supported in V2". Copied v1 code was left in.

## Standards (documented)

**9. `tests/base/src/test/java/org/keycloak/tests/admin/authz/fgap/PermissionClientTest.java:25` — Minor (a clear breach)**
- **Claim:** The file uses `import static org.junit.Assert.fail;`, which is JUnit 4.
- **Breaches:**
  - `tests/MIGRATING_TESTS.md:24,31` maps `org.junit.Assert` to `org.junit.jupiter.api.Assertions`.
  - `docs/tests-development.md:29` says "Please avoid … `org.junit.Assert.*`".
- **Inconsistency:** The same file uses JUnit 5's `Assertions.assertEquals`, and the sibling `UserResourceTypeEvaluationTest.java:25` uses `org.junit.jupiter.api.Assertions.fail`.

**10. `server-spi-private/src/main/java/org/keycloak/authorization/AdminPermissionsSchema.java:53`; `services/src/main/java/org/keycloak/services/resources/admin/permissions/AdminPermissions.java:78-95` — Minor**
- **Claim:** Both contain formatting that isn't needed for the change. `CONTRIBUTING.md` says: "Do not format or refactor code that is not directly related to your contribution."
- **Details:**
  - At line 53, an empty line becomes a line of four trailing spaces.
  - In `AdminPermissions.java`, the cast spacing changes from `(X)event` to `(X) event`, on top of the re-indent the new gate requires.

**11. Documentation — Minor, noted but not pressed**
- `CONTRIBUTING.md` says "Includes documentation", and the patch adds no docs for the Clients resource type or its scopes.
- No v2 docs exist under `docs/documentation` for the existing Users type either (the only scope hit is the v1 page `fine-grain.adoc`). Leaving docs out for this EXPERIMENTAL feature matches what the project already does.

**Summary:**
- **Spec axis:** 8 findings. The worst is #1, the listener gate that changes cleanup for everyone not on v1.
- **Standards axis:** 3 findings. The worst is #9, the JUnit 4 `fail` import against the test docs.

## Files not reviewed

All 10 files in the patch were reviewed, two of them lightly:
- `tests/base/src/test/java/org/keycloak/tests/admin/authz/fgap/UserResourceTypeEvaluationTest.java`: past patch line ~1250 I read only the changed (+/-) lines. They are mechanical moves to the shared helpers in `AbstractPermissionTest`.
- `tests/base/src/test/java/org/keycloak/tests/admin/authz/fgap/UserResourceTypePermissionTest.java` and `.../PermissionRESTTest.java`: only call-site signature changes (`getScopePermissionsResource(client)`, `createPermission(client, …)`), checked for consistency only.

Not checked: whether the new tests pass (no build or test run, by benchmark rules). Fowler-style smells were left out as instructed.
