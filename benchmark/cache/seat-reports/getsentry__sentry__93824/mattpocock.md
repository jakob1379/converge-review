I reviewed the patch (base de11fb0166a, head 3162ad68a5c, 6 files) using `mattpocock-skills:code-review`. You asked me to do both axes myself, so I did not use sub-agents. I did not run project checks. I ran one standalone Python snippet to confirm finding S1.

## Spec
Not runnable. No spec was supplied, and the commit messages ("wip", "fix mypy", "rename", …) don't reference an issue. I can't judge whether anything is missing, out of scope, or implemented wrongly against a requirement.

## Standards
The repo has no AGENTS.md, CONTRIBUTING.md or CODING_STANDARDS.md, so I used the repo CLAUDE.md, including the hasattr→isinstance rule this patch adds. Black, isort, flake8 and mypy run through pre-commit, so I skipped anything they enforce. I've labelled the user's global ~/.claude/CLAUDE.md rules separately, since they are not repo standards.

**S1. Important.** `src/sentry/spans/consumers/process/flusher.py:254`. Also `:346`, where the same check existed before the patch.
- **Claim:** The new type check `isinstance(process, multiprocessing.Process)` is always False for the processes this class creates. So when a flusher process hangs or crashes, it is never killed. A new process is spawned for the same shards, and the hung one is left orphaned and can flush those shards at the same time as its replacement.
- **Evidence:** Processes come from `multiprocessing.get_context("spawn").Process`, which builds `SpawnProcess`. Its MRO is `(SpawnProcess, BaseProcess, object)`, so it is not a subclass of `multiprocessing.Process`.
- **Why it's a regression:** Before the patch, `kill()` was called unconditionally. This is also the exact pattern the patch adds to CLAUDE.md ("RIGHT: Use isinstance()" for unions), applied with the wrong class. The correct check is `multiprocessing.process.BaseProcess` or `isinstance(process, threading.Thread)`.
- **Failing command:**
```
python3 -I -c "import multiprocessing as m; p=m.get_context('spawn').Process(target=print); assert isinstance(p, m.Process)"
```
This raises AssertionError. I confirmed that check locally. I did not write a full test against the flusher.

**S2. Minor (judgement call, possible Speculative Generality).** `flusher.py:127`. `_create_process_for_shard` has no callers anywhere in src/ or tests/; grep finds only its definition. It is dead code.

**S3. Minor (judgement call, Mysterious Name / inconsistency).** `flusher.py:185, :195, :199`. The new metric tag is called `shard` in two places and `shards` in a third, and it holds a comma-joined list, not one shard. The existing buffer metrics use `shard_i` (`src/sentry/spans/buffer.py:372`). No documented standard covers this.

**S4. Minor.** `flusher.py:32`. The docstring says "Creates one process per shard". The new CLI default `--flusher-processes=1` (`src/sentry/consumers/__init__.py`) means one process for all shards in production. The comments at `:178` and `:235` also don't match the code next to them.

**S5. Minor (judgement call).** `flusher.py:222`: `if not process: continue` can never trigger. `flusher.py:337-341`: `process_index` and `remaining_time` don't affect anything that isn't already covered by the inner `while` deadline check.

**S6. Minor.** `tests/sentry/spans/consumers/process/test_consumer.py:62`. The added `time.sleep(0.1)`, commented "Give flusher threads time to process", does nothing. Line 15 replaces `time.sleep` with a no-op for the whole test.

**S7. Minor (user's global CLAUDE.md, not a repo rule: "test contracts, not implementation").** `test_consumer.py:115-120`. `test_flusher_processes_limit` only checks internal fields (`processes`, `num_processes`, `process_to_shards_map`). It never checks that segments from all 4 shards are actually flushed. The repo CLAUDE.md's "test user interactions, not implementation" rule is written for JS only.

**S8. Minor (Divergent Change).** `CLAUDE.md:449-458`. The hasattr/isinstance anti-pattern added to CLAUDE.md has nothing to do with the span-flusher change. The content is fine, but it belongs in its own commit or PR.

## Summary
- **Standards:** 8 findings (1 Important, 7 Minor). The worst is S1: the new restart path never kills spawned flusher processes, so a stuck process can keep flushing the same shards alongside its replacement.
- **Spec:** not runnable, no spec.

## Files not reviewed
None. I reviewed all 6 files in the patch: CLAUDE.md, src/sentry/consumers/__init__.py, factory.py, flusher.py, test_consumer.py and test_flusher.py.

## Not checked (outside this standards/spec seat)
- `spans.buffer.max-flush-segments` now applies per process, so the total flush budget grows with the number of flusher processes.
- `submit()` now makes one cluster-wide `get_memory_info` call per buffer instead of one in total.
- With no assigned shards, no flusher process starts at all.
- I didn't run pytest or mypy.
