I reviewed the patch myself under `superpowers:requesting-code-review`, without dispatching a reviewer. There was no spec, so I judged the change against its own docstrings and against how Arroyo strategies are expected to behave. The new `thread-queue-parallel` mode loses data after the first partition rebalance, so it is not ready to merge.

To reproduce without installing anything, I used minimal stubs of `arroyo`, `sentry_sdk` and `sentry.utils.metrics` in `<bench>/work/getsentry__sentry__95633.scratch/stubs/`, plus a copy of the patched `queue_consumer.py`. Each repro script sits in the `.scratch` directory and runs with this command, swapping in the script name:
`cd <bench>/work/getsentry__sentry__95633.scratch/stubs && python3.13 -I -c "import sys; sys.path.insert(0,'.'); exec(open('../<script>').read())"`

## Findings

**1. `src/sentry/remote_subscriptions/consumers/result_consumer.py:131-137` and `:244-259`, with `queue_consumer.py:335-345` and `:204-212` — Critical**
- **Claim:** After the first partition revocation, every later message is dropped without being processed, and its offset is still committed.
- **Evidence:**
  - The factory builds one `FixedQueuePool` in `__init__` and hands that same pool to every strategy that `create_with_partitions` returns.
  - When partitions are revoked, Arroyo calls `strategy.close()` and `join()`. Both reach `queue_pool.shutdown()`, which shuts down every queue and stops every worker.
  - `factory.queue_pool` is still set afterwards, so the `assert self.queue_pool is not None` at `:247` passes and the next assignment gets a strategy built on the dead pool.
  - In that strategy, `submit()` hits `work_queue.put()`, which raises `queue.ShutDown`. The broad `except Exception` at `queue_consumer.py:317` catches it, calls `add_offset` then `complete_offset`, and the commit loop commits the offset.
  - Result: uptime results are silently lost on every rebalance (deploys, scaling).
- **Failing command:** `repro_rebalance.py`. It prints `processed ['a'] commits [{...: 0}, {...: 1}]` and fails with `AssertionError: message b was never processed`, so offset 1 was committed even though it was never processed.
- **Fix direction:** create the pool and the `OffsetTracker` per strategy inside `create_thread_queue_parallel_worker`, and have only `factory.shutdown()` handle whatever is left.

**2. `queue_consumer.py:185` and docstring `:253` — Important**
- **Claim:** There is no backpressure. Memory grows without limit whenever processing is slower than consumption.
- **Evidence:**
  - `queue.Queue()` is created without `maxsize`.
  - `submit()` never raises `MessageRejected`. A grep shows it is not referenced anywhere in `queue_consumer.py`; compare `spans/consumers/process/flusher.py:364`, which does raise it.
  - Arroyo will therefore keep polling and queueing during a backlog (catch-up after an outage, slow DB). Each queued `WorkItem` holds the full Kafka `Message`.
  - The docstring's "Natural backpressure when queues fill up" is false.
- **Failing command:** reasoned. It follows directly from the constructor call and the grep above.

**3. `queue_consumer.py:273-291`, with `result_consumer.py:249-252` — Important**
- **Claim:** The Arroyo `commit` callback is called from a background thread (`_commit_loop`), while the StreamProcessor's main thread is running `poll`/`_run_once` and rebalance callbacks.
- **Evidence:**
  - Arroyo strategies are expected to run single-threaded, with commits happening from `submit` or `poll` on the processor thread.
  - `StreamProcessor`'s commit path and `KafkaConsumer.stage_offsets`/`commit_offsets` update shared Python state (buffered and staged offsets) without locks.
  - `stage_offsets` raises `ConsumerError` for unassigned partitions. If a rebalance races with the commit loop, that error is swallowed by `except Exception` at `:290`.
  - The safe pattern is for the commit loop to only compute what can be committed, and for `poll()` to call `commit`.
- **Failing command:** reasoned. Arroyo is not installed locally, so I could not check this against its 2.28.0 source.

**4. `queue_consumer.py:335-345` (`close`/`join`) — Minor**
- **Claim:** `close()` tears everything down without draining the queues or doing a final commit, and `join()` ignores its `timeout` argument.
- **Evidence:**
  - `close()` stops the commit thread before workers finish, so work completed since the last 1s tick, plus everything still queued, is never committed. The next owner of the partition reprocesses it, giving at-least-once duplicates.
  - `join(timeout)` just calls `close()` again. That can block for 5s on the commit thread plus 5s for each busy worker, which goes beyond the deadline Arroyo passes in during a rebalance.
- **Failing command:** reasoned.

**5. `queue_consumer.py:254` (docstring) and `tests/sentry/uptime/consumers/test_results_consumer.py:1874-1924`, line `1922` — Minor**
- **Claim:** The docstring says "Only commits offsets after successful processing", but the worker's `finally` (`:148`) completes the offset even when processing raises. `test_thread_queue_parallel_error_handling` asserts that no commit happens, and only passes because it finishes before the 1s commit tick fires. On a slow CI runner it will fail, so it is flaky.
- **Evidence:** committing after a failure matches the existing modes, because `ResultProcessor.__call__` already swallows exceptions. The problems are the false docstring and the test that relies on timing.
- **Failing command:** `repro_error_commit.py` fails with `AssertionError: failed message offset was committed` and shows `[{Partition(topic='t', index=1): 100}]`.

**6. `tests/sentry/uptime/consumers/test_results_consumer.py:1926-1985` (`actual_offset == 101`), and `tests/sentry/remote_subscriptions/consumers/test_queue_consumer.py:351` (`test_offset_gaps_block_commits`) — Minor**
- **Claim:** Both tests say a gap "prevents committing past the gap". The code does not do that.
- **Evidence:**
  - `mark_committed` removes offsets up to the committed one. On the next tick, `start = max(last_committed + 1, min(all_offsets))` jumps over the gap, so offset 103 is committed one cycle later.
  - Skipping the gap is actually correct for Kafka, which delivers in order, so a missing lower offset will never arrive.
  - The tests only pass because they stop asserting within roughly one commit interval, so they are timing-dependent.
- **Failing command:** `repro_gap_commit.py` fails with `AssertionError: committed past the gap at 101` and shows `[{...: 100}, {...: 103}]`.

**7. `tests/sentry/uptime/consumers/test_results_consumer.py`, Kafka test (`processor._run_once()`, `processor._shutdown()`, `factory.create_with_partitions = ...`) — Minor**
- **Claim:** This breaks the global CLAUDE.md testing rules ("never test private methods / implementation details / framework code").
- **Evidence:** the test drives Arroyo's private `StreamProcessor` methods and monkeypatches the factory method it is testing, so an Arroyo upgrade can break it without any change in behaviour.
- **Failing command:** reasoned.

## Unreviewed files
None. I reviewed all seven files in the patch: `src/sentry/consumers/__init__.py`, `queue_consumer.py`, `result_consumer.py`, the two empty test `__init__.py` files, `test_queue_consumer.py` and `test_results_consumer.py`.

I did not run the real test suite, because the instructions ruled it out and the project's dependencies are not installed. Findings 1, 5 and 6 are confirmed with the stub repros. Findings 2, 3, 4 and 7 are reasoned only; finding 3 especially still needs checking against Arroyo 2.28.0's `StreamProcessor`/`KafkaConsumer` source.
