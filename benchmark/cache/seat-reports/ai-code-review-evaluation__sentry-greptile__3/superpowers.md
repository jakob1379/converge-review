I reviewed the patch myself and spawned no agents, as the override required. That means I did not follow the skill's step of handing the review to a subagent. The patch covers two commits on top of base 83f40559: 4cb317c5be adds upsampled error counts, and 6ad6fe3899 adds caching and also commits the `sentry-repo` gitlink. No spec was given, so I judged the change against what its own docstrings and comments claim, plus the repo CLAUDE.md and the user's global CLAUDE.md. I ran nothing except read-only greps and `git diff --check`.

## Findings

1. **sentry-repo:1 — Important.** The patch commits a submodule gitlink with no `.gitmodules` entry. That leaves a broken submodule in the repo root: `git submodule update` reports "no submodule mapping found", and fresh clones get an empty `sentry-repo` directory.
   - Evidence: `git ls-tree HEAD .gitmodules sentry-repo` shows only `160000 commit a5d29095... sentry-repo`. `git show HEAD:.gitmodules` fails with "exists on disk, but not in 'HEAD'". `git log -- sentry-repo` shows the gitlink was added by 6ad6fe3899, which is a caching commit and has nothing to do with it. This was almost certainly committed by accident.
   - Failing command: `git -C <repo> submodule status` (it errors on the unmapped path).

2. **src/sentry/api/helpers/error_upsampling.py:137 — Important.** `_is_error_focused_query` does a substring test for `"event.type:error"`, so negated and OR'd queries also count as error-only.
   - `!event.type:error` matches, so a discover query that explicitly excludes errors gets `count()` rewritten to `upsampled_count()`, which is `sum(sample_weight)`, over non-error events.
   - `event.type:error OR event.type:transaction` matches too, mixing in transactions.
   - The docstring says the check is meant "to err on the side of caution"; it does the opposite here.
   - Failing test (add to `tests/sentry/api/helpers/test_error_upsampling.py`):
     ```python
     self.request.GET = QueryDict("query=!event.type:error")
     assert _is_error_focused_query(self.request) is False  # returns True
     ```
   - At the endpoint level: take `test_error_upsampling_with_transaction_events` and change the query to `"!event.type:error"`. The transaction bucket should still be 1. That second part is reasoned, since I don't know what `sample_weight` holds for transaction rows on the discover entity.
   - Fix: parse the query (the search filter AST) instead of matching substrings.

3. **src/sentry/api/helpers/error_upsampling.py:27-40 — Important (reasoned).** The commit is titled a performance optimization, but it adds a Django cache round trip to every events-stats request, for every dataset (transactions, spans, metrics, logs). The cache lookup runs before the cheap `_should_apply_sample_weight_transform(dataset, request)` check.
   - What it replaces is `options.get(...)`, which is already cached in process: see `OptionsStore.get_local_cache` in `src/sentry/options/store.py:152`.
   - So it swaps a local dict lookup for a network call (memcached or redis) on a hot endpoint. Two of its three claims are false: the docstring's "expensive repeated option lookups" and the comment's "consistent behavior across query execution" (line 219). The third claim, faster traffic spikes, is unproven, and nothing benchmarks or tests the cache path.
   - At minimum, check the dataset first. Better, remove the cache layer.

4. **src/sentry/api/helpers/error_upsampling.py:67-74 — Important.** `invalidate_upsampling_cache` is dead code and cannot work as designed. Nothing calls it (grep finds no callers).
   - The option `issues.client_error_sampling.project_allowlist` is `FLAG_AUTOMATOR_MODIFIABLE` (`src/sentry/options/defaults.py:3464`), and nothing hooks option changes to this function.
   - Even if something did, the key includes an arbitrary set of projects per query. An allowlist change cannot list every cached `(org, project-set)` key that contains a given project.
   - Result: after a project is removed from the allowlist (for example during an incident rollback), queries keep upsampling for up to 60 seconds. Callers will be misled into thinking invalidation exists.
   - The `_are_all_projects_error_upsampled` docstring (lines 48-53) says the allowlist is "read fresh each time… to ensure we always have the latest configuration state". The new cache directly contradicts that.

5. **src/sentry/search/events/datasets/discover.py:1041-1052 — Important (reasoned, conditional).** `upsampled_count` is `toInt64(sum(sample_weight))`, and its comment assumes "sample_weight exists for all events in allowlisted projects".
   - Any error in an allowlisted project with a NULL or 0 `sample_weight` contributes 0 instead of 1. That covers events ingested before the project was allowlisted, and events from SDKs that don't send `contexts.error_sampling.client_sample_rate`. Allowlisted projects would then show undercounted charts.
   - I don't know the default for Snuba's `sample_weight` column; this is a schema question I could not check from this repo. If NULL is possible, use `sum(ifNull(sample_weight, 1))`.

6. **src/sentry/search/events/datasets/discover.py:1042-1052 — Minor.** `upsampled_count` is not marked `private=True`, unlike the internal helpers around it (for example `default_result_type="integer", private=True` at 1038). That exposes it as a public discover function any user can query on any dataset, including where `sample_weight` doesn't exist.
   - `default_result_type="number"` also changes the `count` meta type from integer to number for allowlisted orgs, even though the value is `toInt64`. Use `"integer"`.

7. **src/sentry/api/endpoints/organization_events_stats.py:220-222 — Minor.** The eligibility check gets the outer `dataset`, not the `scoped_dataset` that `_get_event_stats` actually queries. In the dashboard-split path (lines ~350-395), `_get_event_stats(discover, …, "(q) AND !event.type:transaction")` runs while `dataset` is a metrics dataset, so upsampling is silently skipped for the errors half.
   - `_is_error_focused_query` also reads `request.GET["query"]` rather than the `query` argument it is effectively judging.

8. **src/sentry/api/endpoints/organization_events_stats.py:223,234,278 and src/sentry/api/helpers/error_upsampling.py:22,28,33,36,39,49,51,84 — Minor (breaks a documented standard).** These lines have trailing whitespace. The repo CLAUDE.md says "ALWAYS use pre-commit", and `.pre-commit-config.yaml:179` has a `trailing-whitespace` hook that rejects them.
   - Failing command: `git diff --check 83f40559985e HEAD`.

9. **tests/sentry/api/helpers/test_error_upsampling.py:21 — Minor (breaks a documented standard).** `Organization.objects.create(name="test-org")` goes against the repo CLAUDE.md rule "Use `self.create_*` helpers, not direct model creation". Use `self.create_organization()`.

10. **tests/sentry/api/helpers/test_error_upsampling.py:7-11, 37-101 — Minor (breaks the user's global CLAUDE.md testing rules).** The tests import and call private helpers directly (`_are_all_projects_error_upsampled`, `_is_error_focused_query`, `_should_apply_sample_weight_transform`). That breaks "Never test internal/private functions directly".
    - The tests also patch the module's `options`, which the project owns, instead of using the `override_options` test helper (I did not open it to confirm it exists here). That breaks "Never mock things you own".
    - The public entry point `is_errors_query_for_error_upsampled_projects`, and therefore the new cache path, has no unit test at all.

## Files not reviewed

None were skipped. All 8 files in the patch were reviewed:
- `pyproject.toml`: adds two modules to the mypy list; no issue.
- `sentry-repo`: a gitlink with no content to read; covered in finding 1.
- `organization_events_stats.py`
- `error_upsampling.py`
- `datasets/discover.py`
- `testutils/factories.py`: `_set_sample_rate_from_error_sampling` is test-only; no finding.
- Both test files.

I did not check the Snuba schema for `sample_weight` (it is outside this repo), so finding 5 is conditional. Nothing was executed beyond greps and `git diff --check`.
