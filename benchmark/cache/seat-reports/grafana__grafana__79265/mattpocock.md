Code-review report for grafana PR 79265 (base 7ddcd0c96, head bbd8c507cd). My seat was advisory: spec compliance and documented standards only.

How I ran it: I invoked `mattpocock-skills:code-review`. You told me not to spawn agents, so I did the Standards axis myself instead of using the skill's parallel sub-agents.
- **Spec axis:** skipped. There is no spec, and none of the 5 commit messages references an issue.
- **Standards sources:** `CONTRIBUTING.md`, `contribute/create-pull-request.md`, `contribute/backend/{style-guide,services,errors,recommended-practices}.md`, `contribute/developer-guide.md`, `contribute/style-guides/frontend.md`, plus the skill's code-smell baseline. There is no `AGENTS.md`.
- **Verification:** none of the claims below was run. You said not to build or test, so every Important finding is reasoned from the source, with a command given where one would show it.

## Standards findings

1. **`pkg/setting/setting.go:1654`, Important (breach of a documented rule).**
   - **Claim:** the patch adds a new config key, `[auth.anonymous] device_limit`, but the config files and docs the repo requires to change with it were not touched.
   - **Evidence:** `contribute/create-pull-request.md`, "Configuration changes", says: "If your PR includes configuration changes, all of the following files must be changed correspondingly: conf/defaults.ini, conf/sample.ini, docs/sources/administration/configuration.md".
   - None of those files is in the patch. `grep -rn device_limit conf docs` returns nothing. `conf/defaults.ini:581-592` and `conf/sample.ini:581` list `enabled`, `org_name`, `org_role` and `hide_version`, but not `device_limit`.
   - **Command that shows it:** `grep -c device_limit conf/defaults.ini conf/sample.ini` returns 0 and 0.

2. **`pkg/services/anonymous/anonimpl/impl.go:43` together with `pkg/server/wire.go:374-375`, Important (reasoned).**
   - **Claim:** `ProvideAnonymousDeviceService` now builds `anonstore.ProvideAnonDBStore(sqlStore, cfg.AnonymousDeviceLimit)` itself instead of receiving `anonstore.AnonStore` through Wire. That works against `contribute/backend/services.md`, which says "Dependencies between components are represented in Wire as function parameters, encouraging explicit initialization".
   - **The stale registration:** `wire.go:374-375` still registers `anonstore.ProvideAnonDBStore` and binds `AnonStore` to it, even though that provider now takes an extra `int64` that nothing in the Wire graph provides.
   - **OSS impact:** no OSS consumer remains, so the registration is dead.
   - **Enterprise impact:** any consumer outside OSS that injects `AnonStore`/`*AnonDBStore` gets a second store that is not the one the service uses. Wire generation should also fail with "no provider found for int64".
   - **Check:** `make gen-go` (I did not run it).

3. **`pkg/services/anonymous/anonimpl/anonstore/database.go:18`, Minor (documented standard).**
   - **Claim:** `ErrDeviceLimitReached` is a plain `fmt.Errorf` value, and it now leaves the authn client as an authentication failure (`client.go:45-46`).
   - **Evidence:** `contribute/backend/errors.md` says services should declare their error categories with `errutil.<status>(messageID, ...)`, for example `errutil.Unauthorized` or `errutil.TooManyRequests`, so the HTTP status, log level and public message travel with the error. As written, the status and public message the user sees are left to the authn layer's default handling.

4. **`pkg/services/anonymous/anonimpl/anonstore/database_test.go:51`, Minor (documented standard).**
   - **Claim:** the new `TestIntegrationBeyondDeviceLimit` is missing the required `if testing.Short() { t.Skip(...) }` guard.
   - **Evidence:** `contribute/backend/style-guide.md`, "Integration Tests", says: "you must format your test function definition ... with the function name starting with `TestIntegration` and the check for `testing.Short()`", and warns the test "may be run twice or not run at all". The existing tests in this file and in `impl_test.go` also lack the guard; the new test copies that pattern rather than introducing it.

5. **`pkg/services/anonymous/anonimpl/anonstore/database.go:16` and `pkg/services/anonymous/anonimpl/api/api.go:18`, Minor (smell baseline, judgement call: possible Duplicated Code).**
   - **Claim:** commit 7af474db0b ("refactored const ...") turned `thirtyDays` into `anonymousDeviceExpiration` by defining the identical constant `30 * 24 * time.Hour` in two packages, instead of exporting it once from `anonstore` and reusing it.
   - **Risk:** the device-count window and the list-devices window can drift apart.

6. **`packages/grafana-data/src/types/config.ts:200` and `packages/grafana-runtime/src/config.ts:97`, Minor (smell baseline, judgement call: possible Speculative Generality).**
   - **Claim:** `anonymousDeviceLimit: number | undefined` is added to the public `GrafanaConfig` interface, but nothing in `public/` or `packages/` reads it.
   - **Type mismatch:** the backend DTO is a plain `int64` (`pkg/api/dtos/frontend_settings.go`, `json:"anonymousDeviceLimit"`), so it always serialises a number (0 when unset), never `undefined`.
   - **Breaking-change risk:** adding a required member to an exported interface in a published package also falls under `contribute/breaking-changes-guide/breaking-changes-guide.md`. Anything that implements `GrafanaConfig` would have to add the field.

## Spec
Skipped: no spec was provided, and no issue reference exists in the commits (6ccd33f7c4, 566e0a8f24, eb44d75dc7, 7af474db0b, bbd8c507cd).

**Summary:** Standards has 6 findings (2 Important, 4 Minor); the worst is that the new `device_limit` config is missing from `conf/defaults.ini`, `conf/sample.ini` and the docs. Spec has 0 findings because there is no spec.

## Files not reviewed
None skipped. All 11 files in the patch were reviewed against the documented standards. I did not review correctness or performance, which is outside this seat. One example of what that left unchecked: `Authenticate` now calls `TagDevice` synchronously with the request context, and when the limit is above 0 that adds a `CountDevices` query to every anonymous request whose device is not already in the local cache.

I did not run `make gen-go`, `make lint-go` or any tests, and I did not see Grafana Enterprise's wire files. Finding 2's claim that generation fails is therefore unconfirmed.
