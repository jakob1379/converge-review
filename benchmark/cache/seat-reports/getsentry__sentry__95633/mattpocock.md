## Code review: getsentry__sentry__95633, fd358e8a..9966ec5a (8 commits, "feat(uptime): Add ability to use queues to manage parallelism")

I ran the `mattpocock-skills:code-review` skill and did both axes in this one agent, as your override asked. I did not run anything. No Python environment with arroyo is available, and running the suite was out of scope. Every finding is therefore reasoned from the code, and the failing tests I propose below have not been executed.

Standards sources I used:
- The repo's `CLAUDE.md`.
- `.cursor/rules/python_tests.mdc`.
- `.github/CONTRIBUTING.md`, which only links to external docs.
- The mypy stronglist in `pyproject.toml`. `remote_subscriptions` is not on it, so there are no typing breaches.

Spec: none was provided. I therefore checked the change against two contracts that are written down: the patch's own docstrings, which state its guarantees, and the arroyo `ProcessingStrategy` interface it implements.

## Spec / contract axis

1. **src/sentry/remote_subscriptions/consumers/queue_consumer.py:335-338 (`close()`), :344-345 (`join()`), plus result_consumer.py:131-133 and :254**
   - **Severity:** Critical
   - **Claim:** After the first partition rebalance, every message is silently dropped and its offset is still committed.
   - **Evidence:**
     - The factory creates one `FixedQueuePool` in `__init__` and passes that same pool to every strategy it builds.
     - On revocation, arroyo calls `strategy.close()` and then `join()`. `close()` calls `self.queue_pool.shutdown()`, which shuts the queues down and stops the workers.
     - `factory.queue_pool` is set back to `None` only in `factory.shutdown()`. So the next `create_with_partitions` passes `assert self.queue_pool is not None` and hands the new strategy the dead pool.
     - In the new strategy, `submit()` reaches `work_queue.put()` (line 212). On Python 3.13.1, `put()` on a shut-down queue raises `queue.ShutDown`.
     - `submit()` catches that with its broad `except Exception` (line 317), logs it, and marks the offset complete.
     - The commit loop then commits that offset. The data is lost and nothing raises.
     - The `OffsetTracker` is also shared across strategies and never reset, so stale state for revoked partitions carries over.
   - **Failing test (not run):**
     ```python
     f = MockFactory(mode="thread-queue-parallel", max_workers=2)  # MockFactory from test_queue_consumer.py:880-905
     s1 = f.create_with_partitions(mock.Mock(), {p: 0}); s1.close(); s1.join()
     s2 = f.create_with_partitions(commit, {p: 0}); s2.submit(msg)
     # expect the result processor to be called within 2s -> it never is, and commit is still called with offset+1
     ```

2. **queue_consumer.py:270 and :287 (commit thread calling `commit_function`), result_consumer.py:249-252**
   - **Severity:** Important
   - **Claim:** The arroyo `Commit` callable is called from a background thread. Arroyo expects strategies to commit from the consumer thread, i.e. from inside `submit`, `poll` or `join`.
   - **Evidence:**
     - `StreamProcessor`'s commit stages offsets on the `KafkaConsumer`. That consumer is not thread-safe, and the main thread's `_run_once` is using it at the same time.
     - On revocation, the commit thread is joined with only a 5s timeout. A commit for a partition this consumer no longer owns can therefore still happen.
     - The safe pattern is to compute committable offsets in `poll()` and call `commit` there.
   - **Failing test:** none; reasoned.

3. **queue_consumer.py:344-345 (`join()` just calls `close()`)**
   - **Severity:** Important
   - **Claim:** `join()` does not wait for the queued work to finish and does not do a final commit.
   - **Evidence:**
     - The arroyo contract for `join` is to finish the work already submitted and commit it.
     - Here, `shutdown()` sets `worker.shutdown = True` before draining, so a worker exits after its current item and abandons the rest of its queue.
     - Up to about 1s of offsets that were processed but not committed are lost on every graceful shutdown or rebalance. At best those messages are processed twice.
   - **Failing test:** none; reasoned.

4. **queue_consumer.py:253 vs :185**
   - **Severity:** Important
   - **Claim:** The docstring promises "Natural backpressure when queues fill up", but each queue is an unbounded `queue.Queue()`.
   - **Evidence:**
     - `submit()` never raises `MessageRejected`.
     - During a lag spike, the consumer will pull the whole backlog into memory, with no cap.
   - **Failing test:** none; reasoned.

5. **queue_consumer.py:254 vs :149, and tests/sentry/uptime/consumers/test_results_consumer.py:1874-1922**
   - **Severity:** Minor
   - **Claim:** The docstring says offsets are committed "only after successful processing". In fact `complete_offset` runs in `finally`, so offsets for failed items are committed too.
   - **Evidence:**
     - The behaviour itself matches the existing modes, because `ResultProcessor.__call__` already catches and logs errors (result_consumer.py:53).
     - The problem is the test `test_thread_queue_parallel_error_handling`. It asserts that the partition is *not* committed, and it passes only because it checks within about 0.3s, before the commit loop's first 1s tick.
     - Wait past 1s and it would see offset 102. The test confirms a guarantee the code does not have, and its result depends on timing.

6. **src/sentry/consumers/__init__.py:124 (`--mode` help)**
   - **Severity:** Minor
   - **Claim:** A new mode was added, but the `--mode` help text was not updated.
   - **Evidence:** It still says "Parallel uses multithreading." That now misdescribes both `parallel` (which uses multiprocessing) and the new mode.

## Standards axis

1. **tests/sentry/uptime/consumers/test_results_consumer.py:1689-1975 and :74**
   - **Severity:** Minor
   - **Claim:** The new-mode tests are added as methods on `ProcessResultSerialTest`. The file's convention is one `ProcessResultTest` subclass per mode with `strategy_processing_mode` set.
   - **Evidence:**
     - Existing modes each have a subclass: `ProcessResultSerialTest` and `ProcessResultParallelTest`.
     - As a result, the full behavioural suite is never run in `thread-queue-parallel` mode.
     - The `Literal["batched-parallel", "parallel", "serial"]` annotation on that property was not extended either.
   - **Failing test:** none; reasoned.

2. **tests/sentry/remote_subscriptions/consumers/test_queue_consumer.py:98-106 (`test_different_groups_distributed`)**
   - **Severity:** Minor
   - **Claim:** The test can fail at random.
   - **Evidence:** `hash()` on strings is randomized per process (PYTHONHASHSEED). The chance that 20 keys miss one of the 3 queues is about 3·(2/3)^20 ≈ 0.09% per run.

3. **test_queue_consumer.py:137 (`test_concurrent_processing_across_groups`)** and **test_results_consumer.py `test_thread_queue_parallel_concurrent_subscriptions`**
   - **Severity:** Minor
   - **Claim:** The test names promise concurrency, but nothing in either test checks it.
   - **Evidence:** They only check that every item was processed, which serial execution would also pass. This breaks the user's rule "test contracts, not implementation", which needs the asserted behaviour to match the stated one.

4. **queue_consumer.py:145, 291, 318 (logging)**
   - **Severity:** Minor (judgement call)
   - **Claim:** The new log calls do not follow the logging pattern in CLAUDE.md.
   - **Evidence:**
     - CLAUDE.md's pattern is structured logging with dotted event names and `extra`.
     - The new calls use prose messages, such as "Error in commit loop" and "Error submitting message to queue", and pass no partition or offset in `extra`.
     - The existing `result_consumer.py` uses prose too, so the repo is not consistent. This is low priority.

5. **CLAUDE.md "Feature Flags: Always add for new features"**
   - **Severity:** No finding (judgement call)
   - **Evidence:** The new mode is opt-in through the `--mode` CLI flag, which works as a gate. I am not treating this as a breach.

**Smell baseline (judgement only):** `OrderedQueueWorker` has Duplicated Code: the `add_offset`/`complete_offset` pair appears twice in `submit` (queue_consumer.py:302-303 and 320-325).

**Summary:** 6 findings on the contract axis; the worst is the Critical one, where the shared pool is shut down on rebalance and later messages are dropped and committed. 5 items on the standards axis, none worse than Minor; the worst is that the new mode is not run through the existing per-mode test suite.

## Unreviewed files

- `tests/sentry/remote_subscriptions/__init__.py` and `tests/sentry/remote_subscriptions/consumers/__init__.py` are empty package markers, so there was nothing to review.
- I read `ProcessResultThreadQueueParallelKafkaTest` (test_results_consumer.py:2012+) for standards only. It needs a live Kafka, and I did not check its timing assumptions (5s of `_run_once`, expected offset 5).

I also did not check arroyo's source directly, because it is not installed. My statements about the `join` contract and about the commit callable not being thread-safe come from my knowledge of arroyo.
