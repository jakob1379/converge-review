## Code review: getsentry__sentry__77754 (base bb5a6837cb5 to head 9501091c52a, 8 commits, 7 files)

Skill used: `mattpocock-skills:code-review`. I ran both axes myself and spawned no sub-agents. I read the code only and ran no tests.

**Assumptions**
- There is no spec. Commit messages reference no issue, and the only statement of intent is the first commit title, "fix(ecosystem): Breaks issue sync cycles".
- The repo documents no coding standards locally. `.github/CONTRIBUTING.md` only links to the external docs.sentry.io/internal. There is no AGENTS.md, CLAUDE.md, CODING_STANDARDS or style guide. (`.claude/` in the worktree is harness config, not repo standards.)
- So I used the in-repo conventions that are enforced or written down instead:
  - `src/sentry/celery.py` `holds_bad_pickle_object`: "do not pickle custom classes". It is turned on in tests by `testutils/pytest/sentry.py:180`.
  - The layout of `integrations/services/`.
  - The mypy config in `pyproject.toml`.
- I left the Fowler smell baseline out, as your override block asks.

## Standards

No hard breaches of a documented standard.

**Checked and compliant**
- **Celery pickle rule.** `sync_group_assignee_outbound` passes `assignment_source.to_dict()`, a plain dict with str, int and datetime, not the `AssignmentSource` object. That passes `holds_bad_pickle_object`. The serializer is `pickle` (`conf/server.py:739`), so the `datetime` in `queued` round-trips. Commits f665d925d94 and 6eb81dcbbb2 switched to this on purpose.
- **Task signature change is deploy-safe.** The new `assignment_source_dict` kwarg on `sync_assignee_outbound` defaults to `None`, so tasks queued by older code still run.
- **Override compatibility.** Every concrete `sync_assignee_outbound` takes `**kwargs`, so the new `assignment_source=` kwarg is accepted. Checked: vsts/issues.py:217, example/integration.py:152, jira/integration.py:936, jira_server/integration.py:1038.

**Minor (judgement call, convention only, nothing documented)**
- `src/sentry/integrations/services/assignment_source.py:1`
  - **Claim:** a plain dataclass sits in `integrations/services/`. The two existing packages there (`integration/`, `repository/`) are hybrid-cloud RPC services with `service.py`, `impl.py`, `model.py` and `serial.py`. This file is a value object, so the placement goes against the local layout.
  - **Evidence:** `ls src/sentry/integrations/services/`. No written rule exists in the repo, so this is low confidence.
- `src/sentry/integrations/mixins/issues.py:411-419`
  - **Claim:** the abstract `sync_status_outbound` gains an `assignment_source` parameter, but the abstract `sync_assignee_outbound` (the method that actually receives it, line 397) does not.
    - Nothing ever passes `assignment_source` to `sync_status_outbound`. The only references are at the declaration (`grep -rn assignment_source src/sentry`).
    - The status task (`tasks/sync_status_outbound.py:43`) still calls `should_sync("outbound_status")` with no source.
  - **Effect:** the abstract contract is inconsistent with its call sites.
  - **Evidence:** reasoned from the grep above. It does not fail at runtime, because the implementations take `**kwargs`.

## Spec

No spec, so this axis was skipped. Measured against the inferred intent ("break issue sync cycles"):
- Only assignee sync is protected. Inbound assign and deassign tag the source in `utils/sync.py:96-116`, and `should_sync` skips the source integration in `mixins/issues.py:388-391`.
- Status sync cycles are not addressed, apart from the unused parameter noted above.
- Without a spec, I can't say whether status was in scope.

## Outside my axes

Your override asks me to leave these out of the findings; I list them for whoever owns correctness.
- `assignment_source.py:18`: `queued: datetime = timezone.now()` runs once, at import time. Every instance gets the process start time, not the time it was queued. Use `field(default_factory=timezone.now)`.
- `assignment_source.py:32-35`: `from_dict` returns `None` silently on a malformed dict. `should_sync` then treats the call as having no source and syncs, so a bad payload fails open into the cycle this change prevents.

## Summary

- **Standards:** 0 hard breaches and 2 Minor judgement calls. The worst is the abstract `sync_status_outbound` parameter that nothing calls with.
- **Spec:** no spec, so not assessed. Status-sync cycles appear unaddressed relative to the inferred intent.

**Files not reviewed:** none. All 7 files in the patch were read, with surrounding source.

I did not check the external Sentry develop docs (network) or any mypy or test run (benchmark mode).
