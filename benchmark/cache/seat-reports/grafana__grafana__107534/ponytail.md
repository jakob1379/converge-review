## Ponytail review: grafana__grafana__107534 (base d9a8253640 to HEAD 1cab4143d4)

**What the change does:** `runSplitQuery` now runs `datasource.applyTemplateVariables` on each visible, non-empty target before it partitions and groups them. Grafana dashboard variables such as `$step` and `$var` in `expr`/`step`/`legendFormat` are therefore resolved before `calculateStep` and `isLogsQuery` read them. `runShardSplitQuery` changes from `interpolateVariablesInQueries(targets, scopedVars)` to per-query `applyTemplateVariables(q, scopedVars, filters)`, and it now filters hidden and empty targets before interpolating. Both test files gain an "Interpolates queries before execution" test, and the shard tests swap their mocks to the new method.

**Over-engineering verdict:** none found. There are no new abstractions, options or helpers. The production change is 2 call sites and about 6 lines, and it uses the datasource's existing method. Scope: I assumed the load of a Grafana frontend panel query, with one call per panel refresh. I read all of `querySplitting.ts`, `shardQuerySplitting.ts`, `datasource.ts` (`query`, `applyTemplateVariables`, `addAdHocFilters`), `modifyQuery.ts` (`addLabelToQuery`, `addFilterToStreamSelector`, `addFilterAsLabelFilter`) and `DataSourceWithBackend.query` for context.

### Nice to have

1. **Ad-hoc filters on parsed labels are added 2 or 3 times** (`public/app/plugins/datasource/loki/querySplitting.ts:299`, `public/app/plugins/datasource/loki/shardQuerySplitting.ts:52`). Severity: Minor.
   - **What this is:** Each `applyTemplateVariables` pass also runs `addAdHocFilters(expr, request.filters)`. An ad-hoc filter is a dashboard-level label filter that Grafana adds to every query.
   - **Problem:** `DataSourceWithBackend.query` (`packages/grafana-runtime/src/utils/DataSourceWithBackend.ts:185`) already applies it again on every `runQuery`. Indexed labels are deduplicated by `labelExists` in `addFilterToStreamSelector` (`modifyQuery.ts:494`). Labels added after a parser go through `addFilterAsLabelFilter` (`modifyQuery.ts:510-540`), which has no duplicate check. Example: `{app="x"} | logfmt` with filter `level=error` reaches Loki as `... | level=`error` | level=`error`` on the split path. On the shard path it gets the filter three times: `runShardSplitQuery`, then `runSplitQuery` for each sub-request, then `super.query`. Before this patch the shard path did not pass `filters`, so the backend added the filter once.
   - **Impact:** The result is the same, because repeating a filter (`=`, `!=`, `=~`, `!~`, `<`, `>`) does not change what matches. The cost is a longer query in the query inspector and Loki logs, plus extra lezer parses for each sub-request. This claim is reasoned, not run: the instructions ruled out installing dependencies or running test suites.
   - **Fix (smallest):** Accept it, or make the shard path interpolate once: drop the `.map(applyTemplateVariables)` from one of the two layers on the shard route. That needs care, because `runSplitQuery` is also called directly from `datasource.ts:339`. A cleaner option is to interpolate once in `datasource.query()` before dispatching to either splitter and remove both `.map` calls. That is about -1 line net, and it moves the pass count from 3 to 2 on the shard path. It cannot get to 1, because `DataSourceWithBackend` always re-applies.
   - **If we skip it:** Repeated ` | key=`v`` text appears in inspected queries. Nothing breaks.

2. **Shard test pins the redundant pass count** (`public/app/plugins/datasource/loki/shardQuerySplitting.test.ts:112`). Severity: Minor.
   - **What this is:** `expect(datasource.applyTemplateVariables).toHaveBeenCalledTimes(5)` asserts the number of internal calls: 1 at shard entry plus 4 `runSplitQuery` sub-requests.
   - **Problem:** It tests an implementation detail and locks in the double interpolation from finding 1. If someone removes the redundant pass, the test fails while behaviour stays the same. The `toHaveBeenCalledWith` assertion just below already checks the interpolated `expr` that is sent.
   - **Fix:** Delete the `toHaveBeenCalledTimes(5)` line (-1 line) and keep the `runQuery` payload assertion.

Not findings (checked): the second `templateSrv.replace` over text that is already interpolated is a no-op. The only exception is a variable value that itself contains `$<name>` of another defined variable, which is an edge case and not worth a fix. `$__auto`, `$__interval` and `$__range` are left untouched for the backend, as before. The two new "Interpolates queries before execution" tests are near-copies, but they cover two separate public entry points, so that is justified.

Verdict: Ship.
Lean: -1 to -2 lines possible (drop the call-count assertion; optionally make the shard path interpolate only once).
Not checked: I did not run the jest suites (per instructions), so the duplicate-filter text in finding 1 is reasoned from `modifyQuery.ts`, not observed.

**Files in patch not reviewed:** none. I reviewed all 4: `querySplitting.ts`, `querySplitting.test.ts`, `shardQuerySplitting.ts` and `shardQuerySplitting.test.ts`.
