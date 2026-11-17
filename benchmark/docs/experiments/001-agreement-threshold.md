# 001: agreement threshold in the merge step

Status: done 2026-11-16. Decision: adopt.

## Pre-registration

**Hypothesis.** Reporting only the findings raised by at least k seats, with k chosen by the procedure below,
raises pooled Core F1 over the baseline, which reports every finding. Minimum effect worth adopting: +5 F1 points
under the Opus judge.

**What was already seen.** A simulation on all 50 PRs, traced by word overlap from the baseline's judge results,
gave F1 45.1 for k=3 and 44.2 for k=4 under Opus (33.7 and 35.9 under Sonnet). The hypothesis and the knob come
from that look. Cross-validation estimates what the selection procedure delivers; it does not undo the look.

**The change.** One knob: the agreement threshold k in {1, 2, 3, 4}. In the benchmark it is applied as a filter on
the existing ledgers (`bench.py ingest --min-seats k`), which is what the merge step would output if it followed
the rule. No new reviews and no merge-prompt replay. Whether the orchestrator follows a reworded merge prompt is a
separate experiment (issue 02).

**Data.** The 50 PRs in `prs.json`, the baseline ledgers in `out/`, one review run. Folds: leave one repo out, 5
repos of 10 PRs (discourse, sentry, keycloak, grafana, cal.com; the `-greptile` and `-graphite` forks count with
their project).

**Selection procedure, run once per fold on the 4 training repos** (`run.py select`):

1. Simulate the per-PR counts for each k from the baseline's Opus judge results.
2. Drop every k whose simulated pooled Core recall on the training repos is below 60.
3. Choose the k with the highest simulated pooled Core F1. Ties go to the smaller k. If none is left, k=1.

The same procedure on all 50 PRs gives the in-sample k, reported for reference and labelled in-sample.

**Scoring.** Each k that some fold chose is ingested under the tool name `converge-review-k<k>` and scored by the
benchmark's real judge pipeline, once per judge. The out-of-fold counts take each repo's PRs from the variant its
fold chose.

**Metrics.** Primary: out-of-fold pooled Core F1, Opus judge. Secondary: the same under Sonnet; precision, recall
and F2 under both; findings per PR; the gap between simulated and judged scores for the in-sample k.

**Comparisons.** The baseline `converge-review`. Named competitors, fixed now: `coderabbit`, `claude-code`,
`cubic-v2`, `qodo-extended-v2`, `augment`. `cubic-dev` is excluded: it was judged against a different golden set.

**Tests.** Paired repo-stratified PR bootstrap, 10,000 resamples, seed 0, 95% CI and one-sided p. Paired
approximate randomisation, 10,000 resamples, seed 0, as a cross-check. Holm correction across the five
competitors. One review run, one judge run per judge.

**Acceptance rule.** Adopt only if all hold:

1. Out-of-fold F1 minus baseline F1 has a 95% CI lower bound above 0 under the Opus judge.
2. The same difference is above 0 under the Sonnet judge.
3. The difference is at least 0 in 4 or more of the 5 held-out repos (Opus).
4. Out-of-fold pooled Core recall is at least 60 under the Opus judge.
5. Cost per PR does not rise.

And the difference in 1 is at least the minimum effect of +5.

The recall floor of 60 is provisional. It was set by the agent, after seeing the simulation, on the reasoning that
recall is what converge-review is for and it should not fall below CodeRabbit's (59.5). The user should confirm or
replace it before the next experiment.

**A win over a competitor** means a CI lower bound above 0 under Opus after Holm, and a positive difference under
Sonnet. Anything else is reported as not shown.

**Budget and stopping.** At most 45 USD of judge calls. One judge run per variant per judge. No re-runs, no
`--force`. If a run errors part-way, resume it; do not restart it.

**Not covered.** Run-to-run variance of the reviews is unmeasured (issue 01). The judge runs through the local
CLI, not at temperature 0 (issue 05).

## Results (2026-11-16)

Pre-registration commit `b6771d5`. Code `4a3fe84`. Benchmark `e616e84`. Judges `claude-opus-4-5-20251101` and
`claude-sonnet-4-5-20250929` through the local CLI proxy. Judge cost 25.07 USD (Opus 13.13, Sonnet 11.94). One
review run, one judge run per judge. Data: `experiments/001-agreement-threshold/` (`selection.json`,
`counts.json`, `results.json`) and `results/`.

**Selection.** Every fold chose k=3, and so did the in-sample procedure. The out-of-fold and in-sample scores are
therefore the same variant, `converge-review-k3`. In the discourse fold k=4 had the higher simulated F1 (45.6
against 44.9) and was dropped by the recall floor.

**Scores, Core profile, pooled over 50 PRs.**

| | Opus P | Opus R | Opus F1 | Opus F2 | Sonnet P | Sonnet R | Sonnet F1 | Sonnet F2 |
|---|---|---|---|---|---|---|---|---|
| Baseline (k=1) | 17.2 | 82.3 | 28.5 | 46.9 | 12.6 | 77.2 | 21.6 | 38.1 |
| Out-of-fold (k=3) | 28.8 | 66.5 | 40.2 | 52.7 | 21.8 | 67.1 | 32.9 | 47.4 |
| Simulated k=3, before the run | 34.1 | 66.5 | 45.1 | 55.9 | 23.1 | 62.7 | 33.7 | 46.7 |

Findings per PR: 14.2 at baseline, 5.6 out-of-fold.

**Against the baseline.**

| Judge | F1 difference | 95% CI | Bootstrap p | Randomisation p |
|---|---|---|---|---|
| Opus | +11.7 | +8.3 to +14.9 | 0.0001 | 0.0001 |
| Sonnet | +11.3 | +7.8 to +14.5 | 0.0001 | 0.0001 |

Per-repo F1 difference under Opus: discourse +13.3, sentry +11.2, keycloak +10.4, grafana +9.3, cal.com +12.9.

**Against the named competitors** (out-of-fold F1 minus competitor F1; one-sided p for "we are better").

| Competitor | Opus difference | Opus 95% CI | Opus p (Holm) | Sonnet difference | Sonnet 95% CI |
|---|---|---|---|---|---|
| coderabbit | -1.9 | -7.2 to +3.5 | 0.76 (1.0) | -9.9 | -15.1 to -4.5 |
| claude-code | -7.0 | -13.6 to -0.2 | 0.98 (1.0) | -5.8 | -12.3 to +1.0 |
| cubic-v2 | -23.4 | -30.4 to -16.8 | 1.0 (1.0) | -25.6 | -34.3 to -17.1 |
| qodo-extended-v2 | -25.6 | -31.7 to -20.1 | 1.0 (1.0) | -23.7 | -30.5 to -17.3 |
| augment | -22.0 | -28.3 to -15.5 | 1.0 (1.0) | -23.6 | -29.3 to -17.8 |

No win over any named competitor is shown. Under Opus the variant is comparable to CodeRabbit on F1; under Sonnet
it is worse. It ranks 20 of 23 on Core F1 under both judges, up from 21 and 22.

**Acceptance.** All conditions pass: CI lower bound above 0 under Opus; positive under Sonnet; positive in 5 of 5
repos; recall 66.5 against a floor of 60; no cost increase; effect +11.7 against a minimum of +5.

**Decision: adopt.** The merge step reports only findings raised by three or more seats. The changed skill text is
`skill/SKILL.md`; the baseline stays in `skill/SKILL.baseline.md`.

**Deviations from the pre-registration.** None in procedure. The judge cost was 25 USD against an informal
estimate of 19, inside the 45 cap.

**What the run showed beyond the hypothesis.**

- The simulation was optimistic by 4.9 F1 points under Opus. Recall matched exactly; precision did not (34.1
  simulated, 28.8 judged).
- The cause is the benchmark's extraction step. It pulls more candidates out of each finding when the review is
  shorter: 1.10 candidates per finding at baseline and 1.33 at k=3 under Opus; 1.43 and 1.91 under Sonnet. Every
  extra candidate that matches no golden comment is a false positive. Each of our comments carries a claim plus
  its evidence, and the evidence is being split into further candidates.
- So the comment format is a lever of its own, separate from which findings are reported (issue 07).
- A simulation from the baseline's judge results is not a substitute for a judge run. Use it for selection inside
  the folds only.

**Limits.** In-sample for the choice of knob: the agreement idea came from looking at all 50 PRs. One review run,
so review noise is not in the intervals. The rule was applied as a filter on existing ledgers; the orchestrator
following the reworded merge step is untested (issue 02). Competitors are single stored runs. The judge ran through
the local CLI, not at temperature 0.

**Variants tried on these 50 PRs after this experiment.** Judged: 2 (baseline, k=3). Simulated: about 40.
