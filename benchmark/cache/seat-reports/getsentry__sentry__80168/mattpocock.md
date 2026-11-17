Review of change.patch (base bdd229e3f22..HEAD 8422030ef45, 2 commits). I reviewed everything myself, without sub-agents. I ran no tests: there is no venv or installed sentry environment, so every claim below is reasoned from the source.

## Standards

Documented standards in this repo: the root has no CLAUDE.md, AGENTS.md or CODING_STANDARDS. `.github/CONTRIBUTING.md` only points to the external docs.sentry.io/internal page. The rest is tooling config: `.pre-commit-config.yaml` (black, isort, flake8, mypy, pyupgrade, python-use-type-annotations, name-tests-test) and the mypy "stronger typing" list in `pyproject.toml:378-560`. workflow_engine and incidents are not on that list. I found no breach of a documented standard; formatting and typing are left to tooling.

Judgement calls from the smell baseline (labelled heuristics, not violations):

1. **src/sentry/incidents/grouptype.py:10-12. Minor. Stale comment that now contradicts the code.**
   - The comment still says `# TODO: This will be a stateful detector when we build that abstraction`.
   - The class directly below it now subclasses `StatefulDetectorHandler`.

2. **src/sentry/workflow_engine/processors/detector.py:229-233. Minor. Stale docstring.**
   - `evaluate` still says it "returns a list of `DetectorEvaluationResult`".
   - The patch changed the return type to `dict[DetectorGroupKey, DetectorEvaluationResult]`.

## Spec (there is no spec; the commit message is the reference: "Add in hook for producing occurrences from the stateful detector" plus "fix typing")

3. **src/sentry/incidents/grouptype.py:11-12. Important. The one production handler is now abstract and cannot be instantiated.**
   - **Claim:** `MetricAlertDetectorHandler(StatefulDetectorHandler[QuerySubscriptionUpdate]): pass` is still abstract.
   - **Evidence:**
     - `StatefulDetectorHandler` declares four abstract members (`processors/detector.py:143,150,158,166`): `counter_names`, `get_dedupe_value`, `get_group_key_values` and the new `build_occurrence_and_event_data`.
     - Before the patch this class was a concrete `DetectorHandler` whose `evaluate` returned `[]`.
     - `MetricAlertFire.detector_handler = MetricAlertDetectorHandler` (grouptype.py:27). `Detector.detector_handler` (`workflow_engine/models/detector.py:86`) runs `group_type.detector_handler(self)`.
   - **Impact:** For any `metric_alert_fire` detector, `detector.detector_handler` and therefore `process_detectors` now raise `TypeError: Can't instantiate abstract class MetricAlertDetectorHandler ...`. Before the patch they returned a working no-op handler. It is latent today: grep finds no caller of `process_detectors` in src and no test that uses `metric_alert_fire`. The registered GroupType still points at a class that can never be built.
   - **Failing check (reasoned, not run):** in a sentry test env, `self.create_detector(type=MetricAlertFire.slug).detector_handler` raises TypeError. Shorter: `from sentry.incidents.grouptype import MetricAlertDetectorHandler; MetricAlertDetectorHandler(None)`. The ABC check fires before `__init__`.

4. **src/sentry/workflow_engine/processors/detector.py:49, 126-128, 59-65. Minor. A public-interface change the commit message doesn't mention.**
   - The abstract `DetectorHandler.evaluate` return type and `process_detectors`' return shape changed from list to dict keyed by group key.
   - The duplicate-group-key error logging in `process_detectors` was removed, along with its test `test_state_results_multi_group_dupe`.
   - `Detector.group_type` was added (`models/detector.py:58-60`).
   - All of this supports the hook, and the dict makes duplicates impossible by construction. Still, it goes beyond "add a hook" and breaks every `DetectorHandler` subclass. The only in-tree one is finding 3.

5. **tests/sentry/workflow_engine/processors/test_detector.py:458-489 (helper) and its uses at about 381-394, 488-490, 536-545. Minor. The tests don't check what the hook is called with.**
   - **Claim:** the tests can't tell whether the hook got the right group_key, value or priority.
   - **Evidence:**
     - `IssueOccurrence.__eq__` compares only `id` (`src/sentry/issues/issue_occurrence.py:181-184`), and `build_mock_occurrence_and_event` always uses the fixed id `eb4b0acf...`.
     - The expected values are already built with arguments that differ from the real ones, and the tests pass anyway:
       - `TestEvaluateGroupKeyValue.test_dedupe` builds the expected occurrence for `"val1"` but evaluates `"group_key"`, so the fingerprints differ.
       - `test_results_on_change` builds it with value 6 but evaluates 100.
       - `test_state_results_multi_group` builds group_2 with value 6 but evaluates 10.
     - So a wrong group_key, value or priority passed to `build_occurrence_and_event_data` would not fail any test.

Summary: Standards has 2 findings, both Minor judgement calls; the worst is the stale TODO in incidents/grouptype.py. Spec has 3 findings; the worst is finding 3, where MetricAlertDetectorHandler is now abstract and MetricAlertFire's handler can't be built.

## Unreviewed files
None. I reviewed all 4 files in the patch:
- src/sentry/incidents/grouptype.py
- src/sentry/workflow_engine/models/detector.py
- src/sentry/workflow_engine/processors/detector.py
- tests/sentry/workflow_engine/processors/test_detector.py

The patch file stops partway through the last test hunk at line 700, so I read the rest of that test from the checked-out HEAD file.

Not checked: I didn't run mypy or pytest, and I didn't read the external docs.sentry.io standards that CONTRIBUTING.md points to.
