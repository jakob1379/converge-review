## Over-engineering review: getsentry__sentry__93824 (`change.patch`)

**What this change does:** The span flusher used to be one background process. This patch splits the Redis shards across N flusher processes (`--flusher-processes`, CLI default 1). Each process gets its own `SpansBuffer`, its own health and backpressure counters, and its own restart count. The patch also changes tests and adds an unrelated note to CLAUDE.md.

I only looked at over-engineering (unneeded code, abstractions, options, complexity). I assumed production load: a long-running Kafka consumer that calls `submit()` many times per minute.

### Should fix

1. **Dead method `_create_process_for_shard`** (`src/sentry/spans/consumers/process/flusher.py:127-132`)
   - **What this is:** A helper that finds the process owning a shard and restarts it.
   - **Problem:** Nothing calls it. A grep across `src/` and `tests/` finds only the definition. Restarts go through `_create_process_for_shards` at L259.
   - **Fix:** Delete it (6 lines).
   - **If we skip it:** People maintain and read a restart path that never runs.

2. **`self.buffers` duplicates work the old single `self.buffer` already did** (`flusher.py:77, 125, 269-270, 299-301`, import at L18)
   - **What this is:** The parent now keeps one `SpansBuffer` per child process. On every `submit()` it loops over all of them for `record_stored_segments()` and `get_memory_info()`.
   - **Problem:** Every buffer talks to the same cluster (`get_redis_client()` → `SENTRY_SPAN_BUFFER_CLUSTER`, `buffer.py:117`). `get_memory_info()` is just `iter_cluster_memory_usage(self.client)`, so with N processes the parent asks for cluster memory N times per submit. It then adds up N copies of the same nodes. The used/available ratio comes out the same, so the extra calls buy nothing. `record_stored_segments` also sends N small pipelines where one covering all shards did the job. The original `buffer` argument already holds every shard.
   - **Fix:** Keep `self.buffer = buffer` (undo the "remove self.buffer" commit) and call it once, as the base code did. Then drop `self.buffers`, both loops, the `memory_infos` list and the `ServiceMemory` import. The children can still build `SpansBuffer(shards)` locally.
   - **If we skip it:** N times the Redis round-trips on each submit for no added information. It gets worse as `--flusher-processes` grows.
   - Reasoned from the code; I did not run it.

3. **The new test checks internals, and two attributes exist mainly for it** (`tests/sentry/spans/consumers/process/test_consumer.py:84-123`; `flusher.py:51, 60`)
   - **What this is:** `test_flusher_processes_limit` asserts `flusher.max_processes == 2`, `flusher.num_processes == 2` and the sizes in `process_to_shards_map`.
   - **Problem:** This breaks the user's testing rule ("test contracts, not implementation… if refactoring internals breaks your tests… your tests are bad"). It never checks that spans from all 4 shards actually get flushed. Outside this test, `self.max_processes` is read only once (L60), and `max_processes or len(...)` followed by `min(max_processes, len(...))` normalizes the same value twice.
   - **Fix:** Use one local, `n = min(max_processes or len(shards), len(shards))`, and drop `self.max_processes`. Replace the internals assertions with a behavior check: put spans on 4 partitions, set drift, join, and assert all segments come out. `len(flusher.processes) == 2` is the only structural assertion worth keeping.
   - **If we skip it:** Renaming any of these fields breaks the test while behavior stays the same, and the real flushing contract stays untested.

4. **Dead test code in `test_basic`** (`test_consumer.py:60-62`)
   - **What this is:** An extra `step.poll()` plus `time.sleep(0.1)` with the comment "Give flusher threads time to process".
   - **Problem:** Line 15 already replaces `time.sleep` with `lambda _: None`, and the test's `time.sleep` is that same patched module attribute. So the sleep and its comment do nothing.
   - **Fix:** Delete L61-62. Keep the extra `poll()` only if it is needed (I did not check whether it is).
   - **If we skip it:** Readers think there is a timing fix that does not exist.

### Nice to have

5. **Redundant deadline check in `join`** (`flusher.py:337-341`)
   - **Problem:** The `remaining_time <= 0: break` block repeats the `deadline > time.time()` check already in the `while` on L343. The `break` also skips `terminate()` for every later process, and `process_index` is never used.
   - **Fix:** Delete L338-341 and loop over `self.processes.values()`.

6. **Dead guard** (`flusher.py:222-223`)
   - **Problem:** `if not process: continue` can never be true, because `self.processes` only ever holds started Process or Thread objects (L124).
   - **Fix:** Delete it (2 lines).

7. **One-caller wrapper** (`flusher.py:81-84`)
   - **Problem:** `_create_processes` is a 2-line loop with a single caller, plus a comment that says the same thing.
   - **Fix:** Inline it into `__init__`.

8. **Wrong or redundant comments** (`flusher.py:32, 59, 82, 92, 178, 235, 241, 336`)
   - **Problem:** Most of these restate the code. Two are wrong:
     - L32 says "one process per shard", but the CLI default is 1 process for all shards.
     - L235 says "Check if any shard … is unhealthy", but health is tracked per process, not per shard.
   - The project and user standards say no new comments unless needed.
   - **Fix:** Delete them, and correct L32.

9. **Two defaults for one option** (`factory.py:41` and `consumers/__init__.py:433`)
   - **Problem:** The factory default `None` means one process per shard, while the CLI default `1` means a single process. The per-shard mode can only be reached by building the factory directly, as in tests.
   - **Fix:** Pick one default (1, which matches the old behavior) and use it in both places.

10. **Unrelated CLAUDE.md hunk** (`CLAUDE.md:448-458`)
    - **Problem:** The hasattr/isinstance guidance has nothing to do with the span flusher.
    - **Fix:** Move it to its own PR.

### Outside my seat (correctness, not over-engineering)

- **Hung flushers are never killed (Important)** (`flusher.py:253-257`)
  - **Problem:** The new `isinstance(process, multiprocessing.Process)` guard is always False for spawn processes. `SpawnProcess` inherits from `BaseProcess`, not from `multiprocessing.Process`. So on a "hang" restart the old process keeps running and a second one starts on the same shards. Before this patch, `kill()` ran unconditionally.
  - **Check:** `python3 -c "import multiprocessing as m; print(isinstance(m.get_context('spawn').Process(target=print), m.Process))"` prints `False`.
  - **Note:** The same guard on `terminate()` in `join` (L346) was already broken before this patch.
- **Inconsistent metric tag key:** L185 and L195 tag with `"shard"`, but L199 uses `"shards"`.

**Verdict:** fix 1-4 first. Also check the kill-guard bug above, which is more serious than any lean finding.
**Lean:** about -35 lines possible.
**Not checked:** why `django_db(transaction=True)` was added. I did not run any tests or project checks, as instructed.

**Files not reviewed:** none. All 6 files in the patch were reviewed. For CLAUDE.md I only checked scope, not content.
