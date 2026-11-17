I reviewed 7 of the 8 files in the patch and found no Critical or Important issues. The only bigger change is the refactor that moves the contextual-logger code into its own middleware, and in production the code paths behave the same as before. There are two Minor findings. I didn't build or run any tests, so everything below is reasoned from the code.

**How I checked the production path**
- **Field parity:** At the base, the logger middleware wrote `pluginId`, `endpoint`, `uname`, `dsName`, `dsUID` and `traceID` into "Plugin Request Completed" itself. Now it calls `m.logger.FromContext(ctx).Info(...)` (`logger_middleware.go:58`), which picks up the same fields from the context:
  - The plugin fields come from `ContextualLoggerMiddleware` through `log.WithContextualAttributes`. The provider that reads them back is registered in `pkg/infra/log/log.go:55`.
  - `traceID` comes from the provider registered in `pkg/infra/tracing/tracing.go:91`, under the same key.
  - No key is logged twice.
- **Middleware order:** `client.NewDecorator` reverses the list (`pkg/plugins/manager/client/decorator.go:106`), so the first entry is the outermost. The order in `pluginsintegration.go:158-161` is therefore Tracing → Metrics → ContextualLogger → Logger. The span exists before `traceID` is read, and the attributes are set before the logger middleware runs.
- **Type assertion:** In `pkg/plugins/log/logger.go:49`, `ConcreteLogger.FromContext` (`pkg/infra/log/log.go:203-217`) only ever returns `cl` or `cl.New(...)`, both `*ConcreteLogger`. The assertion always succeeds, so the `d.New()` fallback can't be reached.
- **Interface change:** Adding `FromContext` to `plog.Logger` doesn't leave any implementer in the repo uncompiled. The only implementers are `grafanaInfraLogWrapper` and `TestLogger`, and both got the method.
- **Old function name:** `NewInstrumentationMiddleware` has no callers left in the repo.

**Findings**

1. `pkg/plugins/log/fake.go:46` — **Minor**
   - **Claim:** `TestLogger.FromContext` returns a new, empty `NewTestLogger()` instead of `f`. Anything logged through `logger.FromContext(ctx).Info(...)` never reaches the fake the test injected.
   - **Effect:** The logger middleware now logs only this way. A test that passes `plog.NewTestLogger()` to `NewLoggerMiddleware` will always see `InfoLogs.Calls == 0`, whatever the middleware does.
   - **Evidence:** No test exercises this today; grep finds no test that uses `LoggerMiddleware`. So it's a trap for the next test, not a current failure. Returning `f` fixes it.

2. `pkg/services/pluginsintegration/clientmiddleware/logger_middleware.go:49-58` — **Minor**
   - **Claim:** `LoggerMiddleware` used to get its request fields from `req.PluginContext` itself. Now it depends on `ContextualLoggerMiddleware` sitting above it in the chain, and on `tracing.ProvideService` having registered the `traceID` provider globally. Neither dependency is written down, and no test covers either.
   - **Effect:** If someone reorders `CreateMiddlewares` or builds the chain without the contextual middleware, the egress log silently loses `pluginId`, `endpoint`, `uname` and `dsUID`. Nothing fails.
   - **Evidence:**
     - `CreateMiddlewares` (`pluginsintegration.go:156-187`) is the only place in this repo that builds the chain.
     - The patch adds no test for `ContextualLoggerMiddleware` or for the fields in the log line.
     - The renamed `metrics_middleware_test.go` doesn't test the context attributes, and didn't at the base either.
   - **Status:** Reasoned, no failing command.

**Not raised:** The append-to-a-shared-slice behaviour in `log.WithContextualAttributes` (`pkg/infra/log/log.go:285-291`) is older code outside the patch. The patch only moves its caller, so it's not a regression.

**Unreviewed files**
- `pkg/services/pluginsintegration/clientmiddleware/metrics_middleware_test.go` — OCR excluded it from review (default path rule). I read its diff anyway: it's a one-line rename of the constructor call. The test function is still called `TestInstrumentationMiddleware`, which is cosmetic only.

Coverage: 7 of 8 files reviewed (87.5%).
