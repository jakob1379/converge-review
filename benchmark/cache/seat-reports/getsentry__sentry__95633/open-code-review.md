I ran `open-code-review:delegate-review` in range mode (fd358e8a3..9966ec5a1). The OCR preview found 7 files and listed 5 as reviewable. I reviewed every non-empty file, including the two test files that OCR leaves out by default.

The main finding is Critical: after the first partition rebalance in thread-queue-parallel mode, the consumer drops messages and still commits their offsets. I reproduced this with a stubbed script that imports the real `queue_consumer.py` and fails.

## Findings

**1. src/sentry/remote_subscriptions/consumers/result_consumer.py:133 and :254, with queue_consumer.py:335-345 and :317-325 — Critical**
- **Claim:** After a rebalance, every message in thread-queue-parallel mode is dropped without being processed, and its offset is still committed. This is silent data loss.
- **Evidence:**
  - The factory builds one `FixedQueuePool` in `__init__` (line 133).
  - Each `create_with_partitions` call wraps that same pool in a new `SimpleQueueProcessingStrategy` (line 254).
  - When partitions are revoked, arroyo calls `strategy.close()` and then `join()`. `close()` calls `self.queue_pool.shutdown()`, which shuts down every `queue.Queue` and stops the workers. `join()` calls `close()` a second time.
  - When partitions are assigned again, the next strategy reuses the dead pool. `work_queue.put` raises `queue.ShutDown`. The broad `except Exception` in `submit` (lines 317-325) catches it, logs it, and marks the offset complete. The commit loop then commits it.
- **Failing command (exits 1):** `python3 -I <bench>/work/getsentry__sentry__95633.scratch/repro/rebalance_repro.py <bench>/work/getsentry__sentry__95633/src/sentry/remote_subscriptions/consumers/queue_consumer.py`
  - The script stubs `arroyo`, `sentry_sdk` and `metrics`, then runs the real module.
  - Output: `processed: ['a']`, `commits: [{P0: 0}, {P0: 1}]`. Offset 1 was committed but never processed.
- **Test gap:** No test in the patch calls `close()` and then `create_with_partitions()` again. Every thread-queue test in test_results_consumer.py creates one strategy and then calls `factory.shutdown()`.

**2. queue_consumer.py:270-289 and result_consumer.py:249-252 — Important**
- **Claim:** The arroyo `commit` callback is called from a background thread (`_commit_loop`) instead of the consumer's main thread.
- **Evidence:**
  - arroyo's `StreamProcessor` commit callback stages and commits offsets on the consumer. That is consumer state shared with the main poll loop, and arroyo strategies are expected to call it from `submit` or `poll`. Every other strategy in this file commits from the main thread through `CommitOffsets`.
  - The offset tracker is shared across rebalances and never reset. So after a partition is revoked, the commit loop can still put that partition in `committable`. arroyo's `KafkaConsumer.stage_offsets` rejects unassigned partitions (`ConsumerError`).
  - The whole dict goes into one `commit_function` call, so one bad partition fails the commit for every partition. The exception is caught and logged at line 290, `mark_committed` never runs, and the loop retries the same failing dict every second. Commits stall.
- **Status:** Reasoned. Arroyo is not installed locally, so I did not execute this.
- **Fix direction:** Do the commit in `poll()` on the main thread. Also reset or prune the tracker for revoked partitions.

**3. queue_consumer.py:185 and :204-212 (docstring at :253) — Important**
- **Claim:** There is no backpressure. The docstring promises "Natural backpressure when queues fill up", but the queues are unbounded.
- **Evidence:**
  - `queue.Queue()` has no `maxsize`.
  - `submit` never raises `MessageRejected`.
  - When processing is slower than intake (for example, during consumer lag catch-up), arroyo keeps submitting. Memory then grows without limit in the queues and in `OffsetTracker.all_offsets` / `outstanding`.
- **Status:** Reasoned.

**4. queue_consumer.py:86-93 — Important**
- **Claim:** Commits stall permanently for a partition if its offsets are not contiguous.
- **Evidence:**
  - The scan goes from `start` to `max_offset` and stops at the first offset that is not in `all_offsets`.
  - Kafka offsets can have gaps: transaction control markers, compacted topics, or messages the consumer never submits. With a gap, `highest_committable` can never get past it, and `all_offsets` grows forever on that partition.
  - The head commit "remove gap test" suggests a test for this case was written and then deleted rather than fixed.
- **Status:** Reasoned. With offsets {0, 2} both completed, the loop stops at 1 and commits only 0, and 2 is never committed.

**5. queue_consumer.py:231-243 and :335-345 — Important**
- **Claim:** On shutdown or revoke, work already queued or completed is abandoned without a final commit.
- **Evidence:**
  - `FixedQueuePool.shutdown` sets `worker.shutdown = True` before it shuts down the queues. The `while not self.shutdown` check then exits after the current item, so the queue is not drained.
  - The commit thread is stopped before the pool shuts down, and no final `get_committable_offsets()` / commit happens. Up to about 1 second of completed work, plus everything still queued, gets reprocessed by the next owner.
  - `join(timeout)` ignores its `timeout` argument and just calls `close()` again.
- **Status:** Reasoned.

**6. queue_consumer.py:136-140 — Minor**
- **Claim:** Each result gets two nested transactions.
- **Evidence:** The worker opens `sentry_sdk.start_transaction(op="queue_worker.process")` around `self.result_processor(...)`. But `ResultProcessor.__call__` (result_consumer.py:48) already opens its own transaction. Other modes do not add an outer one.
- **Status:** Reasoned.

## Not reviewed

- `tests/sentry/remote_subscriptions/__init__.py` (added, empty file).
- `tests/sentry/remote_subscriptions/consumers/__init__.py` (added, empty file).

The two large test files, `test_queue_consumer.py` and `test_results_consumer.py`, are excluded by OCR by default. I read them only to check for missing coverage and did not do a line-by-line review. The one gap I found is the missing rebalance test noted in finding 1.

I did not run the project test suite, as instructed. Arroyo isn't installed here, so findings 2–6 are reasoned from my knowledge of arroyo 2.28 behaviour (`close()` and `join()` on revoke, `stage_offsets` rejecting unassigned partitions), not executed. The only file I created is the repro script under the `.scratch/repro/` directory.
