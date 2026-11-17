I reviewed the patch directly, using the review criteria from superpowers:requesting-code-review, and did not dispatch a subagent. There was no spec, so I took the intent from the branch name `rename-instrumentation-middleware` and the commit "Removed traceID from logParams": rename InstrumentationMiddleware to MetricsMiddleware, move the contextual-logger work into its own middleware, and have LoggerMiddleware pick up its plugin, request and trace fields from the context. The patch does that.

I found no Critical or Important issues. The behaviour checks I made:
- **Order:** in `client/decorator.go`, `clientFromMiddlewares` reverses the list, so the first middleware is the outermost. The new order is Tracing → Metrics → ContextualLogger → Logger. LoggerMiddleware still receives the enriched context, and so does everything below it.
- **traceID:** it is still logged. `tracing.ProvideService` registers a log provider (`pkg/infra/tracing/tracing.go:91`) that calls the same `TraceIDFromContext(ctx, false)` the removed code called.
- **New interface method:** `ConcreteLogger.FromContext` always returns `*ConcreteLogger`, so the type assertion in the wrapper always succeeds.
- **Other implementations:** the only implementations of the `plog.Logger` interface are `grafanaInfraLogWrapper` and `TestLogger`, and the patch updates both. Nothing outside the repo should break.
- **Leftover references:** no code still refers to `NewInstrumentationMiddleware` or `newInstrumentationMiddleware`.

Nothing was built or run (as instructed), and `gofmt` is not installed here, so there are no failing commands to report.

## Findings

1. **`pkg/services/pluginsintegration/clientmiddleware/contextual_logger_middleware.go:1-69`**: Minor (missing test)
   - **Claim:** this new middleware has no test, and nothing tests LoggerMiddleware's output either. The refactor moves the `pluginId`, `endpoint`, `dsName`, `dsUID`, `uname` and `traceID` fields of the `grafana-data-egress` log line to a different component, and no test pins them.
   - **Evidence:** there is no `contextual_logger_middleware_test.go` or `logger_middleware_test.go` in the clientmiddleware directory. `metrics_middleware_test.go` never checks the context or logs.
   - Under the user's testing rules, the right test is a contract test: run the stack from `CreateMiddlewares` and check the fields on the "Plugin Request Completed" log line.

2. **`pkg/plugins/log/fake.go:46-48`**: Minor (test fake)
   - **Claim:** `TestLogger.FromContext` returns a new, empty `TestLogger`. LoggerMiddleware now logs only through `m.logger.FromContext(ctx)` (`logger_middleware.go:58`). A test that gives LoggerMiddleware a `TestLogger` will therefore always see `InfoLogs.Calls == 0`, so the fake can't be used to test this middleware.
   - **Evidence:** the code reads `return NewTestLogger()`. Returning `f` would keep logs observable.
   - This copies the existing behaviour of `TestLogger.New`, so it is not a regression, but it is the reason finding 1 can't be tested with this fake.

3. **`pkg/services/pluginsintegration/clientmiddleware/logger_middleware.go:49-58`**: Minor (hidden ordering dependency)
   - **Claim:** LoggerMiddleware no longer adds the plugin and request fields itself. It now gets them only if ContextualLoggerMiddleware runs before it. Used alone, or placed above it, the egress log loses `pluginId`, `endpoint`, `uname` and the datasource fields, with no error.
   - **Evidence:** `pluginsintegration.go:159-160` is the only place that wires it, and the order there is correct. Nothing documents or enforces the dependency, either in the docs for `NewLoggerMiddleware` or in a test.
   - The key order in the log line also changes: the context fields now come before `status`/`duration`. That matters only if something downstream parses the egress log by position.

4. **`pkg/plugins/log/logger.go:49-52`**: Minor
   - **Claim:** the `!ok` fallback (`return d.New()`) can never run. `infra/log.ConcreteLogger.FromContext` only ever returns `cl` or `cl.New(...)`, both `*ConcreteLogger` (`pkg/infra/log/log.go:203-217`).
   - It is harmless, but if it ever did run it would silently drop the context fields.

5. **`pkg/services/pluginsintegration/clientmiddleware/metrics_middleware_test.go:21`**: Minor
   - **Claim:** the file and type were renamed to Metrics, but the test function is still called `TestInstrumentationMiddleware`. The rename is incomplete.

6. **`pkg/services/pluginsintegration/clientmiddleware/contextual_logger_middleware.go:26`**: Minor
   - **Claim:** the helper is still named `instrumentContext`, which was the old instrumentation-middleware wording. Out of context the name reads as a metrics or tracing function.

7. **`pkg/plugins/log/ifaces.go:22`**: Minor (doc accuracy)
   - **Claim:** the doc comment on `FromContext` was copied from `New` and says "plus the given context". The method actually adds attributes pulled from a `context.Context` through the registered log providers, not key/value context.

## Files not reviewed

None. I reviewed all 8 files in the patch:
- `pkg/plugins/log/fake.go`
- `pkg/plugins/log/ifaces.go`
- `pkg/plugins/log/logger.go`
- `pkg/services/pluginsintegration/clientmiddleware/contextual_logger_middleware.go`
- `pkg/services/pluginsintegration/clientmiddleware/logger_middleware.go`
- `pkg/services/pluginsintegration/clientmiddleware/metrics_middleware.go`
- `pkg/services/pluginsintegration/clientmiddleware/metrics_middleware_test.go`
- `pkg/services/pluginsintegration/pluginsintegration.go`

Because there was no spec, I could not check the patch against stated requirements. The main risk is untested behaviour: the fields on the egress log line now depend on middleware order, and no test covers them.
