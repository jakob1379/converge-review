## Review: getsentry__sentry__77754 (base bb5a6837 → head 9501091c52a)

I loaded the `open-code-review:delegate-review` skill. OCR preview ran in range mode and reported 7 files, 5 of them reviewable (the 2 test files are excluded by OCR's `default_path`). I pulled the OCR Python rules and reviewed the whole pinned patch, test files included, reading the surrounding source for context. The override applied: report only, no fixes, no agents. There is no spec, so I found no spec gaps.

### Findings

**1. src/sentry/integrations/services/assignment_source.py:18 — Important**
- **Claim:** `queued: datetime = timezone.now()` runs once, when the class is defined at import time. Every `AssignmentSource` in a process gets the same `queued` value: the time the module was imported, not the time the assignment was queued. The field never records what its name says. That value is then serialised into every `sync_assignee_outbound` task through `to_dict()` (sync.py:141).
- **Evidence:** In Python a dataclass default expression is evaluated once, at class creation. The fix is `field(default_factory=timezone.now)`. The new `test_to_dict` (test_assignment_source.py:30-38) only checks `queued is not None`, so it passes despite the bug.
- **Failing test (reasoned, not run):** the sandbox has no Django and benchmark mode bars running the suite. This would fail on the patched code:
  ```python
  def test_queued_is_per_instance(self):
      with freeze_time("2024-01-01"):
          a = AssignmentSource(source_name="a", integration_id=1)
      with freeze_time("2024-01-02"):
          b = AssignmentSource(source_name="b", integration_id=2)
      assert a.queued != b.queued
  ```
- **Impact today:** nothing reads `queued` yet, so no current behaviour is wrong. Any future staleness or loop check based on this timestamp would be silently broken.

**2. src/sentry/integrations/mixins/issues.py:411-418 — Minor**
- **Claim:** The new `assignment_source` parameter on the abstract `sync_status_outbound` is dead. No caller passes it: `tasks/sync_status_outbound.py` still calls `should_sync("outbound_status")` with no source. No implementation reads it either (jira, jira_server, vsts, example).
- **Consequences:**
  - Status sync gets no loop protection from this change, despite the signature suggesting it does.
  - `ExampleIntegration.sync_status_outbound` (example/integration.py:161) takes no `**kwargs`, so it would raise `TypeError` if anyone started passing the argument.
- **Evidence:** a grep over `src/` finds no call site that passes `assignment_source` to `sync_status_outbound`.

**3. tests/sentry/integrations/services/test_assignment_source.py:13 — Minor**
- **Claim:** Test name typo: `test_from_dict_inalid_data` should be `invalid`. This falls under the OCR typo rule for names at their declaration site.

### Checked and found sound
- **Every `sync_assignee_outbound` implementation accepts `**kwargs`** (jira, jira_server, vsts, example, plus the mixin's abstract method), so the new `assignment_source=` keyword in the task cannot raise `TypeError`.
- **No subclass overrides `should_sync`.** The other callers (`tasks/__init__.py`, `sync_status_outbound`, `where_should_sync`) use the positional single argument and still work.
- **The task kwargs serialise fine.** Celery uses pickle (`CELERY_TASK_SERIALIZER = "pickle"`). A plain dict holding str, int and datetime passes `holds_bad_pickle_object`, because the dataclass is converted to a dict before enqueueing.
- **No ping-pong across integrations.** `GroupAssignee.assign` does nothing (`affected=False`) when the assignee is unchanged, so an echo from integration A → Sentry → B → Sentry stops there. The `integration_id` comparison in `should_sync` correctly lets the change reach the other integrations.
- **`from_dict({})` and unknown keys** raise `TypeError` and return `None` as intended. The import at the top of `groupassignee.py` adds no import cycle, because `assignment_source.py` imports only django and the stdlib at runtime.

### Coverage
- total_files: 7, reviewed_files: 7, skipped_files: 0, coverage_rate: 100%.
  - `src/sentry/integrations/mixins/issues.py` (modified): reviewed
  - `src/sentry/integrations/services/assignment_source.py` (added): reviewed
  - `src/sentry/integrations/tasks/sync_assignee_outbound.py` (modified): reviewed
  - `src/sentry/integrations/utils/sync.py` (modified): reviewed
  - `src/sentry/models/groupassignee.py` (modified): reviewed
  - `tests/sentry/integrations/services/test_assignment_source.py` (added): reviewed. OCR excluded it (`default_path`), but the override asked for the whole patch.
  - `tests/sentry/models/test_groupassignee.py` (modified): reviewed, same reason.

Nothing was executed: Django is not installed in the sandbox and benchmark mode forbids running the suite. Finding 1 rests on how Python evaluates dataclass defaults. The proposed failing test was not run.
