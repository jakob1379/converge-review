Review seat: ponytail:ponytail-review. My role was advisory, over-engineering only. I read the patch and the code around it. I did not run builds or tests.

**What this change does:** It removes the `go-duck` dependency (DuckDB, an embedded SQL engine) and its indirect modules. In its place it adds a stub type `sql.DB` whose methods all return "not implemented". It also adds a check in `ExpressionQueryReader.ReadQuery` that rejects SQL expressions.

Assumed load: a server feature that is turned off. Scale and speed are not relevant here.

**Should fix**

1. **A "feature flag check" that ignores the flag** (`pkg/expr/reader.go:129-132`, `pkg/expr/reader.go:194-200`). Severity: Important.
   - **What this is:** `enableSqlExpressions` reads `FlagSqlExpressions`, inverts it, branches on it, and returns `false` from both branches. It is 7 lines that always mean `false`.
   - **Problem:** It looks like the flag controls the feature. Turning `sqlExpressions` on still gives "sqlExpressions is not implemented". The gate is also redundant. The other entry path, `nodes.go:159` → `UnmarshalSQLCommand` → `NewSQLCommand` → `sql.TablesList`, is not gated and already fails on the stub `RunCommands`. That path returns the `sql-invalid-sql` BadRequest. So the gate covers one of two paths and adds nothing the stub does not already do.
   - **Fix:** Delete the helper and the gate (−12 lines). The stub already fails every SQL expression. If a clear message matters, return it once in shared code, at the top of `NewSQLCommand`, so both paths get it.
   - **If we skip it:** The next person to flip the flag will lose time debugging it. They will also find that only one of the two paths gives the clear message.
   - Evidence: this is reasoned from the code, with no failing test. Both branches are visible at `reader.go:195-199`. The ungated path is `nodes.go:159-160` → `sql_command.go:30`.

**Nice to have**

2. **Unused stub method** (`pkg/expr/sql/db.go:12-14`). Severity: Minor.
   - **What this is:** The stub copies the go-duck API, including a `DB.TablesList` method.
   - **Problem:** Nothing calls it. `parser.go:22` calls the package-level `sql.TablesList`. Grep finds no `db.TablesList` caller.
   - **Fix:** Delete the method (−4 lines). `RunCommands` and `QueryFramesInto` stay, because `parser.go:26` and `sql_command.go:100` use them.
   - **If we skip it:** Readers get one more dead stub to wonder about.

The stub approach itself is fine. It keeps the parser and command code ready to put back with a small diff, and every test in `pkg/expr/sql/parser_test.go` (16) and `sql_command_test.go` (1) already calls `t.Skip()`.

Verdict: Ship after 1. Leaving it in is misleading, but it causes no runtime harm.
Lean: −16 lines possible.

Files reviewed: `pkg/expr/reader.go`, `pkg/expr/sql/db.go`, `pkg/expr/sql/parser.go`, `pkg/expr/sql_command.go`, and `go.mod` (only to confirm that `go-duck` and its indirect deps are removed and no `.go` file still imports `go-duck`).

Not reviewed:
- `go.sum` and `go.work.sum`: generated checksum lists (from `make update-workspace`). Over-engineering does not apply, and I could not check them without running `go mod tidy` or `verify`, which benchmark mode forbids.

Not checked: whether `go build` / `go mod tidy` is clean after the dependency removal. Builds were not allowed.
