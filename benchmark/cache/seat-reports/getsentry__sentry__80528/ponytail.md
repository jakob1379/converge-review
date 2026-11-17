## Review of the patch (role: over-engineering only)

**What this change does:** It moves `mark_failed_threshold` out of `src/sentry/monitors/logic/mark_failed.py` into a new `logic/incidents.py` and renames it `try_incident_threshold`. It moves `create_issue_platform_occurrence` into a new `logic/incident_occurrence.py` and renames it `create_incident_occurrence`. It also moves the `SimpleCheckIn` TypedDict into `monitors/types.py`. `mark_failed` now calls `try_incident_threshold`.

**Checks:**
- The moved code is unchanged. I diffed both function bodies against the base `0cfc28e76dd`. Apart from the renames and the blank-line boundary, they are byte-identical (`SAME_OCC` for the occurrence half, and only the boundary differs for the threshold half).
- No callers are left behind. I grepped `src` and `tests` for every old name. The only `create_issue_platform_occurrence` hits are the separate uptime function in `src/sentry/uptime/issue_platform.py`. External code only imports `mark_failed`, and its signature did not change.
- Tests still mock the right thing. They patch `sentry.issues.producer.produce_occurrence_to_kafka`, which is the defining module, so the move does not break them. Both moved functions still import it inside the function.
- No import cycle is added. `types.py` does not import `monitors.models`.
- Splitting into two files is a split by job (the threshold/incident decision vs. building the Kafka payload). It adds no new abstraction, options or layers, so it is not over-engineering.

**Findings**

**Nice to have**

1. **Unused loggers copied into both new files** (`src/sentry/monitors/logic/incidents.py:3,11`, `src/sentry/monitors/logic/incident_occurrence.py:3,25`). Severity: Minor.
   - **What this is:** Each new module has `import logging` and `logger = logging.getLogger(__name__)`.
   - **Problem:** Neither file uses `logger`. The original `mark_failed.py` logger was already unused (`grep -n logger` finds only the definition at `mark_failed.py:11`). The patch now carries three copies of dead code instead of one.
   - **Fix:** Delete the two lines in each new file, and the one in `mark_failed.py` too if you like.
   - **If we skip it:** Only noise. Nothing breaks.

2. **Dead `config` variable moved along unchanged** (`src/sentry/monitors/logic/incident_occurrence.py`, start of `get_monitor_environment_context`). Severity: Minor, existed before this patch.
   - **What this is:** The code makes `config = monitor.config.copy()` and swaps in the display name for `schedule_type`. It then returns `"config": monitor_environment.monitor.config`, the raw dict.
   - **Problem:** The copy and the swap are never used. Either the return should use `config`, or the three lines should go. A refactor that only moves code may keep this on purpose, so I note it rather than flag it.
   - **Fix:** Return `"config": config`. That changes behavior, so it belongs in a separate commit. The other option is to delete the three lines.
   - **If we skip it:** The monitor context sent in the event keeps the raw `schedule_type` integer, as it does today.

Verdict: Ship.
Lean: about -7 lines possible (4 from the unused loggers, 3 from the dead `config` lines).

**Files not reviewed:** none. All 4 files in the patch were reviewed: `logic/incident_occurrence.py`, `logic/incidents.py`, `logic/mark_failed.py` and `monitors/types.py`.

**Not checked:** I did not run the tests, as instructed. My conclusion that this is a pure move comes from the text diff against the base, not from running anything. No spec was provided, so I judged the change against its commit title only.
