## Review of grafana__grafana__107534 (base d9a8253640 → HEAD 1cab4143d4)

I used `open-code-review:delegate-review`. OCR's preview put the 2 source files in scope and left out the 2 test files by its default path rule. I reviewed the test files from the patch anyway. I edited nothing and ran no tests: no new tests and no project suites. The skill says to auto-fix; your brief says report only, so I did not fix anything.

The core change looks right. `runSplitQuery` used to compute `calculateStep` and `isLogsQuery` from the raw `step` and `expr`. It now does both on interpolated values, which fixes `step: '$step'`. One side effect is an improvement: in the shard path, `$__range` is no longer resolved in the frontend, because `applyTemplateVariables` strips `__range`. The `$__range` guard in `querySupportsSplitting` now works there too. The problems are below.

### Important

**1. `shardQuerySplitting.ts:49-52` — a query whose variable resolves to an empty string now leaves the panel loading forever. It used to be dropped.**
- **Before:** `interpolateVariablesInQueries(...)` ran first and `.filter((q) => q.expr)` ran after it, so a target like `expr: '$query'` with an empty textbox or custom variable was removed.
- **Now:** commit 76ffba5f6d ("fix target filtering") filters first and interpolates second, so the target stays in with `expr: ''`.
- **What follows:**
  - `groupTargetsByQueryType` (`shardQuerySplitting.ts:244-251`) sees that `requestSupportsSharding([q])` is false and puts the query in `otherQueries`. That group is pushed first, so it is group 0.
  - `runNextRequest` calls `runSplitQuery(datasource, subRequest)` (`:163`).
  - Inside `runSplitQuery`, `.filter((query) => query.expr)` (`querySplitting.ts:298`) now drops the empty target, so `requests` is `[]`.
  - `runSplitGroupedQueries` (`querySplitting.ts:95-96`) then runs `Math.max(...[])`, which gives `-Infinity`, and `requests.filter(...)[0].partition` throws a TypeError.
- **Effect:** the throw happens inside the `.then()` at `shardQuerySplitting.ts:213`, so it becomes an unhandled promise rejection. The Observable never emits or completes. The panel spins forever, and a valid sharded query in the same request never runs either.
- **When it triggers:** `lokiShardSplitting` is on, there is at least one shardable query, and another target's expression interpolates to `''`.
- **Status:** reasoned, not run. A test that should fail on HEAD:
  - Targets: `[{refId:'A', expr:'sum(count_over_time({a="b"}[1m]))'}, {refId:'B', expr:'$empty'}]`.
  - Datasource: `createLokiDatasource({ replace: (s='') => s.replace('$empty',''), getVariables: () => [] })`, with `fetchLabelValues` mocked to resolve `['1','2']` and `runQuery` mocked to `of({data:[]})`.
  - Assert: `await expect(runShardSplitQuery(ds, request)).toEmitValuesWith(() => expect(ds.runQuery).toHaveBeenCalled())`.
  - On HEAD this times out with no emission. Restoring interpolate-then-filter, or filtering `expr` after the `.map(applyTemplateVariables)`, makes it pass.
- **Wider gap:** `runSplitGroupedQueries` has no guard for an empty `requests` array. That gap existed before, but this patch makes it reachable.

### Minor

**2. `querySplitting.ts:296-299` (and the shard path) — ad hoc filters are added more than once.**
- `datasource.runQuery` calls `DataSourceWithBackend.query`, which calls `applyTemplateVariables(q, scopedVars, request.filters)` again (`packages/grafana-runtime/src/utils/DataSourceWithBackend.ts:185`). The split sub-requests still carry `filters` because of `{...request}`.
- Stream-selector insertion removes duplicates (`labelExists`, `modifyQuery.ts:494`). `addFilterAsLabelFilter` (`modifyQuery.ts:511-541`) does not.
- So for a query with a parser, such as `{a="b"} | logfmt` plus a filter `x=y`, the backend receives `| x=\`y\` | x=\`y\``. In the shard path, `runSplitQuery` interpolates a third time, so the filter appears three times. Before the patch it appeared twice.
- Results are still correct because repeating the same filter changes nothing. The cost is a bloated query string in the query inspector.
- **Status:** reasoned.

**3. Interpolation is no longer idempotent.**
- Running `templateSrv.replace` on an already interpolated expression substitutes any `$name` that came from a variable's value, when `name` is also a defined variable.
- Before the patch the non-shard split path interpolated once. It now does it twice, and the shard path three times.
- This only hits variable values that contain a `$identifier`.
- **Status:** reasoned.

**4. Test quality (`shardQuerySplitting.test.ts:112`, both new "Interpolates queries before execution" tests).**
- `toHaveBeenCalledTimes(5)` pins the exact number of internal calls (1 shard call + 4 sub-requests). Any refactor of how often the code interpolates will break it even when behaviour is unchanged. That goes against your testing guidance: "test contracts, not implementation".
- The new tests mock `replace` so that it rewrites `$__auto`. In production `applyTemplateVariables` strips `__auto`, and `$__auto` reaches the backend unchanged. The asserted `[5m]` never happens for real.

### Coverage
- 4 files, 4 reviewed, 0 skipped, coverage 100%.
- Reviewed:
  - `public/app/plugins/datasource/loki/querySplitting.ts`
  - `public/app/plugins/datasource/loki/shardQuerySplitting.ts`
  - `public/app/plugins/datasource/loki/querySplitting.test.ts` (OCR left it out by default path; I reviewed it from the patch)
  - `public/app/plugins/datasource/loki/shardQuerySplitting.test.ts` (same)
- There was no spec, so I checked nothing against one. The OCR rule checklist (TS rules) found no breaches in the changed lines.

Not checked: I ran nothing, so finding 1 is reasoned, and the git history before the patch could not be fetched because the clone is partial and network access was denied. Risk: finding 1 hangs any shard-split panel that has a target whose variable resolves to an empty string.
