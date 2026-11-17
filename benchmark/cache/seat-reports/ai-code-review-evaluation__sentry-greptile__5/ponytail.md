## Over-engineering review: base 49a2758..HEAD ea188e2 (32 commits, 106 files)

**What this change does:** It's a batch of 32 unrelated commits:
- Explore's `Visualize` moves from a list of y-axes to a single `yAxis`.
- A new `TableWidgetVisualization` component, sitting behind a feature flag.
- A feedback AI summary.
- Error context for the replay AI summary.
- An owner field on detectors.
- Validation in the browser-report collector built on a DRF serializer.
- The PR-comment issue line now shows the environment.
- Many styled flex divs are replaced with the core `<Flex>` component.
- Several deletions: the regex parameterization experiment, the dead migrations, and the grouping "Type" rows.

Most of the change is net deletion and fine. The findings below are what is still unneeded or duplicated.

### Should fix

1. **Flag branch renders a stub table; the whole component has no live caller** — `static/app/views/dashboards/widgetCard/chart.tsx:164-175` — Important
   - **What this is:** With `use-table-widget-visualization` on, the widget renders `<TableWidgetVisualization columns={[]} tableData={{data: [], meta: {fields: {}, units: {}}}} />`.
   - **Problem:** It ignores `tableResults` completely, so turning the flag on shows an empty table instead of the data. The flag is not registered anywhere in the repo, so in practice the branch is dead code. That makes the new 134-line component, the 104-line renderer module, the stories, the fixtures and the spec support code with no production user.
   - **Evidence:** `grep -rn "table-widget-visualization" src/ static/` matches only `chart.tsx:164`. `grep -rln TableWidgetVisualization static` matches only the component's own files and `chart.tsx`.
   - **Fix:** Drop the branch (and the added `organization` destructure and the `org` rename at :141/:152) until the component is fed real `tableResults`.
   - **Proof:** Reasoned plus the grep above. No failing test was written.

2. **Unused props on the new table component** — `static/app/views/dashboards/widgets/tableWidget/tableWidgetVisualization.tsx:31,35,63` (and `FRAMELESS_STYLES` at ~:66-74, uses at :119-125) — Minor
   - `fit`, `frameless` and `scrollable` have no caller anywhere (stories and spec included), so they are speculative options.
   - `tableData` is a required prop, yet it is read with `tableData?.` at :94, :98 and :103. That optional chaining is dead.
   - **Fix:** Delete the three props and the styles constant; use `tableData.` directly. About 25 lines.

3. **Dead `format_comment_subtitle` left behind; truncation written a third time** — `src/sentry/integrations/github/integration.py:394`, `src/sentry/integrations/gitlab/integration.py:240`, `src/sentry/integrations/source_code_management/commit_context.py:578` — Minor
   - Both `format_comment_subtitle` methods lost their only caller in this change.
   - **Evidence:** `grep -rn "format_comment_subtitle(" src tests` shows only the two definitions.
   - The new `_truncate_title(title, max_length=ISSUE_TITLE_MAX_LENGTH)` repeats the same 50-character truncation. Its `max_length` parameter is never passed.
   - **Fix:** Delete both dead methods (about 8 lines) and drop the `max_length` parameter.

4. **Leftover one-element "dedupe" arrays after the single-y-axis refactor** — Minor
   - Locations: `static/app/views/explore/utils.tsx:439`, `spans/spansTab.tsx:349`, `hooks/useExploreTimeseries.tsx:179`, `hooks/useAnalytics.tsx:475,496`, `toolbar/toolbarSaveAs.tsx:153`, `charts/index.tsx:154`.
   - Each one is now `const dedupedYAxes = [visualize.yAxis]` followed by `.flatMap`/`.map` over that single element. The name is now wrong and the loop does nothing.
   - **Fix:** Use `data[visualize.yAxis]` directly, for example `const series = [data[visualize.yAxis]].filter(defined)`, or drop the array entirely.
   - Related: `Visualize.stack` (`contexts/pageParamsContext/visualizes.tsx:41,49`) is now always `'all'` but is still typed optional and still computed in the constructor.

5. **Ineffective memoization and double option-building in the attribute-keys hook** — `static/app/views/explore/hooks/useTraceItemAttributeKeys.tsx:26-43` — Minor
   - When `projects` is passed, `projectIds` is a new array on every render, so both `useMemo`s recompute every time.
   - The options are built once for `queryKey` and again inside `getTraceItemAttributeKeys()`.
   - The new `useGetTraceItemAttributeKeys` has one caller, and that caller never passes the `search`/`queryString` argument (`useGetTraceItemAttributeKeys.tsx:34,40,65,71`), so it is a speculative parameter.
   - The `try { … } catch (e) { throw new Error(`…${e}`) }` at :76-86 turns the `ApiError` into a plain string and adds nothing.
   - **Fix:** Drop the two `useMemo`s and the rethrow, and inline the unused `search`.

6. **Owner-to-ids mapping written twice** — `src/sentry/workflow_engine/endpoints/validators/base/detector.py:66-79` and `:120-128` — Minor
   - `update` and `create` each turn the owner (an "actor", meaning a user or a team) into `owner_user_id`/`owner_team_id` in slightly different shapes.
   - **Fix:** Compute `owner_user_id = owner.id if owner and owner.is_user else None` (and the same for team) once and use it in both places. That removes about 10 lines, and the `update` branch for clearing the owner collapses into it.
   - The repo has no shared helper for this; the same block is also copied in `uptime/subscriptions/subscriptions.py` and `monitors/endpoints/organization_monitor_index.py`.

7. **Mirrored field validators** — `src/sentry/issues/endpoints/browser_reporting_collector.py:50-60` — Minor
   - `validate_timestamp` and `validate_age` are copies of each other. One `validate(self, attrs)` that checks `"age" in attrs and "timestamp" in attrs` replaces both.
   - That rewrite also fixes a real bug: the current checks test truthiness, so a report with both `age: 0` and `timestamp: 0` is accepted.
   - Also, `str(browser_report["type"])` at :126 is redundant because the `ChoiceField` already returns a string.

8. **Three hand-built return objects** — `static/app/components/feedback/list/useFeedbackSummary.tsx:43-66` — Minor
   - The pending, error and success branches each build the same object shape. One `return {summary: data?.summary ?? null, isPending, isError, tooFewFeedbacks: !!data && data.numFeedbacksUsed === 0 && !data.success}` does the same job.
   - `Boolean(normalizedDateRange)` at :37 is always true, because `normalizeDateTimeParams` returns an object.
   - The feature flag is checked both here and in `feedbackSummary.tsx`.

### Nice to have

9. **A field that is written but never read** — `src/sentry/replays/endpoints/project_replay_summarize_breadcrumbs.py:37,112`
   - `ErrorEvent.category` is always set to `"error"` and nothing reads it; `generate_error_log_message` uses only `title`, `message` and `timestamp`. Delete the field.

Verdict: fix 1 first (the stub flag branch). The rest is cleanup.
Lean: about 100 lines could go (about 60 more if the unused table component is held back until it has a real caller).

### Files not reviewed
- **Read only quickly, not line by line (tests and fixtures, low value for this lane):**
  - `tests/sentry/api/endpoints/test_browser_reporting_collector.py`
  - `tests/sentry/api/endpoints/test_project_details.py`
  - `tests/sentry/api/serializers/test_project.py`
  - `tests/sentry/integrations/github/tasks/test_pr_comment.py`
  - `tests/sentry/integrations/gitlab/tasks/test_pr_comment.py`
  - `tests/sentry/migrations/test_0917_convert_org_saved_searches_to_views.py`
  - `tests/sentry/replays/tasks/test_delete_replays_bulk.py`
  - `tests/sentry/replays/test_project_replay_summarize_breadcrumbs.py` (only the test names)
  - `tests/sentry/workflow_engine/endpoints/test_organization_detector_details.py` (only the test names)
  - `tests/sentry/workflow_engine/endpoints/test_organization_detector_index.py` (only the test names)
  - `tests/sentry/workflow_engine/processors/test_delayed_workflow.py`
  - `tests/snuba/api/endpoints/test_organization_events_stats.py`
  - `static/app/views/explore/contexts/pageParamsContext/index.spec.tsx`
  - `static/app/views/explore/contexts/pageParamsContext/visualizes.spec.tsx`
  - `static/app/views/explore/hooks/useGetTraceItemAttributeValues.spec.tsx`
  - `static/app/views/explore/tables/aggregateColumnEditorModal.spec.tsx`
  - `static/app/views/explore/toolbar/index.spec.tsx`
  - `static/app/views/explore/utils.spec.tsx`
- **Read only as far as finding 1 needed:**
  - `static/app/views/dashboards/widgets/tableWidget/tableWidgetVisualization.spec.tsx`
  - `static/app/views/dashboards/widgets/tableWidget/tableWidgetVisualization.stories.tsx`
  - `static/app/views/dashboards/widgets/tableWidget/fixtures/sampleHTTPRequestTableData.ts`
  - `tests/js/fixtures/tabularColumn.ts`
  - `tests/js/fixtures/tabularColumns.ts`
- **Read only partly:** `devservices/config.yml` (dev config, not application code).
- Every other file in the patch was reviewed. The 0917/0920 migrations, `src/sentry/options/defaults.py`, the parameterization removal and the Flex swaps are pure deletions and raise no lean issues.

Not checked: I did not run any tests (the instructions said not to), and I did not check whether getsentry registers `use-table-widget-visualization`.
