**Over-engineering review: getsentry__sentry__95633 (ponytail:ponytail-review)**

What the change does: it adds a `thread-queue-parallel` mode to the uptime/remote-subscription results consumer. It adds a new module, `queue_consumer.py`, with three parts. `FixedQueuePool` is N FIFO queues, each with one worker thread, and items are hashed to a queue by group key. `OffsetTracker` works out which Kafka offsets are safe to commit. `SimpleQueueProcessingStrategy` is the arroyo strategy, with a background commit thread that runs every second. `ResultsStrategyFactory` wires the mode in.

Assumed load: a production Kafka consumer handling many messages per second, with partition rebalances. I did not install dependencies or run the project's test suite. The two repro scripts below load only the patched module, using the system python and stubs.

## Findings (over-engineering lens)

1. **`src/sentry/remote_subscriptions/consumers/queue_consumer.py:44-105`, Important: the gap-tracking code in `OffsetTracker` does not give the guarantee it exists for.**
   - **Claim:** `all_offsets`, the `min`/`max`/`range` scan and the pruning in `mark_committed` (about 30 lines run under the lock) exist to "block commits past a gap". They don't. The gap holds back the commit for one commit cycle only. After that, `start = max(last_committed + 1, min_offset)` jumps over the missing offset.
   - **Evidence:** submit offsets 100, 102 and 103 and complete them all. Cycle 1 commits 100. Cycle 2 commits 103, and 101 never arrived.
   - **Test relying on it:** `tests/sentry/remote_subscriptions/consumers/test_queue_consumer.py:351` `test_offset_gaps_block_commits` claims the gap blocks commits. It passes only because offset 101 is submitted before the next 1-second cycle runs.
   - **Simpler approach:** keep only `outstanding` plus the highest offset seen per partition. The committable offset is `min(outstanding) - 1` when anything is outstanding, otherwise the highest seen. The real behaviour stays the same and about 20 lines go.
   - **Failing command:** `python3 -I <bench>/work/getsentry__sentry__95633.scratch/gap_claim.py src/sentry/remote_subscriptions/consumers/queue_consumer.py`. It fails with the AssertionError "gap at 101 did not block: committed past it on the next cycle".

2. **`queue_consumer.py:222-229`, Minor: `FixedQueuePool.wait_until_empty` is dead code.**
   - **Claim:** nothing calls it, in `src/` or in `tests/`.
   - **Evidence:** grepping for `wait_until_empty` returns only its definition.
   - **Fix:** delete it (8 lines).
   - Reasoned.

3. **`queue_consumer.py:31` and `:312`, Minor: `WorkItem.message` is stored but never read.**
   - **Claim:** every queued item keeps a reference to the whole arroyo `Message` for nothing. The queues have no size limit, so under consumer lag this is pure extra memory.
   - **Evidence:** grepping for `.message` and `work_item.message` finds no readers. Only `partition`, `offset` and `result` are used (`:140`, `:149`).
   - **Fix:** delete the field and the `message=` argument.
   - Reasoned.

4. **`queue_consumer.py:125`, `:129`, `:142-143`, `:233-234`, Minor: the `OrderedQueueWorker.shutdown` flag and the inner `except queue.ShutDown` are redundant, and the flag fights the drain.**
   - **Claim:** `q.shutdown(immediate=False)` already makes `get()` raise `ShutDown` once the queue is empty. The flag is set first, so a worker exits after its current item and leaves queued items behind. That defeats the `immediate=False` drain.
   - **Dead code:** the inner `except queue.ShutDown` at `:142` can't fire, because `result_processor` never touches the queue.
   - **Fix:** delete the flag, the loop condition and the inner except. That is about 5 lines, and the drain then actually happens.
   - Reasoned.

5. **`queue_consumer.py:301-304` and `:319-325`, Minor: the same "add then complete the offset" pair appears twice.**
   - **Fix:** read `partition` and `offset` before the `try`, then mark the offset done once on both the skip path and the error path. About 6 lines less.
   - Reasoned.

6. **`queue_consumer.py:214-220`, Minor: `get_stats` builds a dict holding a `queue_depths` list that production code never reads.**
   - **Evidence:** both production callers (`:226`, `:328`) only read `total_items`. `queue_depths` is asserted only in `test_queue_consumer.py:201-202`.
   - **Fix:** return `sum(q.qsize() for q in self.queues)`.
   - Reasoned.

## Outside my lane, but it blocks shipping: verified data loss on rebalance

7. **`queue_consumer.py:335-345` (`close`, `terminate`, `join`), together with `result_consumer.py:133` and `:255`, Critical: messages are silently dropped and their offsets committed after the first partition rebalance.**
   - **Claim:** the factory creates one `FixedQueuePool` and hands that same pool to every strategy it builds. But `SimpleQueueProcessingStrategy.close()` and `join()` call `queue_pool.shutdown()`, which shuts the shared pool down.
   - **What happens on rebalance:** arroyo closes and joins the old strategy when partitions are revoked, then calls `create_with_partitions` again. The new strategy submits into queues that are already shut down. `put` raises `queue.ShutDown`. The broad `except` at `:317` logs it and marks the offset complete, so the message is committed without ever being processed.
   - **Fix (a deletion):** remove `self.queue_pool.shutdown()` from `close` and `terminate`. The factory's `shutdown()` at `result_consumer.py:183-185` already owns the pool's lifecycle.
   - **Failing command:** `python3 -I <bench>/work/getsentry__sentry__95633.scratch/rebalance_repro.py src/sentry/remote_subscriptions/consumers/queue_consumer.py`.
   - **Output:** `processed ['a'] commits [{p0: 0}, {p0: 1}]`, then the AssertionError "message after rebalance was dropped but its offset was committed".

8. **`queue_consumer.py:185` against the docstring at `:253`, Important (scale, outside my lane): the docstring promises backpressure that doesn't exist.**
   - **Claim:** the docstring says "Natural backpressure when queues fill up", but the queues are `queue.Queue()` with no maxsize, and `submit` never raises `MessageRejected`.
   - **Effect:** under consumer lag, memory grows without limit.
   - Reasoned.

Considered and not reported:
- The `thread_queue_parallel` boolean follows the existing `parallel` / `batched_parallel` pattern.
- The get-then-`setdefault` lock lookup in `_get_partition_lock` was a deliberate choice in commit 1ccdfbf36ac.
- I checked whether a gap could stall commits forever. It can't: `gap_repro.py` in the scratch dir shows commits keep advancing.

Verdict: fix 7 first. Fixes 1–6 are optional cleanup.
Lean: about -45 lines possible.

## Unreviewed files

- `tests/sentry/remote_subscriptions/__init__.py` and `tests/sentry/remote_subscriptions/consumers/__init__.py`: empty package markers, nothing to review.
- `tests/sentry/remote_subscriptions/consumers/test_queue_consumer.py` and `tests/sentry/uptime/consumers/test_results_consumer.py`: read only where they bear on the findings above (the gap tests and the `get_stats` / `get_queue_for_group` usage). I did not review them line by line for over-engineering.
- `src/sentry/consumers/__init__.py`: reviewed. It only adds a CLI choice and changes help text, and I found nothing.

Not checked: I did not run the real arroyo `StreamProcessor` against finding 7, so the rebalance call order (close/join, then `create_with_partitions` on the same factory) is reasoned from arroyo's documented lifecycle. The repro shows the pool-reuse failure directly.
