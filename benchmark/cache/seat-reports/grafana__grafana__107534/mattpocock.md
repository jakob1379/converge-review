## Code review: grafana__grafana__107534 (base d9a8253640, HEAD 1cab4143d4, 6 commits)

I used `mattpocock-skills:code-review`. The skill normally runs the review in two parallel sub-agents. I did both axes myself instead, because the brief forbids spawning agents. I did not run any tests; every finding below is reasoned from the code.

### Spec
There is no spec, so I skipped this axis. From the commit titles, the intent is: "Loki query splitting: interpolate queries before execution", plus a fix to target filtering in shardQuerySplitting. The main goal is met. `runSplitQuery` now interpolates `step` and `expr` before `calculateStep` and `querySupportsSplitting` run, so a `step: '$step'` value now works.

### Standards
**Standards sources checked:** `CONTRIBUTING.md`, `contribute/style-guides/frontend.md`, `contribute/style-guides/testing.md`. None of their rules apply to this diff (test naming and file placement are followed). Everything below is correctness, or a baseline smell, which is a judgement call.

1. **Important: ad hoc filters and template variables are now applied 2–3 times per query.** `querySplitting.ts:296-299` and `shardQuerySplitting.ts:49-52`.
   - **How it happens:**
     - `runShardSplitQuery` calls `applyTemplateVariables(query, scopedVars, request.filters)`.
     - Each shard sub-request then goes to `runSplitQuery` (`shardQuerySplitting.ts:162`), which calls `applyTemplateVariables` again with the same `request.filters`. The `{ ...request, targets }` spread keeps `filters`.
     - `datasource.runQuery` → `DataSourceWithBackend.query` calls `applyTemplateVariables` a third time (`packages/grafana-runtime/src/utils/DataSourceWithBackend.ts:185`).
   - **Before:** the shard path used `interpolateVariablesInQueries(targets, scopedVars)` with no filters, and `runSplitQuery` did no interpolation, so ad hoc filters were applied exactly once (in `super.query`).
   - **Why it duplicates:** `addAdHocFilters` → `addLabelToQuery` only removes duplicates on the stream-selector path (`modifyQuery.ts:494`). `addFilterAsLabelFilter` (`modifyQuery.ts:511-540`) appends the filter with no duplicate check.
   - **Example:** `sum(count_over_time({a="b"} | logfmt [$__auto]))` with ad hoc filter `level="error"` comes out as `... | logfmt | level=`error` | level=`error` | level=`error``.
   - **Impact:** results are the same, because the filters are idempotent. But the query text sent to Loki and shown in the Query inspector grows with each pass.
   - **The patch's own test shows the extra pass:** it expects `applyTemplateVariables` to be called 5 times for one target (`shardQuerySplitting.test.ts:112`).
   - **Test that would fail on the patched code:** run `runSplitQuery` on a real `createLokiDatasource()` with `request.filters = [{key:'level',operator:'=',value:'error'}]`, expr `{a="b"} | logfmt`, and `runQuery` left unmocked down to `super.query`. Assert that the backend target contains exactly one `level=`error``.
   - **Simplest fix direction:** pass ad hoc filters only once. Either call `templateSrv.replace` for `expr`/`step` without filters before splitting, or skip re-interpolation in `runSplitQuery` when it is called from the shard path.
2. **Minor: repeated `templateSrv.replace` is not idempotent for values that contain `$name`.** `querySplitting.ts:299` and `shardQuerySplitting.ts:52`. A variable whose value holds a literal `$foo` is expanded again on each later pass. This edge case is new in the split path.
3. **Minor: the filter now runs before interpolation, so it checks the raw expression.** `shardQuerySplitting.ts:49-52` (and the same order in `querySplitting.ts:296-299`).
   - Before, `.filter((q) => q.expr)` ran after interpolation. Now it runs before.
   - A target whose expr is only a variable that resolves to `''` now gets through and is sent as an empty query. Before, it was dropped.
   - The commit "fix target filtering" seems to have done this on purpose, but empty-after-interpolation targets are not handled anywhere.
4. **Minor: the new tests assert behaviour production never produces.** `querySplitting.test.ts:75-88` and `shardQuerySplitting.test.ts:84-101`.
   - The mocked `replace` swaps `$__auto` for `5m` on every call.
   - The real `applyTemplateVariables` deliberately removes `__auto` from `scopedVars` (`datasource.ts:1113`), so `$__auto` reaches the backend unexpanded.
   - So the `[5m]` assertions test the mock. Only the `step` assertion reflects real behaviour.
5. **Minor (baseline smell, Duplicated Code):** the same "Interpolates queries before execution" test sits in both test files. `shardQuerySplitting.test.ts` now also has a near-duplicate pair: "Interpolates queries before execution" (line 84) and "Interpolates queries before running" (line 110).

**Summary:** Standards has 5 findings; the worst is #1 (ad hoc filters applied 2–3 times, Important). Spec: none, no spec available.

**Files not reviewed:** none. I reviewed all 4 files in the patch (`querySplitting.ts`, `querySplitting.test.ts`, `shardQuerySplitting.ts`, `shardQuerySplitting.test.ts`).

I did not check whether Loki or Grafana's query caching is affected by the duplicated filter text.
