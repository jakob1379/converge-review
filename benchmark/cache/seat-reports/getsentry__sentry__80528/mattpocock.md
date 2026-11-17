## Code review: getsentry__sentry__80528, "ref(crons): Reorganize incident creation / issue occurrence logic"

I found no Critical or Important issues on either axis. The patch only moves code and renames two functions; behaviour is unchanged.

Base `0cfc28e76dd` resolves and the diff is non-empty. It is one commit (`dcdcadb7711`) touching 4 files (+289/−264). I reviewed both axes myself, without sub-agents, as instructed.

### What I checked
- **Bodies are identical.** After applying the two renames, the moved function bodies match the base exactly. I extracted each function from `git show 0cfc28e76dd:src/sentry/monitors/logic/mark_failed.py` and diffed it against the new files:
  - `mark_failed_threshold` became `try_incident_threshold` in `src/sentry/monitors/logic/incidents.py`.
  - `create_issue_platform_occurrence` became `create_incident_occurrence` in `src/sentry/monitors/logic/incident_occurrence.py`.
  - Both diffs printed `IDENTICAL`.
- **Unchanged pieces.** `get_failure_reason`, `get_monitor_environment_context` and the two failure-text maps moved without change. `SimpleCheckIn` moved to `src/sentry/monitors/types.py:105`; the only addition is a docstring.
- **No stale references.** Nothing in `src/` or `tests/` still uses the old names or imports them from `mark_failed`. The `create_issue_platform_occurrence` hits under `sentry/uptime` are a different function. External callers of `mark_failed.mark_failed` are unaffected.
- **Test mocks still apply.** The tests patch `sentry.issues.producer.produce_occurrence_to_kafka`. The moved code still imports that function inside the function body, so the patches keep working.
- **No import cycle.** The chain runs one way: `mark_failed` → `incidents` → `incident_occurrence` → `models`/`types`.
- **Syntax.** All 4 files parse with `ast.parse`.

## Standards
The repo documents no coding standards I can check against. There is no CLAUDE.md, AGENTS.md or CODING_STANDARDS, and `.github/CONTRIBUTING.md` only links to the external docs.sentry.io/internal pages.

The only in-repo standard that could apply is the mypy "stronger typing" list in `pyproject.toml` (lines 377–559). No `sentry.monitors.logic.*` module is on it, so the unannotated return types on the moved functions break nothing. The other enforced rules come from linters (pre-commit, flake8, mypy), which I didn't run, so I left them out.

You asked for no generic smells, so I skipped the baseline smell checks.

**Findings: 0.**

## Spec
There is no spec. I used the commit message as the stated intent: "split out the concept of incidents into it's own logic module, as well as incident_occurrence into it's own module", because "we'll be doing more with issue occurrences".

- (a) **Missing or partial:** none. Both modules exist and `mark_failed` now calls `try_incident_threshold` (`mark_failed.py:79`).
- (b) **Scope creep:** two small changes go beyond a pure move, and both are harmless.
  - The renames themselves.
  - Moving `SimpleCheckIn` to `types.py`. This is needed to avoid an import cycle between `incidents` and `incident_occurrence`.
- (c) **Looks implemented but wrong:** none. Behaviour is unchanged.

**Minor, reasoned (not verified):** the patch removes public names from `sentry.monitors.logic.mark_failed`: `mark_failed_threshold`, `create_issue_platform_occurrence`, `SimpleCheckIn`, `get_failure_reason` and `get_monitor_environment_context`. Nothing in this repo still uses them, but I can't see downstream code such as getsentry. Any import or `mock.patch` string there pointing at the old names would break.

**Findings: 0 blocking, 1 Minor (unverifiable downstream break).**

**Summary:** Standards has 0 findings. Spec has 1 Minor finding, the downstream break above.

**Files not reviewed:** none. I reviewed all 4 files in the patch.

**Not checked:** I didn't run the tests, mypy or linters, as instructed.

**Existing bugs carried over (not counted as findings):**
- `incident_occurrence.py`, `get_monitor_environment_context`: it builds `config` with the human-readable `schedule_type`, then returns the raw `monitor.config` instead.
- The "humam readible" typo in a docstring.
- An unused `logger` in each new module.
