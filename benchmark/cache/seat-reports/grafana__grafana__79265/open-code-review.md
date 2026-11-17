I reviewed the patch through `open-code-review:delegate-review` in range mode (`ocr delegate preview --from 7ddcd0c --to HEAD`, then `ocr delegate rule`). OCR listed 11 files and excluded the 2 test files by default path; I read both anyway. I ran no build or test, as instructed, so every finding below is reasoned rather than executed. I edited no files.

## Findings

1. **pkg/services/anonymous/anonimpl/impl.go:87-95 — Critical — Only the first rejected request is blocked.**
   - **Claim:** A device turned away for being over the limit is let through on every request after the first, for 29 minutes.
   - **Evidence:**
     - `tagDeviceUI` writes the cache entry (`a.localCache.SetDefault(key, ...)`, line 87) before it calls `CreateOrUpdateDevice` (line 93).
     - When the store returns `ErrDeviceLimitReached`, the entry stays. The cache is created with `localcache.New(29*time.Minute, ...)` and the key is just the device ID (`CacheKey()`).
     - On the next request from that device, `tagDeviceUI` finds the key at line 84 and returns nil. `TagDevice` then returns nil, and `client.go:44` returns an anonymous identity.
     - The only test of the limit, `TestIntegrationBeyondDeviceLimit`, calls the store directly and never goes through the cache.
   - **Test that should fail on the patched code (not run):** in `impl_test.go`, build the service with `cfg := setting.NewCfg(); cfg.AnonymousDeviceLimit = 1`. Call `TagDevice` for a request with `X-Grafana-Device-Id: a`, then twice for device `b`. Assert both calls for `b` return `ErrDeviceLimitReached`. The second call returns nil.

2. **pkg/services/anonymous/anonimpl/impl.go:119-128 and client.go:44 — Important — The limit can be skipped by leaving out one header.**
   - **Claim:** A client that does not send `X-Grafana-Device-Id` is never counted against the limit.
   - **Evidence:**
     - `TagDevice` returns nil straight away when the header is empty (line 121). It also returns nil when the IP cannot be parsed (line 128).
     - `Authenticate` then returns the anonymous identity, so any client that drops the header gets full anonymous access no matter how many devices exist.
     - If `device_limit` is meant as access control (the commit says "break auth if limit reached"), this undoes it. If it is only for counting, it should not fail auth at all.

3. **pkg/services/anonymous/anonimpl/anonstore/database.go:108-117 — Important — Concurrent new devices can push the count past the limit.**
   - **Claim:** The count and the insert are not atomic.
   - **Evidence:**
     - `CountDevices` runs in one session. The upsert runs later in another session, with no transaction or lock.
     - N new devices arriving at once can all see `count < limit` and all be inserted.
     - It gets worse across HA instances, because each instance has its own local cache.
     - This used to be harmless because tagging was async and only counted. Now it decides auth, so the limit is soft. It needs a transactional or `INSERT ... SELECT WHERE (SELECT COUNT) < limit` check, or the limit should be documented as approximate.

4. **pkg/services/anonymous/anonimpl/client.go:44 — Important (performance on the auth path) — Device tagging now runs inside every anonymous request.**
   - **Claim:** Requests now wait on tagging database work, and the panic guard is gone.
   - **Evidence:**
     - The goroutine with `context.WithTimeout(context.Background(), 2m)` and `recover()` was replaced by a synchronous call that uses the request context.
     - When a device is not cached, the request now waits on the upsert, plus a `COUNT(*)` over `anon_device` when `deviceLimit > 0`.
     - This happens even when `device_limit = 0`, where nothing is gained. Anonymous request latency now depends on the database.
     - Requests the client cancels now abort the tag write too (minor).

5. **pkg/server/wire.go:374-375 (not in the patch, but broken by it) — Important (reasoned, not run because builds were forbidden) — A dependency-injection (wire) entry no longer fits.**
   - **Claim:** wire.go still registers `anonstore.ProvideAnonDBStore` and the `AnonStore` binding, but the signature is now `ProvideAnonDBStore(sqlStore db.DB, deviceLimit int64)`.
   - **Evidence:**
     - No wire provider supplies a bare `int64`.
     - Nothing in OSS consumes `anonstore.AnonStore` any more, because `ProvideAnonymousDeviceService` now builds the store itself. The binding is dead.
     - Any consumer that resolves `AnonStore` through wire (for example Enterprise) would fail to generate, or would get a store without the limit.
     - Whether `wire gen` fails on an unused provider with an unprovidable argument is unverified. Run `make gen-go` to confirm.

6. **pkg/services/anonymous/anonimpl/client.go:45 — Minor — The error is untyped, which affects logging and the HTTP status.**
   - `ErrDeviceLimitReached` is a plain `fmt.Errorf` value, not an `errutil` error.
   - `authnimpl.errorLogFunc` therefore logs it at Warn on every rejected request (log spam under load).
   - The contexthandler only stores it in `LookupTokenErr`, so the client gets a generic 401 with no explanation that a device limit was hit.

7. **packages/grafana-runtime/src/config.ts:97 — Minor — The TS type and the value the server sends do not match.**
   - `anonymousDeviceLimit = undefined;` has no type annotation, so TypeScript infers the type `undefined` on `GrafanaBootConfig`. Code reading `config.anonymousDeviceLimit` cannot treat it as a number.
   - The server always sends an `int64`, with 0 meaning unlimited, so the value is never `undefined`.

8. **pkg/api/frontendsettings.go:198 — Minor — The limit is sent to all clients, including unauthenticated ones.**
   - `AnonymousDeviceLimit` is included in the frontend settings, and anonymous clients receive those too.
   - That is a small information leak (license or tier sizing). Confirm it is intended.

9. **pkg/setting/setting.go:1654 — Minor (documented-standard breach) — The new setting is not documented.**
   - `device_limit` was added under `[auth.anonymous]` without an entry in `conf/defaults.ini` or `conf/sample.ini`, or in the configuration docs.
   - Grafana's convention is that every ini key exists in `defaults.ini`. Nowhere is it stated that 0 means unlimited.

10. **anonstore/database.go:14, api/api.go:18, impl.go (`thirtyDays`) — Minor — The 30-day window is defined in three places.**
    - The store's limit count, the API list and the usage-stats count must agree.
    - The patch adds a second constant in `api.go` instead of sharing the store's.

## Files skipped
None. All 11 files were reviewed. OCR excluded `anonstore/database_test.go` and `anonimpl/impl_test.go` by default path, and I reviewed them manually. Their only gap is that no test covers the cache bypass in finding 1.

Coverage: 11 files in total, 11 reviewed, 0 skipped, 100%.

Not checked: whether wire generation actually fails (finding 5), since builds were off-limits. Biggest risk: finding 1 makes the device limit block only one request per device every 29 minutes, so the feature does not enforce what it claims.
