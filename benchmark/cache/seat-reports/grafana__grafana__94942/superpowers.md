## Correctness review: grafana__grafana__94942 (cbe1e7d63f..f3317b329b)

**Scope:** The patch removes the `go-duck` dependency and replaces it with stubs in `pkg/expr/sql/db.go` that always return "not implemented". It also adds a hard gate on SQL expressions in `reader.go`. The net effect is that SQL expressions are disabled unconditionally. No spec was given, so I took the commit subject "disable sql expressions" as the intent.

**Verification limits:** Go is not installed here, and benchmark mode rules out builds, tests and installs. Every claim below is reasoned from the source, not from a failing run.

**Verdict:** The change does disable the feature. It compiles by inspection: `db.go` matches the method signatures that `parser.go` and `sql_command.go` call, and no `duck.` references remain anywhere in `pkg`. I found no Critical issues. The problems are a dead and misleading gate, inconsistent behaviour between the two parse paths, and leftover surfaces that still advertise the feature.

### Findings

**1. Important — `pkg/expr/reader.go:194-200` and `:129-132`: the gate ignores the feature flag, so the `sqlExpressions` flag no longer does anything.**
- `enableSqlExpressions` returns `false` on both branches.
- It also computes `enabled := !IsEnabledGlobally(FlagSqlExpressions)`. That variable name is inverted: it is true when the flag is off.
- Result: `QueryTypeSQL` always fails with `sqlExpressions is not implemented`, whatever the flag says.
- The flag is still registered as "Enables using SQL and DuckDB functions as Expressions." (`pkg/services/featuremgmt/registry.go:1083-1088`).
- The frontend still shows the SQL expression type when the flag is on (`public/app/features/expressions/types.ts:73`).
- Production risk: anyone running with `sqlExpressions` enabled still sees SQL expressions in the UI, but every query that uses one fails.
- If an unconditional kill is the intent, the function should simply return `false`, and the flag description and frontend gate should be updated. If the flag was meant to keep working, this is a logic bug.

**2. Minor — `pkg/expr/nodes.go:159-160` (path the patch doesn't change) together with `pkg/expr/sql_command.go:30-35`: the default path is disabled only by accident, and its error says the SQL is invalid.**
- The new gate sits only on the `ReadQuery` path, which is used when `FlagExpressionParser` is on (`nodes.go:124`).
- The legacy path, used by default, never checks the gate. It goes `UnmarshalSQLCommand` → `NewSQLCommand` → `sql.TablesList`. The stubbed `RunCommands` then fails, and that failure is turned into `errutil.BadRequest("sql-invalid-sql", "error reading SQL command")` plus a log line `Warn("invalid sql query")`.
- So users on the default path are told their SQL is invalid rather than that the feature is disabled.
- The disable depends on stub behaviour, not an explicit check, and the two paths return different errors for the same input.

**3. Minor — `pkg/expr/sql/db.go:9-26` and `pkg/expr/sql_command.go:96-104`: dead code is left in place.**
- `DB`, `TablesList`'s JSON/AST handling (`parser.go:32-80`) and `SQLCommand.Execute`'s query logic can no longer run. `NewSQLCommand` always fails first, so `Execute` is never reached.
- The stub is labelled "InMemoryDB" and the variable in `parser.go:23` is still named `duckDB`, which suggests a working backend exists.
- This only matters if the disable is meant to be permanent. If it is temporary until a new engine lands, it is acceptable.

**4. Minor — test gap.**
- No test was added to show that SQL expressions are rejected.
- All the existing SQL tests were already `t.Skip()`: `pkg/expr/sql/parser_test.go` and `pkg/expr/sql_command_test.go:9`. That means nothing exercises the new gate or the default-path error.
- Suggested contract test: a `NewExpressionQueryReader(featuremgmt.WithFeatures(featuremgmt.FlagSqlExpressions)).ReadQuery(...)` call with `type: "sql"` should return an error. Add the same check through `buildCMDNode` with the parser flag off, which would also pin down finding 2.

**5. Minor — schema and doc drift: the API still advertises a query type that always fails.**
- `pkg/expr/query.go:30` still says "SQL query via DuckDB".
- `pkg/expr/query.go:77` still says `SQLExpression` "requires the sqlExpression feature flag".
- The query schema `pkg/expr/query.types.json` still lists the `sql` type, so the generated schema advertises something that always fails.

### Dependency files

- **`go.mod`:** It drops `go-duck` and the indirect dependencies only it pulled in (thrift, `go-which`, `orderedmap`, `overflow`, `asmfmt`, `asm2plan9s`, `c2goasm`). That is consistent with `go mod tidy`.
- **`go.sum`:** The `h1:` lines are removed but the `/go.mod` lines are kept where other modules in the graph still list those modules. That is normal tidy output.
- **`go.work.sum`:** It gains the matching hashes, which is consistent with `make update-workspace`.
- **Other references:** No other `go.mod`, `.go` file, CI file or Makefile mentions `go-duck`. `CHANGELOG.md` mentions it only as history.
- **Not verified:** I could not run `go mod verify` or `go mod tidy -diff` without the Go toolchain.

### Files reviewed

All 7 files in the patch were reviewed:
- `pkg/expr/reader.go`
- `pkg/expr/sql/db.go`
- `pkg/expr/sql/parser.go`
- `pkg/expr/sql_command.go`
- `go.mod`
- `go.sum` and `go.work.sum`, reviewed for structure and consistency only. I did not check the hashes because no Go toolchain is available.

Not checked: whether anything compiles or any test passes, and the exact HTTP status the `ReadQuery` error maps to in `pkg/registry/apis/query`.
