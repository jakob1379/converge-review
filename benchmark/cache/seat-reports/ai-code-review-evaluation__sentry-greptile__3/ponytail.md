Over-engineering review of `change.patch`, done with the `ponytail:ponytail-review` skill. I reviewed for over-engineering and documented-standard breaches only. There was no spec, so I report no spec gaps. Nothing was edited and no tests were run.

**What this change does:** It changes the events-stats endpoint so that `count()` becomes `upsampled_count()` (which computes `sum(sample_weight)`) when every queried project is on the `issues.client_error_sampling.project_allowlist` option and the query is about errors. The patch adds a helper module with a 60-second Django cache, a new SnQL function in the discover dataset, a test-factory hook that sets `sample_rate`, and both unit and endpoint tests.

Assumed load: a Sentry SaaS endpoint with high traffic, served by many processes.

## Should fix

1. **The 60-second cache is slower than what it replaces, and it serves stale answers** (`src/sentry/api/helpers/error_upsampling.py:27-40`, plus `:67-74`). Severity: Important.
   - **What this is:** A shared cache (memcached or redis) wraps the allowlist check "to avoid expensive repeated option lookups".
   - **Problem:** The option lookup is not expensive. `options.get` already uses a per-process local cache (`src/sentry/options/store.py:123-152`, `get_cache` and `get_local_cache`). So the new layer swaps an in-memory dict lookup for a network round trip on every request. It does this before the cheap dataset check, so it also runs for transactions and spans queries, which can never upsample.
   - **Stale answers:** The cache key does not include the allowlist. After a project is removed from the allowlist, its counts stay upsampled for up to 60 seconds.
   - **Dead invalidation function:** `invalidate_upsampling_cache` is meant to handle that, but nothing calls it. `grep -rn invalidate_upsampling_cache src tests` finds only the definition.
   - **Self-contradiction:** The docstring of `_are_all_projects_error_upsampled` (`:50-53`) says the function reads the allowlist "fresh each time … intentional". The cache in front of it defeats exactly that.
   - **Fix:** Delete the cache code and `invalidate_upsampling_cache` (about 20 lines). The body becomes `return _should_apply_sample_weight_transform(dataset, request) and _are_all_projects_error_upsampled(snuba_params.project_ids, organization)`.
   - **Evidence (reasoned, not run):** This test would fail on the patched code. Inside one test, call the function with `self.options({"issues.client_error_sampling.project_allowlist": [p.id]})`, then call it again with the allowlist set to `[]`. The second call still returns True because of the cache.

2. **The test-factory hook copies production logic without its checks and changes every `store_event` in the test suite** (`src/sentry/testutils/factories.py:344-357`, `:1049`). Severity: Important.
   - **What this is:** `_set_sample_rate_from_error_sampling` copies `contexts.error_sampling.client_sample_rate` into `sample_rate` for every stored event.
   - **Problem:** It is a near-copy of `_derive_client_error_sampling_rate` (`src/sentry/event_manager.py:774-799`), minus the allowlist check, the 0-1 range check and the type check. It also has two bare `except Exception: pass` blocks.
   - **Why it exists:** The endpoint tests mock `sentry.api.helpers.error_upsampling.options` instead of setting the real option. So at ingest the real allowlist is empty and production never sets `sample_rate`. The factory hook papers over that.
   - **Side effect:** Every test that stores an event with an `error_sampling` context now gets a `sample_rate` that production would not set.
   - **Fix:** Delete the helper, its call site and the `MutableMapping` import (about 18 lines). In `tests/snuba/api/endpoints/test_organization_events_stats.py`, wrap the stores and requests in `with self.options({"issues.client_error_sampling.project_allowlist": [...]})`. This is the pattern `tests/sentry/event_manager/test_event_manager.py:2881` already uses. It also removes the four `@mock.patch(...options)` decorators (`:3603`, `:3627`, `:3652`, `:3696`), which mock a module Sentry owns.
   - **Evidence:** Reasoned.

3. **A stray git submodule pointer is added at the repo root** (`sentry-repo`, a new gitlink to commit `a5d29095…`). Severity: Important.
   - **Problem:** Nothing in the change uses it. It looks like a local clone that was committed by accident.
   - **Fix:** `git rm --cached sentry-repo`.
   - **Evidence:** `git diff 83f40559 -- sentry-repo` shows a new 160000-mode entry.

4. **The endpoint repeats the same transform three times, behind a variable that only renames another** (`src/sentry/api/endpoints/organization_events_stats.py:218-233`, `:275-277`, `:294-296`). Severity: Minor.
   - **Problem:** `upsampling_enabled = should_upsample` is just a second name. The same `if upsampling_enabled: final_columns = transform(...)` block appears in all three mutually exclusive branches.
   - **False comments:** The comments claim benefits that do not exist: "late transformation ensures we use the most current schema assumptions", "allows for better query optimization and caching". The transform is a pure function of `query_columns`.
   - **Fix:** One statement before the branches:
     `final_columns = transform_query_columns_for_error_upsampling(query_columns) if is_errors_query_for_error_upsampled_projects(snuba_params, organization, dataset, request) else query_columns`
     This saves about 15 lines.

5. **The unit tests call private functions directly and create the organization directly** (`tests/sentry/api/helpers/test_error_upsampling.py:7-11`, `:21`). Severity: Minor.
   - **Problem:** The file imports and asserts on `_are_all_projects_error_upsampled`, `_is_error_focused_query` and `_should_apply_sample_weight_transform`. The user's global CLAUDE.md says to test contracts only and never private functions.
   - **Repo standard breach:** It uses `Organization.objects.create(...)`. The repo's `CLAUDE.md` ("Common Gotchas" #7) says to use `self.create_*` helpers instead. `self.snuba_params` and `self.project_ids` are also built partly for nothing.
   - **Redundant:** The endpoint tests already cover allowlisted, partial, none and transaction cases through the public API.
   - **Fix:** Keep only `test_transform_query_columns_for_error_upsampling`, since that function is public and handles case and whitespace edge cases. Delete the rest, about 70 lines.

## Nice to have

6. **Leftover bloat in the helper module** (`src/sentry/api/helpers/error_upsampling.py`). Severity: Minor.
   - `:59-60` `if not allowlist: return False` is redundant. With an empty allowlist and non-empty `project_ids`, `all(...)` already returns False.
   - `:63-64` and `:123-124` follow the `result = …; return result` pattern. Return the expression directly.
   - `:136-140` the if/return True/return False can be `return "event.type:error" in request.GET.get("query", "").lower()`.
   - `:58` `options.get(key, [])` passes `[]` as the `silent` argument, not as a default (`src/sentry/options/manager.py:285`). The option is already registered with `default=[]` (`src/sentry/options/defaults.py:3463-3468`). Drop the `[]`.
   - `:43-45` the `organization` parameter of `_are_all_projects_error_upsampled` is unused once the cache is gone.
   - `:103` types `dataset: Any`, while the public function types the same thing as `ModuleType`.

Verdict: fix 1, 2 and 3 first.
Lean: about -130 lines possible (cache and invalidation about 25, factory hook about 18, endpoint about 15, unit tests about 70, small helper trims about 8).

**Files not reviewed:** None skipped. Three files were checked only for lean and standards, not correctness:
- `pyproject.toml`: mypy module-list additions, nothing to flag.
- `src/sentry/search/events/datasets/discover.py`: the new `upsampled_count` SnQL function is minimal.
- `tests/snuba/api/endpoints/test_organization_events_stats.py`: covered in finding 2.

Not checked: correctness outside this lens (for example the `upsampled_count() as count` alias in the top-events and RPC paths, and the `default_result_type="number"` choice). I could not read `.gitmodules` (permission denied), so I could not confirm whether `sentry-repo` is also registered there.
