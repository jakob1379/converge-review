# 004: verify each main-list finding against the source

Status: done 2026-11-16. Decision: reject. The verifier confirmed 295 of 300 findings.

## Pre-registration

**Hypothesis.** Reporting only the main-list findings that a fresh verifier confirms against the source raises
pooled Core F1 over the `replay` arm of experiment 003. Minimum effect worth adopting: +4 F1 points under the Opus
judge. The minimum is 4 because the 95% interval for one variant against another on these PRs is about plus or
minus 3.

**Why.** After experiments 001 to 003, precision is 28 to 30 on findings that three seats agree on. The skill's
own precision device never runs in the benchmark: step 5 makes each finding fail a test, and benchmark mode stops
after the merge. The skill's Rejections rule already describes a verifier ("one fresh verifier agent with only
that finding and the patch"); this experiment applies it to every main-list finding.

**What was already seen.** The scores of experiments 001 to 003. No verifier output on these findings. The
original run dispatched a verifier twice in 50 PRs.

**A caution on what a gain would mean.** The verifier checks whether a claim is true. The benchmark counts a
finding only if it matches a golden comment. A true finding outside the golden set still counts against
precision. So a small gain here would not show the verifier is useless; the verdict table below is the evidence
for that question.

**The change.** One step added after the merge. For each of the 300 main-list findings in `replay/adopted/`,
`verify.py` starts one fresh `claude -p` session: model `claude-opus-5-5`, effort high, tools Read, Grep and Glob
only, working directory a checkout of the PR head, plus the patch file. It receives the finding's path, line,
claim and evidence, not its seats or severity. It returns `confirmed`, `refuted` or `unverifiable`. Only
`confirmed` findings stay on the main list; the others move to the appendix. The variant is
`converge-review-verified`.

**Also recorded, not used by the rule.** The verifier states whether the patch introduced the problem, and an
impact of `blocks-merge`, `worth-fixing` or `trivial`. These are collected now because 300 sessions are costly to
repeat. They feed an exploratory simulation that may suggest the next hypothesis. That simulation is in-sample and
is not a result of this experiment.

**Data.** The 50 PRs in `prs.json`, the `replay/adopted/` ledgers, one review run, one merge run, one verifier
run per finding. Folds: leave one repo out, 5 repos of 10 PRs.

**Scoring.** `converge-review-verified` is scored by the benchmark's real judge pipeline, once per judge. The
other arm, `converge-review-replay`, was judged in experiment 003.

**Selection procedure, per fold on the 4 training repos**, using judged counts under the Opus judge
(`evalstats.select_folds`):

1. Drop an arm whose pooled Core recall on the training repos is below 60.
2. Choose the arm with the higher pooled Core F1. A tie keeps `replay`.

**Metrics.** Primary: out-of-fold pooled Core F1, Opus judge, against `replay`. Secondary: the same under Sonnet;
precision, recall, F2; findings per PR; verifier cost per PR; the verdict counts; the verdicts split by whether
the finding matched a golden comment under the Opus judge (traced by word overlap, approximate).

**Comparisons.** Named competitors, unchanged: `coderabbit`, `claude-code`, `cubic-v2`, `qodo-extended-v2`,
`augment`.

**Tests.** Paired repo-stratified PR bootstrap, 10,000 resamples, seed 0. Paired approximate randomisation,
10,000 resamples, seed 0. Holm correction across the five competitors.

**Acceptance rule.** Adopt only if all hold, with `replay` as the baseline:

1. Out-of-fold F1 minus baseline F1 has a 95% CI lower bound above 0 under the Opus judge.
2. The same difference is above 0 under the Sonnet judge.
3. The difference is at least 0 in 4 or more of the 5 held-out repos (Opus).
4. Out-of-fold pooled Core recall is at least 60 under the Opus judge.
5. Cost per PR rises by no more than 3.00 USD at list price.

And the difference in 1 is at least the minimum effect of +4.

Recall has little room: `replay` is at 63.3 under Opus, so the verifier may wrongly remove at most 5 matched
golden comments before the floor of 60 fails.

**Budget and stopping.** The user is on a subscription and lifted the budget cap, so there is none. One verifier
run per finding and one judge run per judge. A verifier call that fails to return a valid verdict is re-run until
it does, and each such re-run is logged as a deviation. No verdict is re-run once it is valid. An interrupted run
is resumed.

**Not covered.** Verifier noise: one run per finding. Whether a verifier that can run code, and so make a finding
red as step 5 asks, would do better; this one can only read. Review noise (issue 01), judge transport (issue 05).

## Results (2026-11-16)

Pre-registration commit `1392430`. Code `cedacab`. Benchmark `e616e84`. Verifier model `claude-opus-5-5`, effort
high, read-only tools. Cost 61.46 USD at list price: verifier calls 36.70 (0.73 per PR, 0.12 per finding) and
judge calls 24.76. Data: `verify/adopted/`, `experiments/004-verify-main-list/` and `results/`.

**Verdicts.** 300 findings verified, none failed to return a verdict.

| | Confirmed | Refuted | Unverifiable |
|---|---|---|---|
| All 300 main-list findings | 295 | 5 | 0 |
| Matched a golden comment (96) | 94 | 2 | 0 |
| Matched no golden comment (204) | 201 | 3 | 0 |

The match column is traced by word overlap from the Opus judge's results on the `replay` arm, so it is
approximate.

**Impact, as the verifier rated it.**

| | blocks-merge | worth-fixing | trivial |
|---|---|---|---|
| Matched a golden comment (96) | 24 | 59 | 13 |
| Matched no golden comment (204) | 15 | 120 | 69 |

Five findings were in code the patch did not touch.

**Scores, Core profile, all 50 PRs.**

| | Opus P | Opus R | Opus F1 | Sonnet P | Sonnet R | Sonnet F1 |
|---|---|---|---|---|---|---|
| `replay` | 27.6 | 63.3 | 38.5 | 22.5 | 65.2 | 33.4 |
| `converge-review-verified` | 27.3 | 62.0 | 37.9 | 21.9 | 64.6 | 32.7 |

**Selection and test.** Every fold kept `replay`, so the out-of-fold variant is the baseline and the difference
is 0 under both judges. Acceptance fails: no CI above 0, no gain under Sonnet, and no effect against a minimum of
+4.

**Decision: reject.** A read-only verification step is not added to the skill. It removed 5 of 300 findings, 2 of
which had matched a golden comment.

**What the verdicts say.**

- Almost nothing the skill reports on the main list is false, by this verifier: 98% confirmed.
- 201 of the 204 findings that match no golden comment were confirmed as true. Low precision on this benchmark is
  therefore not a measure of wrong findings. It measures how many true findings fall outside the 3 or so issues
  per PR the benchmark's authors labelled.
- The verifier's impact rating separates the two groups only weakly. A finding rated `blocks-merge` matched a
  golden comment 62% of the time, `worth-fixing` 33%, `trivial` 16%.

**Exploratory simulation, in-sample, not a result.** Traced from the `replay` arm's Opus results.

| Rule | Findings | P | R | F1 |
|---|---|---|---|---|
| All main-list findings | 300 | 27.6 | 63.3 | 38.5 |
| Confirmed and not trivial | 218 | 31.2 | 54.4 | 39.6 |
| Confirmed and blocks-merge | 39 | 52.1 | 15.8 | 24.3 |

Dropping trivial findings gains about a point of F1 and takes recall below the floor of 60. No rule here is worth
a judged experiment.

**Limits.**

- The verifier is the same model family as the reviewers and was shown the finding's evidence. It may share their
  blind spots and confirm too readily. Its 98% is unvalidated until a person labels a sample (issue 03).
- It can read but not run code. A finding it confirmed may still not fail a test.
- One verifier run per finding.

**Deviations from the pre-registration.** One PR (keycloak#37634) was verified alone first to check the tooling;
its verdicts were kept. No verifier call needed a re-run.

**Variants tried on these 50 PRs after this experiment.** Judged: 6 (baseline, k=3, k=3 claim only, replay,
atomic, verified). Simulated: about 45.

## Exploratory, after the run: recall and F2 against the competitors

Not pre-registered. Chosen after seeing every result above, so it is a description, not a tested claim.

Paired bootstrap as in the method, on pooled Core recall. The original run (`converge-review`, every finding
reported) against each named competitor:

| Competitor | Opus difference in recall | 95% CI | Sonnet difference | 95% CI |
|---|---|---|---|---|
| coderabbit | +22.8 | +13.2 to +33.6 | +19.0 | +8.8 to +29.9 |
| claude-code | +34.2 | +25.6 to +42.5 | +36.1 | +26.4 to +44.9 |
| cubic-v2 | +16.5 | +6.5 to +25.1 | +16.5 | +4.5 to +26.9 |
| qodo-extended-v2 | +17.7 | +10.7 to +24.2 | +20.3 | +12.7 to +27.3 |
| augment | +17.1 | +9.7 to +24.6 | +15.8 | +8.6 to +23.1 |

Every interval is above 0 under both judges. On F2, the benchmark's default ranking metric, no variant of ours
beats `coderabbit` or the top three; the `replay` arm is level with `coderabbit` and `claude-code`.
