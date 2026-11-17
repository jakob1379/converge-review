I ran the `mattpocock-skills:code-review` skill and did both axes myself, as you asked. I used no sub-agents.

- **Spec axis:** couldn't run it, because no spec was supplied. Five commits are in range (f3b7401..bb75657): b31aefd, 0b8cf7c, 7aa8911, 8c68d5b, bb75657. Their messages ("add oauth2 login step in pipeline; check for the user match at the end of pipeline") are the only statement of intent. I did not treat them as a spec.
- **Standards axis:** the repo documents almost nothing a person has to apply by hand. Formatting, imports, lint and types are left to tools, so I didn't re-check those. Within that, I found no hard breach of a documented standard.

## Findings

1. **src/sentry/integrations/github/integration.py:141** (call sites at :471 and :488). Minor (Standards).
   - **Claim:** `_(error_short)` passes a variable to gettext, so `makemessages` can no longer extract the short error strings.
   - **Evidence:**
     - Before the patch, the strings were literal: `_("GitHub installation pending deletion.")` and `_("Github installed on another Sentry organization.")`.
     - The repo's translation workflow is `sentry django makemessages` (Makefile:61, the `merge-locale-catalogs` target).
     - The existing catalogs contain these strings, e.g. `grep -rl "GitHub installation pending deletion" src/sentry/locale` matches ro_RO, zh_CN, uk and others.
     - After the patch, the call sites pass plain strings. Those translations will drop out on the next catalog rebuild. The new default "Invalid installation request." is never extractable.
   - Reasoned; there's no failing command. It's a workflow convention rather than a written rule.

2. **tests/sentry/integrations/github/test_integration.py:379-396** (`test_installation_not_found`). Important (outside my seat: test integrity, not spec or standards).
   - **Claim:** the test no longer reaches the "installation not found" path. It passes because the state check fails.
   - **Evidence:**
     - It sends `state=ddd023d87a913d5226e2a882c4c4cc05`, while every other test uses the pipeline signature `9cae5e88803f35ed7970fc131e6e65d3`.
     - So `OAuthLoginView.dispatch` returns `error()` at integration.py:412-413 before `build_integration` runs.
     - The old assertion `b"The GitHub installation could not be found."` was replaced with the generic `b"Invalid installation request."`.
     - The 404 → `IntegrationError` branch of `build_integration` is now untested, although the test's name says that's what it checks.
   - Reasoned; I didn't run tests (benchmark mode). Changing the state to `9cae5e88...` should make it reach the 404 path.

3. **src/sentry/integrations/github/integration.py:503**. Important (outside my seat: correctness).
   - **Claim:** `integration.metadata["sender"]["login"]` raises `KeyError` when the Integration's metadata has no `sender`. That gives a 500 instead of the error page.
   - **Evidence:**
     - `build_integration` adds `sender` only `if state.get("sender")` (integration.py:376-377).
     - The repo's own test asserts that an Integration created through the pipeline has no `sender` key (test_integration.py:302-308).
     - installation.py:44 guards this exact case: `if "sender" not in integration.metadata`.
     - Path: the Integration exists and is ACTIVE, has no OrganizationIntegration, and was created through the pipeline. A reinstall then crashes.
   - Reasoned.

4. **src/sentry/integrations/github/integration.py:404-408**. Minor (outside my seat).
   - **Claim:** the authorize URL is built with an f-string, so `redirect_uri` and the other parameters are not URL-encoded. Similar views build query strings with `urlencode`.
   - **Evidence:** the test at test_integration.py:233-236 asserts the unencoded `redirect_uri=http://testserver/extensions/github/setup/`, which locks the raw form in.
   - Reasoned; it doesn't break anything today.

The `pipeline_advancer.py` change only inlines `FORWARD_INSTALL_FOR` as `provider_id == "github"` (pipeline_advancer.py:41). Nothing else references `FORWARD_INSTALL_FOR` in src or tests. No issue there.

## Standards docs found
- `.github/CONTRIBUTING.md`: no rules; it links to https://docs.sentry.io/internal/, which I didn't fetch (offline).
- `.github/PULL_REQUEST_TEMPLATE.md`: legal boilerplate only.
- Tool configs, enforced by tools and not re-checked:
  - `.pre-commit-config.yaml`: pyupgrade, black, isort, flake8, mypy, check-mypy-bypass, name-tests-test, among others.
  - `tools/flake8_plugin.py`: rules S002–S011. The patch follows S003; the test uses `from sentry.utils import json`.
  - `pyproject.toml [tool.mypy]`: `sentry.integrations.github.integration` is on the "typing issues" `ignore_errors` list (line 307), so the untyped `error()` / `dispatch(..., pipeline)` arguments break no rule.
- `Makefile:61`: the makemessages translation workflow, used for finding 1.
- No CLAUDE.md, AGENTS.md or CODING_STANDARDS in the repo. The `.claude/` folder is untracked user environment, not repo standards.

## Unreviewed files
None. I reviewed all 3 files in the patch: `src/sentry/integrations/github/integration.py`, `src/sentry/web/frontend/pipeline_advancer.py` and `tests/sentry/integrations/github/test_integration.py`.

Not checked: the external docs.sentry.io/internal standards; whether the hard-coded state `9cae5e88...` is stable across environments; I ran no tests. Findings 2 and 3 fall outside the spec/standards seat but carry the real risk.
