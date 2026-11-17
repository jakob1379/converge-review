I reviewed the patch myself after loading `superpowers:requesting-code-review` and did not dispatch a subagent. There was no spec, so I reviewed against correctness and the tests. I ran no builds or tests, as instructed. The failing-test claims below are reasoned from the code and not confirmed by running them.

The repro tests are in `<bench>/work/grafana__grafana__103633.scratch/seat-sp/denial_cache_repro_test.go`. To run them, copy the file into `pkg/services/authz/rbac/` and run `go test ./pkg/services/authz/rbac/ -run TestRepro`. On the patched code I expect both tests to fail at the final `require.True`.

## Findings

**1. pkg/services/authz/rbac/service.go:116 (key built in pkg/services/authz/rbac/cache.go:30). Important.**
- **Claim:** The denial cache key leaves out the identity type. Anonymous and the render service both use UID "0", so once anonymous is denied a resource, the render service is also denied that resource for `shortCacheTTL` (30s).
- **Evidence:**
  - `userPermDenialCacheKey(ns, checkReq.UserUID, action, name, parent)` contains no `IdentityType`.
  - Anonymous identities use `ID: "0"` (`pkg/services/anonymous/anonimpl/client.go:114`).
  - Render-service identities also use `ID: "0"` (`pkg/services/authn/clients/render.go:44-50`).
  - So `anonymous:0` and `render:0` produce the same key, `org-N.perm_0_dashboards:read_<name>_<parent>`.
  - Check reads the denial cache (service.go:117) before `getIdentityPermissions`. The renderer's `{"*": true}` grant (`getRendererPermissions`) is therefore never reached.
- **Impact:** Image rendering, reports and alert screenshots of dashboards that anonymous cannot see fail closed for 30s after any anonymous hit.
- **Failing test:** `TestRepro_AnonymousDenialBlocksRenderer`. It runs Check as `anonymous:0` (denied), then as `render:0` on the same dashboard. The second call returns `Allowed=false`; it should be `true`.

**2. pkg/services/authz/rbac/cache.go:30. Important.**
- **Claim:** The denial key joins name and parent with `_`. Dashboard and folder UIDs may contain `_`, so different (name, parent) pairs map to the same key. A denial for one resource then denies a different resource the user is entitled to.
- **Evidence:**
  - Allowed UID characters are `a-zA-Z0-9\-\_` (`pkg/util/shortid_generator.go:33`).
  - (name `x_y`, parent `""`) and (name `x`, parent `y_`) both produce `..._x_y_`.
- **Failing test:** `TestRepro_DenialKeyCollision`. The user has `dashboards:uid:x`. Check on `x_y` is denied and cached. Check on `x` in folder `y_` then returns `Allowed=false`; it should be `true`.
- **Smaller related issue:** Denial keys share the `.perm_<uid>_` prefix with `userPermCacheKey` in the same underlying cache. I found no realistic collision because actions contain `:`, but the namespaces are not separated.

**3. pkg/services/authz/rbac/service.go:123-140 and :370-385 (cache read removed from `getUserPermissions`). Important, reasoned.**
- **Claim:** Every denial now costs a permission-store query, even when the cached permissions are fresh.
- **Evidence:**
  - Before: a user's permission map was cached for 30s, and denials within that window cost no queries.
  - After: when the cached map does not grant the resource, Check calls `getIdentityPermissions`. `getUserPermissions` and `getAnonymousPermissions` no longer read `permCache`, so each call runs `permissionStore.GetUserPermissions`.
  - The denial cache only stops repeats of the same (name, parent). singleflight only merges concurrent calls with the same user and action.
- **Impact:** A user denied N distinct dashboards causes N database queries per 30s where there used to be 1. Anonymous traffic is affected the same way.
- **Note:** This may be the intended trade-off (fresh grants show up immediately on the first check). It is still a load regression under deny-heavy patterns and should be decided explicitly. No test covers it.

**4. pkg/services/authz/rbac/service_test.go:973-995. Minor.**
- **Claim:** "Should deny on explicit cache deny entry" does not prove that the denial cache short-circuits Check.
- **Evidence:**
  - The comment at :981 says "Allow access to the dashboard", but the seeded map is `{"dashboards:uid:dash1": false}`. `checkPermission` reads `scopeMap[...]`, so that value denies.
  - Fallback to `setupService()`'s empty fakeStore would also deny.
  - The test therefore passes even with the denial-cache read deleted.
  - Fix: seed `true`, or assert `store.calls == 0`.

**5. pkg/services/authz/rbac/service_test.go:333-395 (`TestService_getUserPermissions`). Minor.**
- **Claim:** The only `cacheHit: true` case was removed, so the `if tc.cacheHit` branches at about lines 367 and 388 are now dead.
- **Gap:** Nothing asserts the new contract that `getIdentityPermissions` always goes to the store.
- **Gap:** Nothing tests the removed anonymous cache read.

## Not flagged
- The `pkg/services/authz/rbac.go` changes:
  - The in-process client now uses `NoopCache` instead of a 30s client-side cache, which is consistent with moving caching to the server.
  - The remote client keeps its local cache.
  - The `grpc` import is still used, at line 149.
  - `NoopCache` is a new exported type with unused params. That is a style point, so I did not raise it.
- Metric changes: `permissionCacheUsage` moved from `getUserPermissions` into Check and List. A hit on cached permissions that denies is counted as a miss. That is debatable, but I did not count it as a defect.

## Unreviewed files
None. I reviewed all four files in the patch: `pkg/services/authz/rbac.go`, `pkg/services/authz/rbac/cache.go`, `pkg/services/authz/rbac/service.go` and `pkg/services/authz/rbac/service_test.go`.

I did not check the authlib module source, because the module cache is not available. That means I could not confirm whether authlib already ships a no-op cache, or how its client-side cache treats denied Check results on the remote path.
