What this change does: when an integration such as Jira tells Sentry to assign or unassign an issue, Sentry now records which integration made that change (`AssignmentSource`). It sends that record through the outbound Celery task as a plain dict, and `should_sync` refuses to push the assignment back to the integration it came from. This breaks the A → Sentry → A sync loop, and the change still goes out to other integrations.

Assumptions: there is no spec, so I judged the patch against its apparent goal, which is to stop assignee sync loops. Expected load is Sentry production, with many workers and many orgs. Review focus: over-engineering only.

Core logic checks out. I checked these points against the code:
- Every `sync_assignee_outbound` implementation accepts `**kwargs`: vsts/issues.py:217, example/integration.py:152, jira/integration.py:936, jira_server/integration.py:1038 and the mixin. The new `assignment_source=` kwarg breaks none of them.
- The `to_dict`/`from_dict` round trip is needed and is not ceremony. `src/sentry/celery.py:55` rejects pickling any `sentry.*` class ("do not pickle custom classes"), so a dict is the right way to send it.
- An assignment that doesn't change anything does not trigger an outbound sync again (`groupassignee.py:160-169`, where `affected` is False). So the cross-integration case A → Sentry → B → Sentry stops at Sentry.

**Should fix**

1. **`queued` gets its default once, at import time, and nothing reads it** (`src/sentry/integrations/services/assignment_source.py:18`), Minor
   - What this is: `queued: datetime = timezone.now()` is the default for a dataclass field.
   - Problem: Python evaluates a default once, when the class is defined, not on each new instance. Every `AssignmentSource` a worker creates gets that worker process's start time, so the "queued" timestamp is wrong from the first call. Nothing in src/ reads `queued` (grep: its only uses are the class and `test_to_dict`'s `result.get("queued") is not None`, which passes despite the bug).
   - Evidence: this is reasoned, not run, because running Django tests is off-limits. The plain-Python equivalent shows it: `python3 -c "from dataclasses import dataclass,field;from datetime import datetime;import time;\n@dataclass\nclass A:\n  q: datetime = datetime.now()\na=A();time.sleep(1);b=A();print(a.q==b.q)"` prints `True`.
   - Fix: delete the field, along with the `datetime`/`timezone` imports and the `queued` assertion in the test. If it is really wanted, use `field(default_factory=timezone.now)`.
   - If we skip it: the first person who logs or compares `queued` gets stale times without any error.

2. **Unused `assignment_source` parameter on the abstract `sync_status_outbound`** (`src/sentry/integrations/mixins/issues.py:410-418`), Minor
   - What this is: the abstract method grew from one line to seven to add `assignment_source: AssignmentSource | None = None`.
   - Problem: no caller passes it. `tasks/sync_status_outbound.py` doesn't, and none of the concrete implementations declare it (jira:990, jira_server:1090, vsts:266, example:161). This is status sync, not assignee sync, so it is a speculative hook for a feature this PR doesn't build.
   - Fix: revert to `def sync_status_outbound(self, external_issue, is_resolved, project_id, **kwargs):`.
   - If we skip it: the abstract contract advertises a loop guard for status sync that does not exist.

**Nice to have**

3. **`source_name` is carried around but never read** (`assignment_source.py:16`, `:23`), Minor
   - What this is: a string copied from `integration.name` into every task payload.
   - Problem: the only consumer, `should_sync`, compares just `integration_id`, and grep finds no reader of `source_name` outside the class.
   - Fix: drop it, or keep it only if someone is about to log it.
   - If we skip it: very little cost, just a bit of dead data in each task payload.

No Critical or Important findings.

Not reported, because I judged them correct or noise:
- `from_dict` returns None on bad input. Its only producer is `to_dict`, and the fallback just means the old behavior, so it is a safe degradation.
- Deassign with a matching source has no dedicated test. The assign path has one (`test_assignee_sync_outbound_assign_with_matching_source_integration`), and both paths share `should_sync`.

Verdict: Ship. Findings 1 and 2 are cheap cleanups worth doing before merge.
Lean: -10 lines possible: about 6 for `queued` plus imports plus test line, 6 for the `sync_status_outbound` signature, 2 for `source_name`.

Files reviewed: all 7 in the patch (mixins/issues.py, services/assignment_source.py, tasks/sync_assignee_outbound.py, utils/sync.py, models/groupassignee.py, tests/.../test_assignment_source.py, tests/sentry/models/test_groupassignee.py). None skipped.

Not checked: I did not run the tests (benchmark mode), so the `queued` behaviour comes from reasoning plus the plain-Python equivalent, not from running the patched module. I also did not check GitHub or GitLab, because they have no `sync_assignee_outbound` implementation in src/ for this patch to break.
