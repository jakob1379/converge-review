# 002: comment format, claim without evidence

Status: done 2026-11-16. Decision: reject.

## Pre-registration

**Hypothesis.** Sending each reported finding as its claim only, without the evidence text, raises pooled Core F1
over the adopted k=3 variant. Minimum effect worth adopting: +3 F1 points under the Opus judge.

**Why.** Experiment 001 showed the benchmark's extraction step makes 1.33 candidates per finding at k=3 under Opus
and 1.91 under Sonnet. A comment is `[Severity] claim`, a blank line, then the evidence. The evidence appears to
be split into extra candidates, and each one that matches no golden comment is a false positive.

**What was already seen.** The candidate counts above, on all 50 PRs. No claim-only review has been judged or
simulated. A back-of-envelope figure, one candidate per finding with unchanged recall, gives about F1 47 under
Opus. The risk runs the other way too: the evidence may be what lets the judge match a golden comment, so recall
may fall.

**This is partly a fit to the judge.** The change alters how the review is written, not what it found. Any gain
says the benchmark rewards short single-issue comments. It does not say the review is better for a human reader.

**The change.** One knob: the comment body, either claim plus evidence (current) or claim only
(`bench.py ingest --claim-only`). The agreement threshold stays at k=3 from experiment 001. The `[Severity]`
prefix stays. No new reviews.

**Data.** The 50 PRs in `prs.json`, the baseline ledgers in `out/`, one review run. Folds: leave one repo out, 5
repos of 10 PRs, as in experiment 001.

**Scoring.** The claim-only variant is ingested as `converge-review-k3-claim` and scored by the benchmark's real
judge pipeline, once per judge. The other arm, `converge-review-k3`, was judged in experiment 001 and is not
re-judged.

**Selection procedure, per fold on the 4 training repos** (`experiments/002-comment-format/run.py`), using judged
counts under the Opus judge:

1. Drop a format whose pooled Core recall on the training repos is below 60.
2. Choose the format with the higher pooled Core F1. A tie keeps the current format.

**Metrics.** Primary: out-of-fold pooled Core F1, Opus judge. Secondary: the same under Sonnet; precision, recall
and F2 under both; candidates per finding; the in-sample score of each format.

**Comparisons.** The baseline is now `converge-review-k3`. Named competitors, unchanged from experiment 001:
`coderabbit`, `claude-code`, `cubic-v2`, `qodo-extended-v2`, `augment`.

**Tests.** Paired repo-stratified PR bootstrap, 10,000 resamples, seed 0, 95% CI and one-sided p. Paired
approximate randomisation, 10,000 resamples, seed 0. Holm correction across the five competitors. One review run,
one judge run per judge.

**Acceptance rule.** Adopt only if all hold:

1. Out-of-fold F1 minus baseline F1 has a 95% CI lower bound above 0 under the Opus judge.
2. The same difference is above 0 under the Sonnet judge.
3. The difference is at least 0 in 4 or more of the 5 held-out repos (Opus).
4. Out-of-fold pooled Core recall is at least 60 under the Opus judge.
5. Cost per PR does not rise.

And the difference in 1 is at least the minimum effect of +3.

The recall floor stays at 60, as in experiment 001. The user was told it is provisional and asked to continue.

**A win over a competitor** means a CI lower bound above 0 under Opus after Holm, and a positive difference under
Sonnet.

**Budget and stopping.** At most 35 USD of judge calls. One judge run per judge. No re-runs, no `--force`. If a
run errors part-way, resume it.

**Not covered.** Review noise (issue 01), judge transport (issue 05), and whether a human reader is better served
by comments without evidence.

## Results (2026-11-16)

Pre-registration commit `1f165de`. Code `970328f`. Benchmark `e616e84`. Judges as in experiment 001, through the
local CLI proxy. Judge cost 24.83 USD (Opus 13.83, Sonnet 11.01). One review run, one judge run per judge. Data:
`experiments/002-comment-format/` (`counts.json`, `results.json`) and `results/`.

**Interruption.** A server restart killed the run after the Opus judge had finished and the Sonnet judge had
written 34 of 50 evaluations. The Sonnet judge was resumed and wrote the remaining 16. Nothing was re-judged.

**Scores, Core profile, all 50 PRs (in-sample).**

| Format | Opus P | Opus R | Opus F1 | Opus candidates per finding | Sonnet P | Sonnet R | Sonnet F1 | Sonnet candidates per finding |
|---|---|---|---|---|---|---|---|---|
| Claim plus evidence (current) | 28.8 | 66.5 | 40.2 | 1.33 | 21.8 | 67.1 | 32.9 | 1.91 |
| Claim only | 28.0 | 67.1 | 39.6 | 1.44 | 22.7 | 65.2 | 33.7 | 1.72 |

**Selection.** Two folds chose claim only (by 0.3 F1 each), three kept the current format.

**Out-of-fold against the baseline (`converge-review-k3`).**

| Judge | Out-of-fold F1 | F1 difference | 95% CI | Bootstrap p | Randomisation p |
|---|---|---|---|---|---|
| Opus | 38.5 | -1.8 | -3.5 to +0.1 | 0.97 | 0.11 |
| Sonnet | 32.9 | 0.0 | -1.8 to +1.7 | 0.50 | 0.96 |

**Acceptance.** Fails four of five conditions: the CI lower bound is below 0 under Opus, the difference is not
positive under Sonnet, only 3 of 5 repos are at or above 0, and the effect is below the minimum of +3. Recall
passes.

**Decision: reject.** The comment format stays as claim plus evidence.

**Why the hypothesis was wrong.** The evidence is not what gets split. Claim-only comments produce as many
candidates per finding as before (1.44 against 1.33 under Opus). The claims themselves are compound: the median
claim is 31 words, and 181 of the 282 have more than one clause or sentence. The merge step folds related issues
from several seats into one finding, and the extraction step correctly separates them again. Example, one finding
on keycloak#37634: "matcher reads the wrong offset ... and its comparison is inverted ...; the updated assertions
never verify the grant shortcut. A prefix shorter than 5 chars throws ..." became three candidates.

**What this means.**

- The inference in experiment 001's results, that the evidence is split into extra candidates, was wrong.
- The agreement count is taken on compound findings. Three seats may each have raised only one part of a finding,
  so "raised by three seats" overstates agreement on any single issue in it.
- The lever is the merge step's dedup: one issue per finding, with seats counted per issue. That is a prompt
  change and needs the merge step replayed on the cached seat reports (issue 02).
- The two formats are the same findings, judged twice from different text. Their scores differ by 0.6 F1 under
  Opus and 0.8 under Sonnet. That is a first reading of extraction-plus-judge noise: about 1 F1 point.
- The out-of-fold score (38.5) is below both arms (40.2 and 39.6). The folds selected on noise.

**Deviations from the pre-registration.** The interruption and resume above. None in procedure.

**Variants tried on these 50 PRs after this experiment.** Judged: 3 (baseline, k=3, k=3 claim only). Simulated:
about 40.
