## Correctness review: grafana__grafana__94942 (cbe1e7d63f..f3317b329b)

I ran the review through `open-code-review:delegate-review`. `ocr delegate preview --from cbe1e7d63f --to f3317b329b` listed 7 files, 4 of them reviewable. I applied the Go rule group from `ocr delegate rule`. Under benchmark mode I made no edits, ran no builds or tests, and installed nothing.

**What the patch does:** it removes `github.com/scottlepp/go-duck` (DuckDB). It replaces it with a stub `sql.DB` whose methods all return `errors.New("not implemented")`, and it adds a check in `ExpressionQueryReader.ReadQuery` that always rejects `QueryTypeSQL`. In effect, SQL expressions are turned off everywhere. I found nothing Critical or Important.

### Findings

**1. Minor: `pkg/expr/reader.go:194-200`. `enableSqlExpressions` always returns false, so the feature flag has no effect.**
- **Claim:** the function reads `FlagSqlExpressions` and then ignores it. Both branches `return false`, and the local `enabled` holds the opposite of what its name says (`!IsEnabledGlobally`).
- **Evidence:** the patch body is `enabled := !h.features.IsEnabledGlobally(...); if enabled { return false }; return false`.
- **Effect:** the `sqlExpressions` toggle is still registered at `pkg/services/featuremgmt/registry.go:1083` as "Enables using SQL and DuckDB functions as Expressions". The frontend also still offers the SQL expression type when the toggle is on (`public/app/features/expressions/types.ts:73`). An operator who turns the flag on gets a SQL option in the UI that the backend always rejects with "sqlExpressions is not implemented".
- **Assessment:** this matches the commit intent ("disable sql expressions"), so it is not a functional bug. The function is misleading dead logic, though. A plain `return false`, or deprecating the toggle and hiding it in the frontend, would be honest about the state.
- Reasoned; no failing test.

**2. Minor: the legacy parse path does not reach the new check and reports a misleading error.**
- **Where:** `pkg/expr/nodes.go:159` (unchanged), which leads to `pkg/expr/sql_command.go:30` and then `pkg/expr/sql/parser.go:23-29`.
- **Claim:** when `FlagExpressionParser` is off, SQL nodes skip `ReadQuery` and go to `UnmarshalSQLCommand`, then `NewSQLCommand`, then `sql.TablesList`. That now always fails in the stub `RunCommands`. The user gets `BadRequest "error reading SQL command"` instead of a "not implemented" message.
- **Side effect:** each such request logs `logger.Error("error serializing sql", ...)` and then `logger.Warn("invalid sql query", ...)`, both with the full raw SQL.
- **Impact:** nothing crashes and SQL is still blocked. The cost is a misleading user error and error-level log noise. On both paths, the reader check is the only thing that names the real cause.
- Reasoned.

**3. Minor: `pkg/expr/sql/db.go:12-14` and `pkg/expr/sql_command.go:96-104` contain dead code.**
- `DB.TablesList` has no callers; `parser.go` calls the package-level `TablesList`.
- In `SQLCommand.Execute`, `db.QueryFramesInto` can never succeed. It also cannot be reached, because `NewSQLCommand` already fails while building the command.
- This is harmless. I mention it only because the stub's API suggests a working DB.

### Other checks (no issue found)
- No `.go` file or nested `go.mod` still imports `go-duck` or any of the indirect modules the patch removed.
- `gotest.tools/v3` dropped its `h1:` hash from go.sum, but nothing imports it any more.
- The `pkg/registry/apis/query/testdata/with-expressions.json` fixture uses datasource type `"sql"` and not the SQL expression, so the new check does not affect it.
- The SQL tests in `pkg/expr/sql/parser_test.go` are all `t.Skip()`. The SQL entry in `query_test.go` is schema-only. No existing test exercises the disabled path, and no new test was added for the rejection.

### Coverage
- **Total:** 7 files. 4 reviewed, 3 skipped by OCR, so 57% by file count. All Go source in the patch was reviewed.
- **Reviewed:** `pkg/expr/reader.go`, `pkg/expr/sql/db.go`, `pkg/expr/sql/parser.go`, `pkg/expr/sql_command.go`.
- **Skipped by OCR (unsupported extension):** `go.mod`, `go.sum` and `go.work.sum`. I read their hunks by hand only to check that the removed modules have no remaining importers. I did not check hash correctness or `go mod tidy` consistency, because that needs the Go toolchain and running it is not allowed in benchmark mode.

### Not checked
- I did not confirm that the code compiles (`go build` / `go vet` not run).
- I did not check how the HTTP layer maps the plain `fmt.Errorf` from `ReadQuery` to a status code.
