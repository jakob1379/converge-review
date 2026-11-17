I reviewed this with ponytail:ponytail-review, as the advisory seat on over-engineering only. I read the patch, the code around it, and the callers: pkg/server/wire.go, impl.go, api.go, sqlstore/session.go, and a grep of the frontend. I ran no builds and no tests.

What this change does: It adds a setting, `[auth.anonymous] device_limit`. When the limit is set and that many devices were active in the last 30 days, new anonymous devices are refused at login and known devices only get their timestamps updated. It also makes device tagging synchronous (it used to run in a goroutine) and sends the limit to the frontend.

## Findings (over-engineering / lean)

1. **pkg/server/wire.go:374-375 — Important — Dead wiring left behind (reasoned; wire not run)**
   - **Claim:** `ProvideAnonymousDeviceService` now builds its own store (impl.go:43, `anonstore.ProvideAnonDBStore(sqlStore, cfg.AnonymousDeviceLimit)`). Nothing in OSS asks for `anonstore.AnonStore` any more. Yet wire.go still registers `anonstore.ProvideAnonDBStore` and the `AnonStore` bind.
   - **Evidence:** Grep of non-test `pkg/` code for `anonstore.AnonStore` finds only impl.go:32 (a struct field) and api.go:28/36, which gets the store passed in from impl.go. The provider now needs an `int64`, and no wire provider supplies one.
   - **Risk:** If anything (for example enterprise wiring) still injects `AnonStore`, wire generation fails with "no provider found for int64". If nothing does, these two lines are dead.
   - **Fix:** Pick one of two:
     - (a) Delete wire.go:374-375 and keep the construction inside the service.
     - (b) Smaller and closer to the codebase's DI pattern: change the signature to `ProvideAnonDBStore(sqlStore db.DB, cfg *setting.Cfg)`, keep wire, and drop the signature change to `ProvideAnonymousDeviceService` (plus the edits it forced in impl_test.go).
   - **Not checked:** whether wire actually errors on an unresolvable input in an unused provider, and enterprise injectors.

2. **pkg/services/anonymous/anonimpl/anonstore/database.go:16, pkg/services/anonymous/anonimpl/api/api.go:18, pkg/services/anonymous/anonimpl/impl.go:25 — Minor — The 30-day window now has three copies**
   - **Claim:** The commit says it "refactored const to make it clearer with expiration". It renamed api.go's `thirtyDays`, added a new private copy in anonstore, and left `thirtyDays` in impl.go (used at impl.go:70 for usage stats).
   - **Evidence:** All three are `30 * 24 * time.Hour` and must change together. If the limit window drifts from the listing or stats window, the count shown in the UI no longer matches the count that is enforced.
   - **Fix:** Export one `anonstore.AnonymousDeviceExpiration` and use it in api.go and impl.go. That is -2 const declarations.

3. **packages/grafana-data/src/types/config.ts:200, packages/grafana-runtime/src/config.ts:97, pkg/api/dtos/frontend_settings.go:195, pkg/api/frontendsettings.go:198 — Minor — The setting is sent to the frontend but never read there**
   - **Claim:** `anonymousDeviceLimit` is added to the DTO and both TS config types, but nothing reads it.
   - **Evidence:** `grep -rn anonymousDeviceLimit public packages` hits only the two declarations.
   - **Extra mismatch:** The TS type is `number | undefined`, but Go always serializes an `int64` (0 when unset), so `undefined` can never arrive.
   - **Fix:** Drop all four lines until a UI needs the value (-4 lines). If it stays, type it `number` with default `0`.

4. **pkg/services/anonymous/anonimpl/anonstore/database.go:84 — Minor (lean, and also a latent bug) — The query is prepended inside the retry callback**
   - **Claim:** `args = append([]interface{}{query}, args...)` mutates the captured `args` inside the `WithDbSession` callback.
   - **Evidence:** `WithDbSession` retries the callback on SQLite "database locked" (sqlstore/session.go:83-102). On a retry the query is prepended again, so `Exec` gets `[query, query, ...]` and fails.
   - **Context:** This copies the existing pattern at database.go:150, so the pre-existing code has the same issue.
   - **Fix:** `dbSession.Exec(append([]any{query}, args...)...)`. That is one line, the mutation goes away, and it fixes the retry case. Using a single `args := []any{query, ...}` from the start works too.

5. **pkg/services/anonymous/anonimpl/anonstore/database.go:72 — Minor — The doc comment describes a parameter that does not exist**
   - **Claim:** "updated between the given times" — no times are given. The window comes from `device.UpdatedAt` ±(30d, 1m).
   - **Fix:** Fix the comment or delete it. The repo's standard is no comments unless they explain why.

6. **pkg/setting/setting.go:1649-1654 — Minor — Unrelated refactor mixed into the feature**
   - **Claim:** Pulling out an `anonSection` local rewrites four untouched lines to add one. It is harmless churn and makes the diff and blame noisier.
   - **Fix:** Optional: add only the `device_limit` line in the existing style.

## Outside my lane (for the bug/correctness seats, not verified by test)

- **The limit only blocks the first request — reasoned.** impl.go:87 writes the device into `localCache` before `CreateOrUpdateDevice` at impl.go:93. When the limit is hit, `Authenticate` rejects that request. But for the next 29 minutes, `TagDevice` returns nil from the cache path, so the same refused device gets in.
  - The new store test (`TestIntegrationBeyondDeviceLimit`) calls the store directly, so it cannot catch this. A test that calls `Anonymous.Authenticate` twice for an over-limit device would expect an error both times and get success on the second.
- **Every anonymous login now waits on database calls.** On a cache miss with a limit set, that is a COUNT plus an insert or update, run synchronously; before this change it ran in a goroutine. Worth a look from the load seat.

## Files skipped

None. All 11 files in the patch were reviewed. The two test files (database_test.go, impl_test.go) were read only for signature fallout and lean issues, not judged for coverage.

Verdict (advisory): fix 1 before merge, because the wire state is either broken or dead. 2–6 are cleanup.
Lean: about -8 lines possible (2 wire lines, 4 frontend-config lines, 2 duplicate consts).
Not checked: wire generation, enterprise injectors, and nothing was built or run.
