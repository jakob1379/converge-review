## Review: getsentry__sentry__93824 (base de11fb0 to head 3162ad68a5c), multiprocess span flusher

There was no spec, so I took the intent from the CLI help and the commit history: split the span flusher across up to N processes by shard, set N with `--flusher-processes` (default 1), and keep the existing liveness, backpressure and restart behaviour per process. I loaded `superpowers:requesting-code-review` and did the review myself, with no subagent. I ran no project checks. The only thing I executed was a stdlib Python one-liner.

### Critical

**1. `src/sentry/spans/consumers/process/flusher.py:253-257`: a hung flusher process is never killed before its replacement starts.**
- **Claim:** the patch wraps `process.kill()` in `if isinstance(process, multiprocessing.Process):`. Production processes come from `multiprocessing.get_context("spawn").Process`, which is a `SpawnProcess`. `SpawnProcess` inherits from `BaseProcess`, not from `multiprocessing.Process`, so the check is always False and `kill()` never runs. The base code called `self.process.kill()` with no condition.
- **Effect:** on a `hang` restart, the old process keeps running and a new one starts on the same shards. A "hang" is just one loop taking longer than `max-unhealthy-seconds`, for example a slow Kafka produce, so the old process is usually still working. Two processes then run `flush_segments` on the same queues and can both read the same segment keys before either calls `done_flush_segments`. That duplicates segments in buffered-segments. Up to `MAX_PROCESS_RESTARTS` (10) orphaned processes can pile up per process index.
- **Evidence (fails on head):**
  `python3 -I -c "import multiprocessing as mp; p=mp.get_context('spawn').Process(target=print); print(isinstance(p, mp.Process))"` prints `False`.
- **Fix direction:** check `isinstance(process, multiprocessing.process.BaseProcess)`, or call `kill()` when it exists.
- **Related:** `join` at line 346 uses the same wrong check, so `terminate()` never runs either. That part was already broken before this patch, but the patch copies it into the new per-process loop.

### Important

**2. `flusher.py:64-66` together with `src/sentry/spans/buffer.py:382-384, 410`: `spans.buffer.max-flush-segments` and the backpressure threshold now scale with the number of processes.**
- **Claim:** each process gets its own `SpansBuffer(shards)`, so `max_segments_per_shard = ceil(max_flush_segments / len(shards_in_this_process))`.
- **Effect:** with P processes, each process flushes up to `max_flush_segments` per cycle, so the consumer as a whole flushes up to P times that. The `any_shard_at_limit` threshold also rises by a factor of P, so backpressure kicks in later.
- None of this is documented. It does not apply at the CLI default of 1, but it does apply whenever the flag is raised, and in tests that use the `None` default.
- Reasoned, not run.

**3. `flusher.py:47,51` against `src/sentry/consumers/__init__.py:433`: the two defaults disagree, and the tests cover the one production doesn't use.**
- **Claim:** `max_processes=None` on `SpanFlusher` and `ProcessSpansStrategyFactory` means one process per shard. The CLI default is `1`, meaning a single process.
- **Effect:** `test_basic` and `test_backpressure` don't pass the parameter, so they run the one-per-shard path. The configuration production actually runs (all shards in one process) is only covered when there happens to be a single shard.
- The docstring at line 32, "Creates one process per shard", is also wrong for the default deployment.

**4. No test covers the restart/kill path or flushing across several processes.**
- The new test `test_flusher_processes_limit` (`tests/.../test_consumer.py:84-123`) only checks internal attributes: `processes`, `max_processes`, `num_processes` and `process_to_shards_map`.
- That conflicts with the user's documented testing standard: test contracts, never implementation details.
- It produces no spans and never checks that segments from all 4 shards get flushed. Nothing exercises `_ensure_processes_alive`, so finding 1 went through unnoticed.

### Minor

5. **`test_consumer.py:60-62`: the added sleep does nothing.** `time.sleep(0.1)` with the comment "Give flusher threads time to process" runs after `monkeypatch.setattr("time.sleep", lambda _: None)`, so the wait never happens. The switch to `django_db(transaction=True)` in both tests is unexplained.

6. **`flusher.py:336-347`: `join` can skip later processes.** Once the deadline passes, `break` skips the remaining processes completely. The base code always reached the terminate step. Today this has no effect because of the `isinstance` bug in finding 1, but it becomes a real gap once that is fixed.

7. **`flusher.py:298-301`: memory info is fetched once per buffer.** Every per-process buffer talks to the same Redis cluster, so `get_memory_info()` runs `INFO` on every node N times per `submit()`. The used/available ratio is unaffected because both sums are multiplied by N. It is pure redundant I/O on the consumer's main thread, and one buffer would be enough.

8. **Dead code.** `_create_process_for_shard` (`flusher.py:127-132`) has no callers. `if not process: continue` (line 222) can never be true.

9. **Inconsistent metric tags.**
   - `spans.buffer.flusher.wait_produce` uses the tag `shards` (line 199). The other metrics use `shard`.
   - The `shard` tag value is a joined list such as `"0,1,2,3"` in some places (lines 185, 195) and a single int in others (line 244).
   - The joined values change with every rebalance, which creates new tag combinations.

10. **`CLAUDE.md:448-458`: unrelated change.** The `hasattr`/`isinstance` anti-pattern guidance has nothing to do with this feature and is scope creep in this PR.

### Declined to judge
- The `--flusher-processes` option wiring in `src/sentry/consumers/__init__.py`: `click` is already imported and the option mirrors the existing ones. I did not trace how click options reach the factory kwargs beyond confirming the kwarg name matches.
- Starting zero processes when no shards are assigned: `range(0)` means nothing runs. Before, an idle flusher with no shards started anyway. Harmless either way.

### Files not reviewed
None. All six files in the patch were reviewed: `CLAUDE.md`, `src/sentry/consumers/__init__.py`, `src/sentry/spans/consumers/process/factory.py`, `src/sentry/spans/consumers/process/flusher.py`, `tests/sentry/spans/consumers/process/test_consumer.py` and `tests/sentry/spans/consumers/process/test_flusher.py`.

**Verdict:** not ready to merge. Finding 1 quietly turns off the existing hang-recovery kill in production.

Not checked: I ran no pytest or Redis, so findings 2-4 and 6-7 are reasoned from the code. A regression test for finding 1 would have to drive a real spawn process through `_ensure_processes_alive`. I did not write one because that needs Kafka producer config.
