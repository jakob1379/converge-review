## Code review: base 49a2758 → HEAD ea188e2 (32 commits, 106 files)

I followed the `mattpocock-skills:code-review` skill and did both axes myself, with no sub-agents. The only repo standards source is the root `CLAUDE.md`; `.github/CONTRIBUTING.md` just links to external docs. As instructed, I left out the skill's generic smell checklist and the user's personal global rules (no comments, no noqa).

### Spec axis
There is no spec, so there is nothing to check on this axis.

### Standards axis: findings

1. **`static/app/views/dashboards/widgetCard/chart.tsx:164`: Important.** The new branch checks the flag `use-table-widget-visualization`, but nothing registers that flag. CLAUDE.md says to add flags in `temporary.py` ("Add feature flag in `temporary.py`"; Common Gotchas #2 "Feature Flags: Always add for new features").
   - **Evidence:** `grep -rn "use-table-widget-visualization" src/` returns nothing, while the other flags in this patch (`user-feedback-ai-summaries`, `preprod-artifact-assemble`) are in `src/sentry/features/temporary.py` (lines 441 and 278).
   - **Impact:** the branch is dead code for now. If someone turns the flag on, every table widget renders `<TableWidgetVisualization columns={[]} tableData={{data: [], ...}} />`, which is an empty table.
   - **Failing check:** `grep -q "use-table-widget-visualization" src/sentry/features/temporary.py || echo MISSING` prints `MISSING`.

2. **`static/app/components/feedback/feedbackSummary.tsx` and `static/app/components/feedback/list/useFeedbackSummary.tsx`: Minor.** Both are new and neither has a colocated `.spec.tsx`. CLAUDE.md says "ALWAYS write test in same directory with `.spec.tsx`" (Frontend Rules #5). `ls static/app/components/feedback/feedbackSummary.spec.tsx` fails. The hook's `tooFewFeedbacks = numFeedbacksUsed === 0 && !success` logic and the component's hide/placeholder states are not tested anywhere.

3. **`static/app/views/explore/hooks/useGetTraceItemAttributeKeys.tsx`: Minor.** This new hook has no colocated spec (same rule as #2). It is only exercised indirectly through `useTraceItemAttributeKeys.spec.tsx`, which always calls it without `queryString`. So the `substringMatch` path that the new callable exists for is never tested.

4. **`static/app/views/feedback/feedbackListPage.tsx:88`: Minor.** The new styled component `SummaryListContainer` is given an inline `style={{gridArea: 'list'}}`. CLAUDE.md lists "WRONG: Inline styles … RIGHT: Emotion styled". This carries over the old `<Container style=…>`, but since the container is new, `grid-area` can go into its styled definition.

5. **`src/sentry/integrations/source_code_management/commit_context.py:584`, called per issue at `github/integration.py:409` and `gitlab/integration.py:257`: Minor.** This is the "N+1 queries" anti-pattern from CLAUDE.md. For each issue, `get_environment_info` calls `issue.get_recommended_event()`: a Snuba query plus a nodestore fetch, and a second query when it falls back to `get_latest_event`. The list is capped at 5 issues (`set_limit(5)`, `commit_context.py:572`) and runs inside a task, so the impact is small.

6. **Same PR-comment change (commit fd4ab7b535, `feat(scm)`): Minor.** It changes the format of the PR/MR comment every customer sees: it drops the culprit, changes the link style, and adds environment. There is no feature flag, against Common Gotchas #2 "Always add for new features". Test coverage is also thin ("Write comprehensive tests"):
   - the `_truncate_title` path (titles over 50 characters) is never hit, because the test titles are "issue 1"–"issue 3";
   - the exception branch of `get_environment_info` is never hit;
   - `grep -rn "_truncate_title\|ISSUE_TITLE_MAX_LENGTH" tests/` returns nothing.

7. **`src/sentry/preprod/api/endpoints/organization_preprod_artifact_assemble.py:81`: Minor.** `analytics.record("preprod_artifact.api.assemble", …)` runs before the `features.has("organizations:preprod-artifact-assemble", …)` check at line 88. Orgs without the feature get a 404 but still emit the event. CLAUDE.md's flag pattern puts new feature code inside the `features.has` block. No test checks the event: `tests/sentry/preprod/api/endpoints/test_organization_preprod_artifact_assemble.py` never mentions analytics.

8. **`src/sentry/issues/endpoints/browser_reporting_collector.py:50-60`: Minor.** Validation of the `age`/`timestamp` pair is incomplete (Security Guideline 1, "Always validate user input"). This is reasoned, not run:
   - Both fields are `required=False`, so a report with neither `age` nor `timestamp` passes, even though the validators' docstrings say one must be present.
   - The checks use truthiness (`self.initial_data.get("age")`), so `age: 0` together with `timestamp` passes.
   - The rewritten tests no longer post `content_type="application/reports+json"`; `grep -n "reports+json"` on the test file returns nothing. The custom `BrowserReportsJSONParser` now has no passing-request coverage, only the 415 negative test.

### Checked and not flagged
- **Migrations 0917/0920 turned into no-ops, and `test_0917` deleted.** No schema change, and the replacement `0921_…_rerevised.py` and its test `tests/sentry/migrations/test_0921_…py` exist, so the backwards-compatible/rollback rules are not breached.
- **Direct model imports in the replay endpoint (`project_replay_summarize_breadcrumbs.py:19-20`).** This literally matches the CLAUDE.md "Direct model import in API" anti-pattern, but 206 of 236 files in `src/sentry/api/endpoints/` do the same, so the rule isn't enforced in practice and I didn't treat it as a finding.
- **`src/sentry/preprod/__init__.py` `# NOQA`.** Matches the existing repo pattern (`src/sentry/api/__init__.py:1`).
- **Browser report fields in snake_case (`user_agent`).** The W3C Reporting format dictates these names, so the camelCase body rule doesn't apply.
- **Detector `owner` field.** `ActorField` checks the owner against the org, and both endpoints pass `organization` in context.
- **Everything else:** Taskworker deadline bumps, delayed_workflow refactor, the contextual logger, the `Flex` primitive migrations, and the Visualize single-yAxis refactor all match existing conventions and Emotion usage. I found no new class components and no raw `fetch`.

### Outside my axis (correctness, for whoever reviews bugs)
- **`project_replay_summarize_breadcrumbs.py:118`:** `zip(error_ids, events.values())` assumes `nodestore.get_multi` keeps input order. It doesn't: `get_multi` removes duplicate ids and, when some ids are cached, puts the cached ones after the fetched ones (`nodestore/base.py:184,205`). Error ids can end up paired with the wrong event data.
- **`useTraceItemAttributeKeys`:** it no longer sends `environment` (the comment at `useGetTraceItemAttributeKeys.tsx:50` says this is intentional), which changes behaviour.

### Files not reviewed
None. I read all 106 files in the patch. The mechanical test updates (the explore `*.spec.tsx` `new Visualize([x])` → `new Visualize(x)` edits, and the autofix default `"low"`→`"off"` test asserts) I only skimmed for pattern consistency.

I didn't run any tests, as instructed. Every claim comes from reading the patch and HEAD source plus grep; findings 5, 6 (impact) and 8 are reasoned rather than shown by a failing command.
