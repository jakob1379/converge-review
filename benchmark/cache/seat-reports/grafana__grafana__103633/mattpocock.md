I ran both axes of `mattpocock-skills:code-review` myself, with no sub-agents.
- **Fixed point:** base 5634ca44f7. HEAD is 7562f37880, a merge commit on branch `gabriel-ieva/improve-authz-caching`.
- **Under review:** only the patch file. Line numbers below are for the PR-head files.
- **Standards sources I read:** CONTRIBUTING.md, contribute/backend/style-guide.md, contribute/backend/recommended-practices.md and contribute/backend/instrumentation.md. The style guide adopts Effective Go and Go Code Review Comments by reference.
- **Not present:** the repo has no AGENTS.md or CLAUDE.md.
- **Smell baseline:** I left it out because you asked for no generic code smells.

## Spec
This axis could not run because there is no spec. I found no issue reference in the commits and none was supplied. So I cannot report missing requirements, scope creep or wrongly built requirements.

## Standards
All four are Minor. None is Critical or Important, so I have no failing command to give.

1. **pkg/services/authz/rbac.go:241, 245, 249 — Minor.**
   - **Claim:** The new `NoopCache` methods use the receiver name `lc`, which is the abbreviation of `LocalCache`, not of `NoopCache`.
   - **Evidence:** style-guide.md adopts Go Code Review Comments, whose "Receiver Names" rule says a receiver name should reflect its type. It should be `nc`, or dropped since it is unused.
   - **Suppressed on purpose:** I did not flag the missing doc comment on the exported `NoopCache`. recommended-practices.md #1 says Grafana's documentation does not enforce public declarations, and that overrides the Code Review Comments doc-comment rule.

2. **pkg/services/authz/rbac/service.go:126 — Minor.**
   - **Claim:** The new log line `ctxLogger.Error("could not check permission", ...)` starts with a lowercase letter.
   - **Evidence:** instrumentation.md, Logs → Naming conventions: "Start the log message with a capital letter." The same message already exists lower down, but this is a newly added line.

3. **pkg/services/authz/rbac/service.go:181-191 (List) and 123-136 (Check) — Minor, judgement call.**
   - **Claim:** The normal path is indented and errors fall into `else` or fall-through: `if err == nil { ...hit... } else { ...fallback... }`.
   - **Claim, continued:** Any error from `getCachedIdentityPermissions` is treated as a cache miss without being looked at. That includes a `GetUserIdentifiers` store error and the "unsupported identity type" error, not only `cache.ErrNotFound`.
   - **Evidence:** Go Code Review Comments, "Indent Error Flow" and "Handle Errors", adopted via style-guide.md. Nothing is lost at runtime: the fallback `getIdentityPermissions` gets the same error again and logs it. But only `errors.Is(err, cache.ErrNotFound)` should mean "miss".

4. **pkg/services/authz/rbac/service_test.go:973-990 — Minor.**
   - **Claim:** The test "Should deny on explicit cache deny entry" does not prove the denial cache is used.
   - **Evidence:** The comment on line 981 says "Allow access to the dashboard to prove this is not checked", but the cached permission is set to `{"dashboards:uid:dash1": false}`, not `true`. In `checkPermission` (service.go:558) a `false` value means not allowed. The `fakeStore` from `setupService` has no permissions, so `Check` returns `Allowed: false` with no error even if the denial-cache lookup is deleted.
   - **Why it matters:** style-guide.md (Testing) says code should be "covered by unit tests", and this test does not cover what it claims to.
   - **Status:** Reasoned; I did not run it. To confirm: delete service.go:116-121 and run `go test ./pkg/services/authz/rbac -run 'TestService_CacheCheck/Should_deny'`. I expect it still passes.

## Outside this seat's axes (flagged, not ranked)
- **pkg/services/authz/rbac/cache.go:30**
  - **Problem:** `userPermDenialCacheKey` joins `name` and `parent` with `_`. Dashboard and folder UIDs can contain `_`, so name `a`, folder `b_c` and name `a_b`, folder `c` produce the same key.
  - **Effect:** A cached denial for one resource wrongly denies the other for `shortCacheTTL`. It fails closed, so access is wrongly refused, not wrongly granted.
  - **Status:** Reasoned, not run.
- **pkg/services/authz/rbac.go:101-105**
  - **Change:** The in-process client now uses `NoopCache` instead of a 30s `LocalCache`. That is a deliberate behaviour change: caching moves into the service.
  - **Not checked:** No spec states the intent, so I cannot check it against one.

## Unreviewed files
None. I reviewed all four files in the patch: pkg/services/authz/rbac.go, pkg/services/authz/rbac/cache.go, pkg/services/authz/rbac/service.go and pkg/services/authz/rbac/service_test.go.

## Summary
- **Spec:** 0 findings; the axis could not run without a spec.
- **Standards:** 4 findings, all Minor. The worst is #4, the denial-cache test that cannot fail.

I did not check whether authlib already ships a no-op `cache.Cache`, because the module cache was not reachable. Per your instructions I ran no build or test, so every claim is reasoned, not executed.
