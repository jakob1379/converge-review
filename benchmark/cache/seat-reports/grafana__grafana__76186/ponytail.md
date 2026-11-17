What this change does: It splits the old `InstrumentationMiddleware` in two. The metrics part is renamed `MetricsMiddleware`. A new `ContextualLoggerMiddleware` attaches plugin/request attributes (endpoint, pluginId, dsName, dsUID, uname) to the request context. `LoggerMiddleware` stops building those attributes itself and reads them through a new `FromContext` method on the `plog.Logger` interface. The tracing log provider in `pkg/infra/tracing/tracing.go:91` already supplies `traceID`, so `LoggerMiddleware` drops its own copy too.

Assumed load: Grafana server, every plugin request goes through this middleware chain. I only looked for over-engineering. Nothing reaches Critical or Important. Net effect: the change deletes duplicated attribute-building from `LoggerMiddleware`, which is good.

**Findings**

1. **Dead fallback branch in the wrapper** — `pkg/plugins/log/logger.go:48-56` (the `!ok` branch is L50-52). Severity: Minor.
   - Claim: The type assertion `d.l.FromContext(ctx).(*log.ConcreteLogger)` cannot fail, so `if !ok { return d.New() }` never runs.
   - Evidence: `ConcreteLogger.FromContext` (`pkg/infra/log/log.go:203-217`) returns either `cl` or `cl.New(args...)`, and both are `*ConcreteLogger`. Simpler: `return &grafanaInfraLogWrapper{l: d.l.FromContext(ctx).(*log.ConcreteLogger)}`, which saves about 3 lines. A better fix is to make infra `FromContext` return `*ConcreteLogger`, but that is out of scope. This is reasoned; I ran no test.

2. **Test fake drops logs written through `FromContext`** — `pkg/plugins/log/fake.go:46-48`. Severity: Minor.
   - Claim: `TestLogger.FromContext` returns `NewTestLogger()`, a fresh logger. Anything logged through it, such as `LoggerMiddleware`'s "Plugin Request Completed", never reaches the `TestLogger` the test is holding. `return f` is shorter and keeps assertions working.
   - Evidence: The only production caller is `logger_middleware.go:58`, which logs only through `FromContext`. No current test wires a `TestLogger` into `LoggerMiddleware` (grep found none), so nothing fails today. This is reasoned.

3. **Unrelated `interface{}` → `any` churn** — `pkg/plugins/log/ifaces.go:9-39`. Severity: Minor.
   - Claim: About 15 of the lines this file changes only swap `interface{}` for `any` in `Logger` and `PrettyLogger`. That has nothing to do with the feature and inflates the diff.
   - Evidence: The diff for this file. Harmless, but it should be its own commit or be dropped.

4. **Copy-pasted doc comment on the new interface method** — `pkg/plugins/log/ifaces.go:22`. Severity: Minor.
   - Claim: The comment on `FromContext` is a copy of the comment on `New` ("…plus the given context"). It does not say the attributes come from the `context.Context` log providers.
   - Evidence: Compare L6 and L22.

Checked and not reported:
- `ContextualLoggerMiddleware` being a separate middleware is justified. `NewLoggerMiddleware` returns `next` when `cfg.PluginLogBackendRequests` is false, so the attributes must be added somewhere that always runs.
- The three pass-through stream methods are needed to satisfy the interface. Every other middleware in this package writes them out the same way.
- Moving `instrumentContext` into the new file is a move, not duplication.
- The `imw` local name left in `NewMetricsMiddleware` (`metrics_middleware.go:77`) and the test function still called `TestInstrumentationMiddleware` (`metrics_middleware_test.go:21`) are leftover names. They are naming nits, not over-engineering.

Verdict: Ship. Lean: about -3 lines possible (finding 1), plus about 15 churn lines (finding 3) that could move to a separate commit.

**Unreviewed files:** None. I read all 8 files in the patch:
- `pkg/plugins/log/fake.go`
- `pkg/plugins/log/ifaces.go`
- `pkg/plugins/log/logger.go`
- `pkg/services/pluginsintegration/clientmiddleware/contextual_logger_middleware.go`
- `pkg/services/pluginsintegration/clientmiddleware/logger_middleware.go`
- `pkg/services/pluginsintegration/clientmiddleware/metrics_middleware.go` (renamed)
- `pkg/services/pluginsintegration/clientmiddleware/metrics_middleware_test.go` (renamed)
- `pkg/services/pluginsintegration/pluginsintegration.go`

Not checked: I ran no builds or tests, as instructed. The new `ContextualLoggerMiddleware` has no test, but that is a test-coverage gap, not over-engineering, so it is outside my scope.
