## Review of change.patch (base 83f40559..HEAD): error upsampling in events-stats

I ran it through OCR delegate mode. `ocr delegate preview --from 83f40559 --to HEAD` found 8 files, of which 6 are reviewable; it excluded the 2 test files by default path. I pulled the rules with `ocr delegate rule` and did the review by hand against the surrounding source. I made no edits, installed nothing and ran no tests. Every claim below is **reasoned** from reading the source; none comes from a test run.

### Findings

**1. src/sentry/api/helpers/error_upsampling.py:137 — Important**
- **Claim:** `_is_error_focused_query` uses a substring match, so negated and mixed queries turn on upsampling for transaction data.
- **Evidence:** `"event.type:error" in query` is true for `!event.type:error` and for `event.type:error OR event.type:transaction`. With the discover dataset (the default), every `count()` then becomes `toInt64(sum(sample_weight))` across transactions as well. The case is wrong exactly where the docstring says it "errs on the side of caution".
- **Failing test (reasoned, not run):**
  ```python
  self.request.GET = QueryDict("query=!event.type:error")
  assert _is_error_focused_query(self.request) is False
  ```
  On the patched code this returns True.

**2. src/sentry/api/endpoints/organization_events_stats.py:220-222 — Important**
- **Claim:** The eligibility check looks at the wrong inputs: the outer `dataset` and `request.GET["query"]`. It should use the `scoped_dataset` and `query` that `_get_event_stats` actually receives.
- **Evidence:** On the dashboard split path (lines ~344-440), `metrics_enhanced` is true, so the outer `dataset` is a metrics dataset. `_should_apply_sample_weight_transform` returns False for metrics datasets. As a result, ERROR_EVENTS widget splits never upsample, even though they run against `discover` with `!event.type:transaction`. The reverse also happens: the decision is made once from the raw request query, so the transactions-only split call (`... AND event.type:transaction`) is still marked for upsampling when the user's query contains `event.type:error`.

**3. src/sentry/api/helpers/error_upsampling.py:95, together with organization_events_stats.py `transform_alias_to_input_format` — Important**
- **Claim:** With `transformAliasToInputFormat=1`, an upsampled request returns zero counts.
- **Evidence:**
  - `process_results` (src/sentry/search/events/builder/base.py:1566-1572) renames each result column to `function_details.field`, which is now the literal `"upsampled_count() as count"`.
  - `resolve_axis_column` (src/sentry/api/bases/organization_events.py:75) looks the column up as `"count()"`.
  - The serializer then does `r.get(column, 0)` (src/sentry/api/serializers/snuba.py:92), which gives silent zeros, not an error.
- **Failing test (reasoned, not run):** add `"transformAliasToInputFormat": "1"` to `test_error_upsampling_with_allowlisted_projects`. The bucket counts come back as 0 instead of 10.

**4. sentry-repo (gitlink, new) — Important**
- **Claim:** A stray nested repository is committed as a submodule with no mapping.
- **Evidence:** `git ls-tree HEAD sentry-repo` shows `160000 commit a5d29095...`, and `git show HEAD:.gitmodules` fails: ".gitmodules ... not in 'HEAD'". `git submodule` commands will fail with "no submodule mapping found". This looks like an accidental commit.
- **Command:** `git --no-pager show HEAD:.gitmodules` exits 128.

**5. src/sentry/api/helpers/error_upsampling.py:27-38 — Minor**
- **Claim:** The "performance optimization" cache probably makes things slower and adds staleness.
- **Evidence:**
  - `options.get` is already served from an in-process cache. This swaps that for a round trip to the Django cache (the network cache in production) on every events-stats request.
  - The call also runs before the cheap dataset check (organization_events_stats.py:220), so transactions, metrics and spans requests pay for it too.
  - The allowlist is a global option, but results are cached per org for 60s and nothing invalidates them.
  - The docstring at line 50 ("reads the allowlist configuration fresh each time ... intentional") is now false.

**6. src/sentry/api/helpers/error_upsampling.py:67-74 — Minor**
- **Claim:** `invalidate_upsampling_cache` is dead code. Nothing in `src/` calls it, and no option-change hook triggers it.

**7. src/sentry/api/endpoints/organization_events_stats.py:275-277 — Minor**
- **Claim:** This upsampling branch can never run.
- **Evidence:** `use_rpc` requires `dataset in {spans_rpc, ourlogs}`, and `_should_apply_sample_weight_transform` returns False for both. The same holds for the RPC branch inside top events (line 232 combined with 236). EAP RPC has no `upsampled_count` function anyway.

**8. src/sentry/api/helpers/error_upsampling.py:22,28,33,36,39,49,84 and organization_events_stats.py:223,234,278 — Minor (documented standard)**
- **Claim:** These lines are whitespace-only, which breaks the repo's pre-commit (black / flake8 W293). CLAUDE.md says "ALWAYS use pre-commit".
- **Command:** `grep -nP '^\s+$' src/sentry/api/helpers/error_upsampling.py` returns those lines.

**9. src/sentry/testutils/factories.py:344-357, called at 1049 — Minor**
- **Claim:** The test factory sets `sample_rate` without the gating that production applies, so tests stop matching real behaviour.
- **Evidence:**
  - Production `_derive_client_error_sampling_rate` (src/sentry/event_manager.py:774) applies only to allowlisted projects, numeric values and the range 0 < x ≤ 1.
  - The factory helper applies to every project, accepts strings, values above 1 and negative values, and silently swallows exceptions with `except Exception: pass`.
  - So every `store_event` that carries an `error_sampling` context gets a `sample_rate` in any test.

**10. tests/sentry/api/helpers/test_error_upsampling.py:21 — Minor (documented standard)**
- **Claim:** The test uses `Organization.objects.create(...)`.
- **Evidence:** CLAUDE.md "Common Gotchas #7" says to use `self.create_*` helpers, not direct model creation.
- **Also:** the tests import only private functions. The public cached entry point `is_errors_query_for_error_upsampled_projects` and the cache behaviour have no tests at all.

### Not reported, could not verify
I did not flag `upsampled_count` (src/sentry/search/events/datasets/discover.py:1042-1051) summing `sample_weight` with no null or default handling. Whether that undercounts depends on Snuba's errors processor defaulting `sample_weight` to 1, and that code is not in this repo.

### Coverage
total_files: 8, reviewed_files: 8, skipped_files: 0, coverage_rate: 100%.
- `pyproject.toml`: reviewed. It adds the new module and its test to the strict mypy list; no issue.
- `sentry-repo`: reviewed as a gitlink only. OCR could not read it at HEAD, and there is no tree content to review.
- `src/sentry/api/endpoints/organization_events_stats.py`: reviewed. The error-message fix at line 124 is fine.
- `src/sentry/api/helpers/error_upsampling.py`: reviewed.
- `src/sentry/search/events/datasets/discover.py`: reviewed. The errors builders use `DiscoverDatasetConfig`, so the function resolves for the errors dataset.
- `src/sentry/testutils/factories.py`: reviewed.
- `tests/sentry/api/helpers/test_error_upsampling.py` and `tests/snuba/api/endpoints/test_organization_events_stats.py`: OCR excluded both (default_path). I reviewed them by hand only for documented-standard breaches and coverage gaps; I did not review their logic line by line.

No spec was given, so there are no spec gaps to report.
