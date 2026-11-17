## Code review: grafana__grafana__94942 (base cbe1e7d63f, HEAD f3317b329b)

I followed `mattpocock-skills:code-review` and did both axes myself, without sub-agents. Per benchmark mode, I ran no builds, tests or `go mod` commands. The fixed point resolves and the diff is not empty. It has two commits: `6e6ed73416 disable sql expressions` and `f3317b329b Run make update-workspace`.

I checked these standards sources: `contribute/backend/style-guide.md`, `contribute/backend/errors.md`, `contribute/feature-toggles.md`, `contribute/create-pull-request.md`, `contribute/UPGRADING_DEPENDENCIES.md` and `.golangci.toml`. The repo has no AGENTS.md or CLAUDE.md.

## Standards

1. **`pkg/expr/reader.go:194-200`, Important (breaks a documented standard).** The new feature-flag check can never return true.
   - The function reads the `sqlExpressions` flag, but both branches `return false`, so the flag's value is thrown away.
   - `contribute/feature-toggles.md` says to "wrap [your feature] around a check if the feature flag is enabled ... Use the `IsEnabled` function". This code makes the call and ignores what it returns.
   - The flag is still documented as "Enables using SQL and DuckDB functions as Expressions" in `pkg/services/featuremgmt/registry.go:1084` and `docs/sources/setup-grafana/configure-grafana/feature-toggles/index.md:187`. The frontend still shows the SQL expression option when the flag is on (`public/app/features/expressions/types.ts:73`).
   - Result: an admin who turns the flag on gets a UI option that every backend request rejects.
   - The double negation (`enabled := !IsEnabledGlobally(...)`) also makes the name `enabled` say the opposite of what it holds.
   - Evidence: reasoned, I did not run anything. This test would show it: build `NewExpressionQueryReader(featuremgmt.WithFeatures(featuremgmt.FlagSqlExpressions))`, call `ReadQuery` with `"type":"sql"`, and assert no error. It fails with "sqlExpressions is not implemented".
   - If the goal is to turn the feature off for good, that is a decision to state openly. The clear way is to remove or deprecate the toggle and the frontend option, not to keep a flag that does nothing.

2. **`pkg/expr/reader.go:131`, Important (breaks a documented standard).** The error users see is a plain `fmt.Errorf("sqlExpressions is not implemented")`.
   - `contribute/backend/errors.md` requires `errutil` errors declared with a `<service>.<id>` messageID. It lists `errutil.NotImplemented(messageID, opts...)`, which fits this case exactly.
   - A plain error loses the status code and the public message. The same file already follows the pattern: `sql_command.go:27` uses `errutil.BadRequest("sql-missing-query", ...)`.
   - The text is also misleading. The feature is disabled, not unimplemented, and the message names the toggle, which is an internal detail.
   - Evidence: reasoned.

3. **`pkg/expr/sql/db.go:1-26` and `pkg/expr/sql/parser.go:23`, Important (style guide: "clean and readable code ... covered by unit tests").** The stub `DB` returns `errors.New("not implemented")` from every method.
   - On the legacy path (`expressionParser` flag off), `nodes.go:160` → `UnmarshalSQLCommand` → `NewSQLCommand` → `TablesList` never reaches the new gate in reader.go.
   - Instead it logs `logger.Error("error serializing sql", ...)` with the user's raw SQL (`parser.go:28`) and returns `BadRequest "error reading SQL command"`.
   - So the "disable" is carried out two different ways, and they give the user different errors. There is no test for either.
   - Evidence: reasoned. I traced `nodes.go:123-161`.

4. **`pkg/expr/sql/parser.go:23`, Minor (Mysterious Name, judgement call).** The variable is still called `duckDB` but now holds the stub `DB`. `sql_command.go:96` renamed the same variable to `db`, so the two are inconsistent.

5. **`pkg/expr/sql/db.go:12`, Minor (Speculative Generality, judgement call).** `DB.TablesList` is never called. The package-level `TablesList` in parser.go is what callers use. `DB` also has no doc comments on exported names; this is the Code Review Comments rule that the style guide adopts.

6. **`pkg/expr/reader.go:194`, Minor (Feature Envy, judgement call).** `enableSqlExpressions(h *ExpressionQueryReader)` is a free function that only reads `h.features`. The existing check at `reader.go:160` calls `h.features.IsEnabledGlobally(...)` inline.

7. **Commit subjects, Minor (`contribute/create-pull-request.md:90-125`).** "disable sql expressions" and "Run `make update-workspace`" have no `<Area>:` prefix, for example `Expressions: Disable SQL expressions` or `Chore: ...`. The PR title becomes the squashed commit, so this only matters if it carries over to the PR title.

## Spec

No spec was given or found, so I skipped this axis. One side note: without a spec, I can't tell whether "disable" was meant to be permanent (which would mean removing the toggle) or flag-controlled (which is what the code appears to attempt but does not do). Finding 1 depends on which was intended.

## Summary

- **Standards:** 7 findings (3 Important, 4 Minor). The worst is that `enableSqlExpressions` always returns false, so the documented `sqlExpressions` toggle does nothing while the frontend still offers the feature.
- **Spec:** not reviewed, no spec.

## Files not reviewed in depth

- **`go.sum` and `go.work.sum`:** generated by `go mod tidy` / `make update-workspace`. I only checked that the removals match the `go.mod` deletions (go-duck and the indirect dependencies only it needed). I did not check hashes, because benchmark mode bars running `go mod verify`.
- **`go.mod`:** read. No other module in the workspace refers to `go-duck`.

All other files in the patch (`reader.go`, `sql/db.go`, `sql/parser.go`, `sql_command.go`) were reviewed. Everything above is reasoned from the code; no test run confirms it. The existing SQL tests (`pkg/expr/sql/parser_test.go`, `sql_command_test.go`) were already `t.Skip()`ed before this patch, so CI will not catch any of this.
