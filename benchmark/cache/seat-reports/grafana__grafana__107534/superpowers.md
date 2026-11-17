## Code review: grafana__grafana__107534 (base d9a8253640, head 1cab4143d4)

I loaded `superpowers:requesting-code-review`. That skill normally hands the review to a subagent, but your brief said not to spawn agents, so I did the review myself using its checklist (plan alignment, quality, architecture, tests). I did not run any tests or install anything; every finding is from reading the code.

**What the patch does (there is no spec, so I took the intent from the commit "Loki query splitting: interpolate queries before execution").**
- `runSplitQuery` now runs `datasource.applyTemplateVariables(query, request.scopedVars, request.filters)` on each target before it partitions them.
- `runShardSplitQuery` swaps `interpolateVariablesInQueries` (which took no filters) for the same per-query `applyTemplateVariables` call.

**Plan alignment.** The core goal is met. `calculateStep(..., query.step)` and the `isLogsQuery` / `querySupportsSplitting` partitioning now see the interpolated `expr` and `step`, so a `step: '$step'` target is grouped by its real step. `$__range`, `$__auto` and `$__interval` are still left for the backend, because `applyTemplateVariables` strips them from scopedVars. That keeps the `isQueryWithRangeVariable` guard working.

### Findings

**1. Important: ad-hoc filters are applied two or three times, and the tests lock that in.**
- Locations:
  - `public/app/plugins/datasource/loki/querySplitting.ts:296-299`
  - `public/app/plugins/datasource/loki/shardQuerySplitting.ts:49-52`
  - re-entry point: `shardQuerySplitting.ts:163`
- **Claim:** queries are now interpolated, with ad-hoc filters added, more than once on every split path.
  - Time-split path: once in `runSplitQuery`. Then `datasource.runQuery` calls `super.query(...)`, and `DataSourceWithBackend.query` (`packages/grafana-runtime/src/utils/DataSourceWithBackend.ts:185`) calls `this.applyTemplateVariables(q, request.scopedVars, request.filters)` again. Sub-requests are built as `{ ...request, targets }`, so `filters` is still there.
  - Shard path: once in `runShardSplitQuery`, again when it hands each sub-request to `runSplitQuery` (`shardQuerySplitting.ts:163`), and a third time in `super.query`.
  - Before the patch, the time-split path added filters once and the shard path added them once (`interpolateVariablesInQueries` was called without filters).
- **Evidence that this is not idempotent:**
  - `addLabelToQuery` only removes duplicates for stream-selector matchers (`labelExists` in `addFilterToStreamSelector`, `modifyQuery.ts:494`).
  - Queries with a parser take the `addFilterAsLabelFilter` path (`modifyQuery.ts:511-541`), which always appends. The existing test at `modifyQuery.test.ts:46` shows `{foo="bar"} | logfmt | x="y"` gaining another filter rather than being merged.
  - So `rate({a="b"} | logfmt [5m])` with ad-hoc `k=v` becomes `rate({a="b"} | logfmt | k=`v` | k=`v` [5m])` on the time-split path, with a third copy on the shard path. The non-split path (`datasource.ts:343`) produces a single copy.
- **Impact:** results are the same, because repeated ANDed label filters change nothing. But the executed LogQL differs between split and non-split paths, the query inspector shows bloated queries, and the template replace runs again on already-interpolated text. A dashboard variable value or ad-hoc value containing `$name` that matches another variable would be expanded a second time. Any future non-idempotent transform inside `applyTemplateVariables` turns this into a real bug.
- **Tests that lock it in:** the shard test now asserts `expect(datasource.applyTemplateVariables).toHaveBeenCalledTimes(5)` (`shardQuerySplitting.test.ts:112`), i.e. 1 call in the shard entry plus 4 in `runSplitQuery`.
- **Failing test (reasoned, not run):** in `querySplitting.test.ts`, use a real `createLokiDatasource()`, `request.filters = [{ key: 'k', operator: '=', value: 'v' }]`, target `expr: 'rate({a="b"} | logfmt [5m])'`, and spy on `runQuery`. Then assert:
  `const t = runQuery.mock.calls[0][0].targets[0]; expect(datasource.applyTemplateVariables(t, {}, request.filters).expr).toBe(t.expr)`.
  This fails on the patched code because a second `| k=`v`` gets appended, and that is exactly what `super.query` does next.
- **Simpler fix:** interpolate into local copies used only for classification and step grouping, and still send the original targets to `runQuery`. Or interpolate without `filters` (as the old shard code did) and leave ad-hoc injection to `super.query`. In both cases, don't interpolate again inside `runSplitQuery` when the shard path calls it.

**2. Minor: the shard test checks how many times interpolation runs, not what gets sent.**
- Location: `public/app/plugins/datasource/loki/shardQuerySplitting.test.ts:112`.
- `toHaveBeenCalledTimes(5)` describes the redundant re-interpolation in finding 1 rather than the query that is sent. It will break when that redundancy is removed, even though behaviour is unchanged. The `toHaveBeenCalledWith` assertion right below it already covers the real contract.

**3. Minor: no test covers ad-hoc filters or `$__range` on the new interpolation path.**
- Locations: `querySplitting.test.ts:75-88` and `shardQuerySplitting.test.ts:84-101`.
- Both new tests mock `templateSrv.replace` as plain string replacement and pass no `filters`. So the new `request.filters` argument, the more-than-once interpolation, and the `$__range` no-split guard on interpolated queries are all untested.

**4. Minor: the shard path now resolves `$__auto` / `$__interval` / `$__range` differently.**
- Location: `shardQuerySplitting.ts:49-52`.
- `interpolateVariablesInQueries` resolved these on the client from the full scopedVars. `applyTemplateVariables` leaves them for the backend, which then resolves them per time-split sub-request.
- For `[$__range]`, `querySupportsSplitting` now stops the time split, which is arguably more correct than before. For `$__auto` / `$__interval`, the backend now picks the value per chunk. This matches the non-shard path, so I don't count it as a bug, but it is a user-visible change the PR doesn't mention.
- Side effect: the shard-values selector (`getSelectorForShardValues`) now includes ad-hoc stream matchers, so fewer shards are fetched. That is probably an improvement.

### Behaviours I set aside as out of scope
- The `datasource: this.getRef()` that `interpolateVariablesInQueries` used to set is gone. `DataSourceWithBackend.query` falls back to `this` when `q.datasource` is unset, so there is no impact.
- I did not check whether Scenes' `sceneGraph.interpolate` resolves `$__range` as a macro even when it is absent from scopedVars. `node_modules` isn't present. The non-split path already depends on the same `applyTemplateVariables` behaviour, so this isn't new.

### Files not reviewed
None. I reviewed all 4 files in the patch: `querySplitting.ts`, `querySplitting.test.ts`, `shardQuerySplitting.ts` and `shardQuerySplitting.test.ts`.

### Verdict
The patch fixes the step/variable grouping problem it set out to fix. Merge it with fixes: finding 1 should be addressed first, because the patch stacks interpolation (twice on the time-split path, three times on the shard path), and the 5-call assertion in the tests holds that in place.

I did not run jest. Findings 1 and 2 come from reading `DataSourceWithBackend.query` and the `modifyQuery` code and its existing test table, not from an executed failing test.
