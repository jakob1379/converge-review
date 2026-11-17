Review of `change.patch` (base 58ba11ecbd, head 303cdc2caf). I ran the `mattpocock-skills:code-review` process myself and did not spawn sub-agents. You told me to leave generic code smells out, so I did not apply the skill's Fowler smell baseline. Every finding below is tied to a repo document. Nothing was built or run, so every claim is reasoned from the code.

The standards sources I checked:
- `contribute/backend/style-guide.md`, which also brings in Go's Code Review Comments, plus `.golangci.toml` for what tooling enforces.
- `contribute/backend/instrumentation.md`, the Logs and Contextual logging sections.
- `CONTRIBUTING.md`.
- There is no `AGENTS.md` or `CODING_STANDARDS.md` in the repo.

## Standards

1. **pkg/services/pluginsintegration/clientmiddleware/logger_middleware.go:49-58 and pkg/services/pluginsintegration/clientmiddleware/contextual_logger_middleware.go:14-69 — Important (reasoned, no failing command)**
   - **Claim:** The "Plugin Request Completed" (`grafana-data-egress`) log line used to set `pluginId`, `endpoint`, `uname`, `dsName`, `dsUID` and `traceID` itself. Now it only gets them through `m.logger.FromContext(ctx)`. That works only if `NewContextualLoggerMiddleware()` sits earlier in the chain, which today is `pluginsintegration.go:160`. None of this has a test:
     - the new `ContextualLoggerMiddleware`
     - the changed `LoggerMiddleware` output
     - `grafanaInfraLogWrapper.FromContext` (`pkg/plugins/log/logger.go:48-56`)
     - the ordering in `CreateMiddlewares`

     If someone reorders or drops that middleware, those fields vanish from the log line and no test fails.
   - **Standard:** `contribute/backend/style-guide.md:28` says "We value clean and readable code, that is loosely coupled and covered by unit tests." This change adds coupling that depends on middleware order, and leaves it uncovered.
   - **Evidence:**
     - No `logger_middleware_test.go` or `contextual_logger_middleware_test.go` exists in `clientmiddleware/`.
     - The base `instrumentation_middleware_test.go` never asserted on contextual log attributes either, so no existing coverage moved over.
     - `TestLogger.FromContext` (`pkg/plugins/log/fake.go:46-47`) returns a fresh `NewTestLogger()`. A test that uses the fake therefore can't see anything logged through `FromContext`.
     - The old comment saying the middleware "should live at the top of the middleware stack" was deleted from `metrics_middleware.go`. No ordering note was added to the new middleware to replace it.
   - **Mitigating:** the patch does follow `instrumentation.md`'s "Contextual logging" section, which says to use `logger.FromContext(ctx)`. `traceID` should still appear, because `pkg/infra/tracing/tracing.go:91` registers a contextual log provider for it.

2. **pkg/services/pluginsintegration/clientmiddleware/contextual_logger_middleware.go:22 — Minor**
   - **Claim:** The exported type `ContextualLoggerMiddleware` and its exported methods (lines 39-67) have no doc comments.
   - **Standard:** `contribute/backend/style-guide.md:8` adopts Go Code Review Comments, whose "Doc Comments" rule is that all top-level exported names should have doc comments.
   - **Evidence:** The constructor at line 12 has a doc comment and the type does not. The renamed `MetricsMiddleware` keeps its type doc comment, so the new file is less documented than its neighbour.

3. **pkg/services/pluginsintegration/clientmiddleware/logger_middleware.go:53 — Minor (the key is older than this patch, but the patch rewrote the block it sits in)**
   - **Claim:** The log key `time_before_plugin_request` is snake_case.
   - **Standard:** `contribute/backend/instrumentation.md`, Logs → Naming conventions: "Prefer using camelCase style when naming log keys."
   - **Evidence:** It sits in the `logParams` literal the patch rewrote, next to camelCase keys (`eventName`, and `pluginId` / `dsName` / `dsUID` coming from the contextual middleware). Renaming it would change emitted log output, so it may belong in a separate change.

4. **pkg/services/pluginsintegration/clientmiddleware/metrics_middleware_test.go:21 and pkg/services/pluginsintegration/clientmiddleware/metrics_middleware.go:77-80 — Minor**
   - **Claim:** The rename from Instrumentation to Metrics is incomplete. The test is still `func TestInstrumentationMiddleware`, and the local variable is still `imw`.
   - **Standard:** Go Code Review Comments, adopted via `style-guide.md:8`, on names. This is a judgement call, not a hard breach.
   - **Evidence:** Shown by the `grep` output above. The logger name `log.New("plugin.instrumentation")` at `pluginsintegration.go:161` was rightly left alone, because it is the key users match in `[log] filters`.

What I checked and found fine:
- **Imports:** the new import grouping in `logger_middleware.go` and `contextual_logger_middleware.go` matches the repo's goimports setup in `.golangci.toml`.
- **`any` instead of `interface{}`:** the swap in `ifaces.go` is mechanical.
- **Other implementers:** the only implementations of `plog.Logger` are `grafanaInfraLogWrapper` and `TestLogger`, and the patch updates both. The `logWrapper` types in `coreplugin` and `grpcplugin` wrap `plog.Logger` rather than implement it.
- **Type assertion:** `d.l.FromContext(ctx).(*log.ConcreteLogger)` always succeeds, because `ConcreteLogger.FromContext` returns either `cl` or `cl.New(...)`, both `*ConcreteLogger`. The fallback branch can't be reached.

## Spec

No spec was provided, and none could be found:
- No issue reference in the commits.
- No spec file in `docs/`, `specs/` or `.scratch/`.

The Spec axis did not run. The commit messages are the only statement of intent ("Renamed instrumentation middleware to metrics middleware", "Add contextual logger middleware", "Removed traceID from logParams"). The diff matches them, apart from the leftover names in Standards finding 4.

## Unreviewed files

None. I reviewed all 8 files in the patch:
- `pkg/plugins/log/fake.go`
- `pkg/plugins/log/ifaces.go`
- `pkg/plugins/log/logger.go`
- `pkg/services/pluginsintegration/clientmiddleware/contextual_logger_middleware.go`
- `pkg/services/pluginsintegration/clientmiddleware/logger_middleware.go`
- `pkg/services/pluginsintegration/clientmiddleware/metrics_middleware.go` (renamed from `instrumentation_middleware.go`)
- `pkg/services/pluginsintegration/clientmiddleware/metrics_middleware_test.go` (renamed from `instrumentation_middleware_test.go`)
- `pkg/services/pluginsintegration/pluginsintegration.go`

## Axes that could not run

- **Spec:** no spec source.
- **Standards:** fully run against the documented sources, without the smell baseline.

**Summary:** Standards has 4 findings (1 Important, 3 Minor); the worst is that `LoggerMiddleware` now silently depends on middleware order for its log fields, with no test. Spec has 0 findings because it did not run.

I did not compile or run tests, so whether the patch builds, and whether `golangci-lint` reports things like the missing doc comments, is unconfirmed.
