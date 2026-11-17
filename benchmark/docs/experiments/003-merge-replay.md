# 003: replay the merge step, adopted text and one issue per finding

Status: done 2026-11-16. H1 (fidelity) holds. H2 (one issue per finding) inconclusive, not adopted.

## Pre-registration

This is the first experiment that runs a changed prompt. Experiments 001 and 002 filtered or reformatted the
ledgers of the original run.

**Two questions, two arms.**

- **Arm `replay`** (`converge-review-replay`): step 4 is replayed with the adopted skill text, `skill/SKILL.md`.
  Question: does the orchestrator, given the reworded step, reproduce what the filter gave in experiment 001
  (Core F1 40.2 under Opus)?
- **Arm `atomic`** (`converge-review-atomic`): the same replay with `skill/SKILL.atomic.md`, which differs from
  the adopted text in one sentence group of step 4: one issue per finding, and a seat counts toward a finding only
  if it raised that same issue. Question: does this raise F1 over the `replay` arm?

**Hypotheses.**

- H1, fidelity. `replay` scores within 3 F1 points of `converge-review-k3` under the Opus judge, and the 95% CI of
  the difference includes 0. No direction is predicted.
- H2, one issue per finding. `atomic` raises pooled Core F1 over `replay`. Minimum effect worth adopting: +3 F1
  points under the Opus judge.

**What was already seen.** Experiment 002: 181 of the 282 reported findings at k=3 hold more than one issue, and
the judge makes 1.33 candidates per finding under Opus and 1.91 under Sonnet. No replay output has been judged.

**The replay** (`replay.py`). One `claude -p` call per PR, model `claude-opus-5-5`, effort high, no tools, the
skill text as the system prompt. The user message gives the four cached seat reports and asks for step 4 and the
Rejections rule only. The ledger records `list: main` or `list: appendix` per finding. The benchmark receives the
main list with verdict `fix` or `defer`; no seat-count filter is applied afterwards, so the score depends on the
orchestrator following the rule.

**Known differences from the original run.** The original orchestrator had the repository checked out, could read
source and dispatch a verifier, and rejected 91 of 802 findings. The replay has the seat reports only and is told
to keep a finding it cannot verify. The replay is a fresh session with a different system prompt. H1 measures the
net effect of all of this together with the reworded step; it cannot separate them.

**Data.** The 50 PRs in `prs.json`, `cache/seat-reports/`, one review run, one merge run per arm. Folds: leave one
repo out, 5 repos of 10 PRs.

**Scoring.** Each arm is scored by the benchmark's real judge pipeline, once per judge.

**Selection procedure for H2, per fold on the 4 training repos**, using judged counts under the Opus judge:

1. Drop an arm whose pooled Core recall on the training repos is below 60.
2. Choose the arm with the higher pooled Core F1. A tie keeps `replay`.

**Metrics.** Primary for H2: out-of-fold pooled Core F1 under the Opus judge, against `replay`. Primary for H1:
F1 of `replay` minus F1 of `converge-review-k3` under Opus, with its 95% CI. Secondary: the same under Sonnet;
precision, recall, F2; main-list findings per PR; the share of main-list findings with three or more seats;
median claim length; candidates per main-list finding; `atomic` minus `converge-review-k3`.

**Comparisons.** Named competitors, unchanged: `coderabbit`, `claude-code`, `cubic-v2`, `qodo-extended-v2`,
`augment`.

**Tests.** Paired repo-stratified PR bootstrap, 10,000 resamples, seed 0. Paired approximate randomisation,
10,000 resamples, seed 0. Holm correction across the five competitors.

**Acceptance rule for H2.** Adopt the one-issue-per-finding text only if all hold, with `replay` as the baseline:

1. Out-of-fold F1 minus baseline F1 has a 95% CI lower bound above 0 under the Opus judge.
2. The same difference is above 0 under the Sonnet judge.
3. The difference is at least 0 in 4 or more of the 5 held-out repos (Opus).
4. Out-of-fold pooled Core recall is at least 60 under the Opus judge.
5. Cost per PR does not rise by more than 0.10 USD.

And the difference in 1 is at least the minimum effect of +3.

**What follows from H1.** If `replay` is within the stated band, the adopted text is taken to deliver what the
filter did. If it is not, the honest score of the adopted skill text is the `replay` score, the log says so, and
`replay` replaces `converge-review-k3` as the baseline for later experiments.

**Budget and stopping.** At most 90 USD in total: merge calls for two arms and judge calls for two arms. One merge
run per arm and one judge run per judge. No re-runs, no `--force`. A PR whose merge call fails to return a valid
ledger is re-run until it does, and each such re-run is logged as a deviation. An interrupted run is resumed.

**Not covered.** Merge-step noise: one merge run per arm, so run-to-run variance of the merge is not in the
intervals. Review noise (issue 01). Judge transport (issue 05).

## Results (2026-11-16)

Pre-registration commit `f04611b`. Code `241dda5`. Benchmark `e616e84`. Merge model `claude-opus-5-5`, effort
high. Judges as before, through the local CLI proxy. Cost 81.69 USD: merge calls 34.38 (adopted 16.31, atomic
18.07, failed calls included) and judge calls 47.31. Data: `replay/adopted/`, `replay/atomic/`,
`experiments/003-merge-replay/` and `results/`.

**The ledgers.**

| | `replay` | `atomic` |
|---|---|---|
| Findings in the ledgers | 928 | 1233 |
| Rejected | 17 | 20 |
| Main list | 300 (6.0 per PR) | 343 (6.9 per PR) |
| Main-list findings with three or more seats | 300 of 300 | 343 of 343 |
| Appendix findings with three or more seats | 0 of 611 | 0 of 870 |
| Median claim length, main list | 36.5 words | 28 words |
| Candidates per main-list finding, Opus / Sonnet | 1.29 / 1.74 | 1.03 / 1.27 |

**Scores, Core profile, all 50 PRs.**

| | Opus P | Opus R | Opus F1 | Opus F2 | Sonnet P | Sonnet R | Sonnet F1 | Sonnet F2 |
|---|---|---|---|---|---|---|---|---|
| Filter, `converge-review-k3` | 28.8 | 66.5 | 40.2 | 52.7 | 21.8 | 67.1 | 32.9 | 47.4 |
| `replay` | 27.6 | 63.3 | 38.5 | 50.3 | 22.5 | 65.2 | 33.4 | 47.2 |
| `atomic` | 30.0 | 64.6 | 41.0 | 52.5 | 24.6 | 62.0 | 35.2 | 47.5 |

**H1, fidelity: holds.** `replay` minus the filter is -1.8 F1 under Opus (95% CI -5.4 to +2.0) and +0.5 under
Sonnet (-3.4 to +4.7). Both are inside the band of 3 points with 0 in the interval. The orchestrator followed the
rule exactly: every main-list finding has three or more seats and no appendix finding does. The adopted skill
text is taken to deliver what the filter did. `replay` is the baseline for later merge-prompt experiments,
because it goes through the same pipeline as they will.

**H2, one issue per finding: inconclusive, not adopted.** Every fold chose `atomic`, so the out-of-fold score is
the `atomic` score.

| Judge | Out-of-fold F1 | Difference against `replay` | 95% CI | Bootstrap p | Randomisation p |
|---|---|---|---|---|---|
| Opus | 41.0 | +2.5 | -0.3 to +5.4 | 0.044 | 0.13 |
| Sonnet | 35.2 | +1.7 | -2.4 to +5.6 | 0.20 | 0.43 |

Per-repo difference under Opus: discourse +5.4, sentry +2.2, keycloak +3.6, grafana +7.7, cal.com -4.3.

Acceptance: the CI lower bound is not above 0 under Opus, and the effect is below the minimum of +3. The other
conditions pass (positive under Sonnet, 4 of 5 repos, recall 64.6). By the rule, inconclusive does not mean adopt,
and the change is not re-tested on these data.

**The mechanism worked; the gain did not follow in full.** Candidates per finding fell to 1.03 under Opus, as
intended, and claims got shorter. But splitting also raised the main list from 300 to 343 findings, so precision
rose by only 2.4 points.

**Against the named competitors** (`atomic`, the out-of-fold arm). No win is shown. Against `coderabbit`: -1.2
under Opus (CI -7.1 to +4.9), -7.6 under Sonnet (CI -14.0 to -0.7). Against `claude-code`: -6.2 and -3.5.
Against `cubic-v2`, `qodo-extended-v2` and `augment`: -21 to -25 under both judges.

**What this run says about the method.**

- The 95% interval for one arm against another on these 50 PRs is about plus or minus 3 F1 points under Opus and
  plus or minus 4 under Sonnet. A real effect smaller than that cannot be confirmed here, whatever it is.
- Two different ways of applying the same rule, filter and replay, differ by 1.8 F1 under Opus. Together with
  experiment 002, that puts pipeline noise at 1 to 2 points.
- The replay keeps more findings than the original run (928 against 802, 17 rejected against 91). It has no
  repository access, so it cannot disprove anything.

**Deviations from the pre-registration.**

- One PR (keycloak#37634, `replay` arm) was run alone first, to check the tooling. Its output was kept.
- Five merge calls returned ledgers without the `list` field and were re-run once each, as the pre-registration
  allows: sentry-greptile#5 and grafana#107534 in `replay`; grafana#94942, grafana#107534 and cal.com#7232 in
  `atomic`. The failed outputs are kept as `*.failed1.log.json`.
- The user lifted the budget cap during the run. The final cost stayed under it.

**Variants tried on these 50 PRs after this experiment.** Judged: 5 (baseline, k=3, k=3 claim only, replay,
atomic). Simulated: about 40.
