# Experiment log

One file per experiment. The pre-registration is committed before the run; results are appended to the same file.
Method: `docs/methodology.md`.

| ID | Change | Status | Out-of-fold F1, Opus | Decision |
|---|---|---|---|---|
| [001](001-agreement-threshold.md) | Report only findings raised by at least k seats | done | 40.2 against 28.5 (difference +11.7, 95% CI +8.3 to +14.9) | adopt k=3 |
| [002](002-comment-format.md) | Send each finding as its claim, without the evidence (k=3 kept) | done | 38.5 against 40.2 (difference -1.8, 95% CI -3.5 to +0.1) | reject |
| [003](003-merge-replay.md) | Replay the merge step: adopted text, and one issue per finding | done | replay 38.5 (within noise of the filter's 40.2); one issue per finding 41.0 against 38.5 (difference +2.5, 95% CI -0.3 to +5.4) | prompt confirmed; one issue per finding inconclusive, not adopted |
| [004](004-verify-main-list.md) | Report only main-list findings a verifier confirms against source | done | 38.5 against 38.5 (no fold chose it; in-sample 37.9) | reject; the verifier confirmed 295 of 300 findings |
| [005](005-pooled-truth.md) | Compare tools on verified truth with a pooled set of issues, not on the golden set | run, provisional | not an F1 experiment: 96% of comments true and 740 of 990 true issues found, against 84 to 94% and 138 to 247 for the competitors | both hypotheses hold; the human check is still to do |

## Variants tried on these 50 PRs

The count matters: every look at the data is a chance to fit noise.

**Scored by the real judge:** 6 (the baseline; k=3 in experiment 001; k=3 claim only in experiment 002; replay and atomic in experiment 003; verified in experiment 004).

**Spent so far, at list price:** reviews 184 USD; judge calls about 171 USD; merge replays 34 USD; verifier calls 37 USD in experiment 004 and 507 USD in experiment 005; grouping 5 USD.

**Simulated only, before experiment 001** (from the baseline's judge results, in-sample, all 50 PRs seen):

- severity cuts: Critical only, Critical and Important, each severity alone (5)
- agreement thresholds k = 1, 2, 3, 4, and exactly 1, 2, 3, 4 seats (8)
- seat subsets: all 14 combinations of 1 to 3 seats
- both correctness seats; k at least 2 or Critical; k at least 3 or Critical (3)
- agreement by severity grid (12 cells)

That is about 40 simulated cuts. The hypothesis of experiment 001 came out of them.

**Simulated in experiment 004:** 5 rules on the verifier's verdict and impact rating. None was worth a judged run.
