## Over-engineering review: getsentry__sentry__80168

**What this change does:** It adds an abstract hook, `build_occurrence_and_event_data`, to `StatefulDetectorHandler`. When a detector's status becomes non-OK, the hook builds an `IssueOccurrence` and its event data. `evaluate()` now returns a dict keyed by group key instead of a list, which lets `process_detectors` drop its duplicate-key log check. It also adds a `Detector.group_type` property, and the tests are rebuilt around a shared base class.

The best part is the deletion. Keying results by group key removes the duplicate-key loop and its test, and the dict keys can never repeat, since they come from `get_group_key_values()`. I found nothing structural to remove from the production code. The `group_type` property and the `builtins.type` annotation are small and justified: the model's `type` field hides the built-in `type` inside the class body, and real handlers will need `group_type` to fill `IssueOccurrence.type`.

### Findings

1. **`src/sentry/incidents/grouptype.py:10-12` — Minor (reasoned)**
   - **Claim:** `MetricAlertDetectorHandler(StatefulDetectorHandler[...]): pass` is now an abstract class that cannot be created. It is missing `counter_names`, `get_dedupe_value`, `get_group_key_values` and `build_occurrence_and_event_data`.
   - **Evidence:** `MetricAlertFire.detector_handler = MetricAlertDetectorHandler` (line 27). `Detector.detector_handler` ends in `group_type.detector_handler(self)` (`src/sentry/workflow_engine/models/detector.py:86`). So any `metric_alert_fire` detector now raises `TypeError: Can't instantiate abstract class`. Before this change, the stub `evaluate` returned `[]`.
   - **Why only Minor:** grep shows nothing in production calls `process_detectors` or `.detector_handler` (`processors/__init__.py` only re-exports it). The crash is latent, not live.
   - **Also:** the TODO on line 10 ("will be a stateful detector when we build that abstraction") is now stale. The class body adds nothing over the old stub.
   - **Fix:** either keep the concrete stub, or remove `detector_handler` from `MetricAlertFire` until a real handler exists.

2. **`tests/sentry/workflow_engine/processors/test_detector.py:101-105` — Minor**
   - **Claim:** the `detector_type` parameter of `BaseDetectorHandlerTest.build_handler` is dead code.
   - **Evidence:** every `self.build_handler(...)` call in the file passes either nothing or a `Detector`. None passes `detector_type=`.
   - **Same pattern:** `create_detector_and_conditions(self, type: str | None = None)` at lines 86-88 sets `None` and then replaces it with `"handler_with_state"`. A plain default argument does this in one line.

3. **`tests/sentry/workflow_engine/processors/test_detector.py:125-126` — Minor**
   - **Claim:** `TestProcessDetectors.setUp` only calls `super().setUp()`, so it does nothing.
   - **Evidence:** lines 125-126 are the entire method body. Delete them.

4. **`tests/sentry/workflow_engine/processors/test_detector.py:151, 180, 191, 428, 446, 490, 510, 537` — Minor**
   - **Claim:** `build_mock_occurrence_and_event` ignores its `value` argument, so the hardcoded `6` at these call sites is noise, and in places it is wrong. No test checks that the hook receives the real value.
   - **Evidence:** the helper (lines 244-275) never reads `value`. The tests pass `6` where the evaluated value is 100 (line 488), 8 (line 508) or 10 (line 177, `group_2`), and they still pass.

5. **`src/sentry/workflow_engine/processors/detector.py:230` — Minor**
   - **Claim:** the docstring of `StatefulDetectorHandler.evaluate` still says it "returns a list of `DetectorEvaluationResult`". After this change it returns a dict.
   - **Evidence:** lines 226-244, return annotation `dict[DetectorGroupKey, DetectorEvaluationResult]`.

**Verdict:** No Critical or Important issues from the over-engineering angle. Finding 1 is the only one that is more than lean cleanup.

**Lean:** about 8 lines can go (findings 2 and 3, plus the empty class body if finding 1 takes the "remove `detector_handler`" route).

### Unreviewed files

None. I reviewed all four files in the patch: `src/sentry/incidents/grouptype.py`, `src/sentry/workflow_engine/models/detector.py`, `src/sentry/workflow_engine/processors/detector.py` and `tests/sentry/workflow_engine/processors/test_detector.py`.

**Not checked:** I ran no tests, as instructed. No finding comes with a failing test, because finding 1 has no production caller to trigger it.
