# converge-bench

Scores `/converge-review` on Martian's offline Code Review Bench (50 PRs, 173 golden comments) and puts it next to
the stored results for CodeRabbit (`coderabbit`), cubic (`cubic-dev`, `cubic-v2`), `claude-code` and ~45 other tools.
Benchmark pinned at `withmartian/code-review-benchmark@e616e84`.

Where things stand: `docs/findings.md`. How experiments are run: `docs/methodology.md`. The log:
`docs/experiments/README.md`. Open work: `docs/issues/`.

## Runbook

1. Judging runs locally by default: `score.sh` starts `judge_proxy.py`, which answers through the `claude` CLI
   and serves Anthropic judges only. To judge through Martian's router instead, set `MARTIAN=1` and put
   `MARTIAN_API_KEY` in `vendor/code-review-benchmark/offline/.env`.
   Optional: `GH_TOKEN` in your shell if `prepare.sh` hits the unauthenticated GitHub limit (60 calls/hour).
2. `./prepare.sh`. It resumes: resolves any PR SHAs still missing, fetches repos, and ends with a dry run of one PR.
3. Smoke test one PR, and read its findings file before going further:
   `./bench.py run --limit 1`, then check `out/*.json` and `out/*.log.json` (`total_cost_usd`).
4. Full run: `./bench.py run --jobs 2`. It resumes and skips PRs that already have findings. Each PR runs in a
   detached worktree under `work/` at the PR head. The run fails a PR if it edits the checkout.
5. `./score.sh` ingests `out/`, then runs extract → dedup → judge for one tool name, under the Opus 4.5 and
   Sonnet 4.5 judges (`JUDGES="anthropic/claude-opus-4-5-20251101"` for one). Then it builds the dashboard HTML.
   It refuses to score until all 50 PRs have findings; `./score.sh --allow-partial` overrides that.
6. A variant is scored under its own name, so the baseline stays untouched:
   `TOOL=converge-review-k3 MIN_SEATS=3 ./score.sh` reports only findings raised by at least 3 seats.
   Commit a pre-registration in `docs/experiments/` first.

## What gets measured

- Benchmark mode runs skill steps 1-4 (pin, gate, round-1 review, merge with rejections) and stops. Rounds 2+ only
  verify its own fixes, so they don't change which PR issues it reports.
- Findings with verdict `fix` or `defer`, at every severity, count as the review. `reject` is dropped.
- The gate is skipped by default (`--gate skip`). The competitors don't run tests either, and running the gate means
  installing and executing five big untrusted codebases. `--gate run` turns it on.
- Each run gets `GIT_CONFIG_GLOBAL=/dev/null`, and the base blobs are fetched before it starts. Without that, a
  global `diff.external` (difftastic) turns the pinned patch into truncated side-by-side text, and the review's
  sandbox cannot fetch base blobs into the read-only bare clone.
- `CLAUDE_ARGS` (default `--permission-mode auto`) is passed to each `claude -p` call.

## Files

`bench.py` (manifest / repos / run / ingest), `prepare.sh`, `score.sh`, `test_bench.py`
(`python3 -m unittest test_bench`). `prs.json` holds base, head and merge-base per PR.
`evalstats.py` (per-PR counts, pooled metrics, paired tests), `cache_seats.py` and `cache/seat-reports/` (the raw
seat reports), `experiments/` (one folder of scripts and data per experiment), `skill/` (the skill text under test).
