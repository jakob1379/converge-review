What this change does: It changes how the RBAC authz service caches permissions. `Check` now reads cached permissions first and returns early only when they allow access. On a cached deny or a cache miss it goes back to the database, and it stores database-confirmed denials in a new per-resource denial cache (`permDenialCache`). `List` uses the same cache-first lookup. The in-process authz client now gets a no-op cache, so it no longer adds its own 30s client-side cache on top of the server's.

Seat: over-engineering only. Assumed load: a multi-tenant server where Check runs on every request, so the denial cache is a real load concern and not speculative. I don't count it as over-engineering.

**Findings (all Minor; no Critical or Important)**

1. `pkg/services/authz/rbac/service.go:342-368`, Minor (lean/merge)
   - Claim: `getCachedIdentityPermissions` returns an `error` that both callers use only as a hit/miss flag. It also copies the identity-type `switch` from `getIdentityPermissions` (lines 320-340).
   - Evidence: It returns the sentinel `cache.ErrNotFound` three times (lines 352, 354, 364). Both callers (`Check` at line 123, `List` at line 180) only test `err == nil` and never read the error; real errors are thrown away and come back later from `getIdentityPermissions`. Adding a new identity type now means editing two switches.
   - Fix: Return `(map[string]bool, bool)` like `cacheWrap.Get`. Drop the `TypeRenderService` arm and let `default` return a miss, since any miss falls through to the database path anyway. About -6 lines, no sentinel errors. Reasoned, not run.

2. `pkg/services/authz/rbac/service_test.go:337-390` (`TestService_getUserPermissions`), Minor (dead code)
   - Claim: The patch deletes the only `cacheHit: true` case, so the `cacheHit` field and both `if tc.cacheHit` branches can no longer run.
   - Evidence: The remaining cases at lines 347 and 353 both set `cacheHit: false`. The `permCache.Set` branch (~line 367) and the `store.calls == 1` branch (~line 388) never execute.
   - Fix: Remove the field and both branches, and always assert `store.calls == 3`. About -8 lines.

3. `pkg/services/authz/rbac.go:239-251` (`NoopCache`), Minor (yagni/visibility)
   - Claim: A new exported type is added to the public `authz` package but used at only one call site in the same package (line 103).
   - Evidence: `grep -rn NoopCache pkg` finds only the definition and that one use.
   - Fix: Unexport it as `noopCache` and drop the unused receiver names. Not checked: whether `authlib` (v0.0.0-20250325095148-d6da9c164a7d) already ships a no-op cache, or skips caching when no cache option is given. If either holds, this type can be deleted outright (-13 lines). The module isn't in a local module cache, so I couldn't look.

4. `pkg/services/authz/rbac.go:160-170` (`newRemoteRBACClient`), Minor (lean)
   - Claim: `client := authzlib.NewClient(...)` followed by `return client, nil` is a temporary variable with no purpose.
   - Fix: `return authzlib.NewClient(...), nil`. -2 lines.

Outside this seat (one line, not an over-engineering finding): `userPermDenialCacheKey` at `pkg/services/authz/rbac/cache.go:30-32` joins `name` and `parent` with `_`, and UIDs may contain `_`. (name=`x_y`, parent=`z`) and (name=`x`, parent=`y_z`) produce the same key, so a cached denial can wrongly deny a different resource for up to `shortCacheTTL` (30s). It fails closed, so it can't grant access, but it can block a user who should get in. Reasoned, not run.

Verdict: Ship. Nothing here blocks on over-engineering grounds.
Lean: about -16 lines possible (-29 if authlib already provides a no-op cache).
Not checked: the authlib source (module not available offline). Nothing was built or run, per instructions.

**Unreviewed files:** None. All four files in the patch were reviewed: `pkg/services/authz/rbac.go`, `pkg/services/authz/rbac/cache.go`, `pkg/services/authz/rbac/service.go` and `pkg/services/authz/rbac/service_test.go`.
