I reviewed the patch with `mattpocock-skills:code-review`. Your override replaced two of the skill's steps: I ran no sub-agents, and I left out the skill's code-smell baseline. The base is 83f40559985e and the head is 6ad6fe3899. That range holds two commits, 4cb317c5be and 6ad6fe3899, which change 8 files.

## Standards
I checked the patch against the repo's CLAUDE.md and its `.pre-commit-config.yaml`. Where a rule comes from your global `~/.claude/CLAUDE.md` instead, I say so.

1. **src/sentry/api/helpers/error_upsampling.py:22,28,33,36,39,49,51,84 and src/sentry/api/endpoints/organization_events_stats.py:223,234,278** — Minor, but it will fail CI.
   - **Claim:** these lines have trailing whitespace. That breaks the repo rule "ALWAYS use pre-commit for linting", because the `trailing-whitespace` hook at `.pre-commit-config.yaml:179` rejects it.
   - **Evidence:** `grep -nP "[ \t]+$" src/sentry/api/helpers/error_upsampling.py src/sentry/api/endpoints/organization_events_stats.py` lists all 11 lines. `pre-commit run trailing-whitespace --files <those two files>` should fail. I did not run it, because pre-commit rewrites the files.

2. **tests/sentry/api/helpers/test_error_upsampling.py:21** — Minor, a clear breach of a written rule.
   - **Claim:** the test creates its organization with `Organization.objects.create(name="test-org")`. The repo says "Tests: Use `self.create_*` helpers, not direct model creation" (Common Gotchas #7) and "Use factories for test data".
   - **Evidence:** the line itself. `self.create_organization(...)` is available, since this is a `TestCase`.

3. **src/sentry/api/endpoints/organization_events_stats.py:218-221 and src/sentry/api/helpers/error_upsampling.py:58** — Minor, a judgement call.
   - **Claim:** this changes what `count()` returns on a public endpoint. It is gated only by the option allowlist `issues.client_error_sampling.project_allowlist`, with no `features.has(...)` check. The repo says "Feature Flags: Always add for new features" and "Add feature flags for experimental features".
   - **Evidence:** the patch adds no feature flag. An option-based allowlist is a common Sentry pattern, so this is a deviation from the written rule, not a hard defect.

4. **tests/sentry/api/helpers/test_error_upsampling.py:7-12, 37-38** — Minor. This rule comes from your global CLAUDE.md, not the repo's.
   - **Claim:** the test imports and tests four private functions directly: `_are_all_projects_error_upsampled`, `_is_error_focused_query`, `_should_apply_sample_weight_transform` and `transform_*`. It also patches `options`, which is code Sentry owns. Your rules say "Never test internal/private functions directly" and "Never test mocks of things you own".
   - **Evidence:** the import block, and `@patch("sentry.api.helpers.error_upsampling.options")`.

## Spec
No spec was provided, so I skipped this axis. Two changes look unrelated to the upsampling feature:

5. **sentry-repo (repo root, new gitlink, mode 160000)** — Important.
   - **Claim:** the patch adds a stray submodule pointing at a5d290951def. HEAD has no `.gitmodules` entry for it, so this is almost certainly an accident.
   - **Evidence:** the patch shows `new file mode 160000` for `sentry-repo`. `git show HEAD:.gitmodules` returns "exists on disk, but not in 'HEAD'". `git ls-tree HEAD sentry-repo` shows the gitlink.

6. **src/sentry/api/endpoints/organization_events_stats.py:124** — Minor.
   - **Claim:** the error message text changes ("If topEvents needs" becomes "topEvents needs"). The fix is harmless but outside the feature.

## Problems outside the two axes (not scored, reasoned only)
These are correctness problems, not standards breaches.

- **error_upsampling.py:137** — the check is a plain substring match, `"event.type:error" in query`. So `!event.type:error`, a query that excludes errors, still counts as error-focused, and its `count()` gets upsampled when querying the discover dataset.
- **error_upsampling.py:27-38 against 50-53** — the docstring promises a fresh allowlist read on every call, but the result is now cached for 60s. Removing a project from the allowlist therefore takes up to 60s to apply.
- **error_upsampling.py:67** — `invalidate_upsampling_cache` has no callers anywhere in `src/` (checked with grep).

## Files not reviewed
- I reviewed all 8 files in the patch. `pyproject.toml` only adds the two new modules to a mypy list, which matches the existing pattern.
- I did not inspect the contents of the `sentry-repo` submodule. It is a gitlink, and its directory in the checkout is empty.

## Summary
- **Standards:** 4 findings. The worst is the trailing whitespace, which blocks pre-commit.
- **Spec:** skipped because there is no spec. Of the 2 unrelated changes, the worst is the stray `sentry-repo` submodule.
- **Not checked:** I ran no tests or pre-commit hooks, so the failure claims are reasoned, apart from the grep evidence.
- **Biggest risk:** the negated-query bug at line 137, which falls outside both axes.
