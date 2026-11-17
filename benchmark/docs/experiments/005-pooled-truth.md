# 005: compare the tools on verified truth, with a pooled set of issues

Status: run 2026-11-16, provisional. Both hypotheses hold under the verifiers. The human check is still to do.

## Pre-registration

**Why.** Experiment 004 found that a verifier confirmed 295 of the 300 findings three seats agreed on, including
201 of the 204 that match no golden comment. The benchmark's precision therefore counts true findings as errors
when they fall outside the 3 or so labelled issues per PR. This experiment replaces the golden set with a pooled
set of verified issues and asks whether converge-review finds more true issues than the named competitors, and
whether its comments are as often true.

**Design, from the T3 thread `28461a89-5f77-4ab5-b841-22caffed96f8`.** Pooled ground truth, the usual method when
nobody can list every true answer:

1. **Pool** (`pool.py`). Per PR, take the Opus judge's extracted candidates for seven sources: `converge-review`
   (the original run, every finding), `converge-review-replay` (the adopted three-seat rule), `coderabbit`,
   `claude-code`, `cubic-v2`, `qodo-extended-v2` and `augment`. Add the golden comments as an eighth source. That
   is 2,337 comments.
2. **Merge duplicates, blind.** One `claude -p` call per PR (`claude-opus-5-5`, no tools) receives the comments
   shuffled and without their source, groups those that describe the same defect, and writes one neutral claim
   per group. A group is an **issue**.
3. **Verify, blind** (`verify.py`). One fresh read-only session per issue, with a checkout of the PR head and the
   patch. It sees the neutral claim and the path, never the source or the original wording. It returns
   `confirmed`, `refuted` or `unverifiable`, whether the patch introduced the problem, and an impact of
   `blocks-merge`, `worth-fixing` or `trivial`.
4. **Two verifiers.** Primary: `claude-fable-5-2`, a different model from the reviewers. Second:
   `claude-opus-5-5`, the reviewers' own model. Both at effort high.
5. **Human check.** After the run, `run.py sheet` draws 15 issues per tool for six tools (90 in all), up to 5 of
   each 15 from issues the primary verifier did not confirm. The sheet shows the claim, the path and the PR, and
   nothing else. The user labels each true or false. `run.py agreement` compares.

**Deviation from the design, decided before the run.** The design called for a verifier from another model
family. None is available: no outside CLI is installed and the user chose to proceed with Claude only. So this is
Claude models checking reviews, some of them written by Claude models. Blind neutral claims, a second Claude model
and the human check are the mitigations. The pool is kept so an outside verifier can be run on it later.

**Definitions.**

- A comment is **true** if its issue is `confirmed`. `unverifiable` counts as not true.
- **Truth precision** of a tool: its true comments over its comments, pooled over the 50 PRs.
- **Pooled recall** of a tool: the confirmed issues it has a comment in, over all confirmed issues in the pool
  from any source, golden comments included.
- Two scopes. **All true issues** is primary: the user would rather find and fix a trivial issue than leave it
  out. **True and not trivial** (impact `worth-fixing` or `blocks-merge`) is secondary, to show how much of any
  lead is nits.

**Hypotheses, for `converge-review` (the original run) under the primary verifier and the primary scope.**

- H1, recall. Its pooled recall is higher than each named competitor's.
- H2, precision. Its truth precision is not more than 5 points below each named competitor's.

The same two are reported for `converge-review-replay` as a secondary analysis.

**Tests.** Paired repo-stratified PR bootstrap, 10,000 resamples, seed 0, on the difference in pooled recall and
in truth precision against each of the five competitors. Holm correction across the five for H1.

**Decision rules.**

- H1 holds against a competitor if the 95% CI lower bound of the recall difference is above 0 and the
  Holm-adjusted one-sided p is below 0.025, under the primary verifier, and the difference is above 0 under the
  second verifier.
- H2 holds against a competitor if the 95% CI lower bound of the precision difference is above -5 under the
  primary verifier. Precision is called higher only if that bound is above 0.
- "Outperforms on both" is claimed against a competitor only if H1 holds and the precision bound is above 0.
  "Finds more at the same accuracy" is claimed if H1 and H2 hold.
- Every claim is provisional until the human check passes: the user agrees with the primary verifier on at least
  80% of the labelled issues, and for no tool is the share of verifier-confirmed issues the user calls true more
  than 20 points below the highest tool's share. If the check fails, the results are reported as unvalidated.

**Also reported.** Counts of comments, true comments and issues found per tool and per PR. The verdict and impact
counts. The share of golden comments whose issue the verifier confirms, as a check on the verifier: the golden
comments were labelled true by the benchmark's authors, so a low share means a strict or mistaken verifier.
Agreement between the two verifiers, overall and per tool, with Cohen's kappa.

**What was already seen.** Experiments 001 to 004. In particular, the original run finds 82% of the golden
comments and reports about 15 candidates per PR against about 3 for the leaders, so a recall lead on a pooled set
is expected. Recall against a pool rewards volume: a tool that reports more true things defines more of the pool.
The precision test and the not-trivial scope are what make the comparison informative.

**Limits known in advance.**

- The pool only contains issues some tool or the golden set raised. Recall is relative to that pool.
- Both of our variants are in the pool, so our own findings enlarge it. This raises nobody's recall but ours.
- The neutral claim is a rewrite. It may sharpen a vague comment or lose the detail that made one wrong.
- The verifier reads code and does not run it.
- Candidates come from the Opus judge's extraction, which splits long comments into several candidates.
- One review run, one merge, one grouping run, one run per verifier.

**Budget and stopping.** No cap; the user is on a subscription. One grouping call per PR and one verifier call per
issue per verifier. A call that fails to return valid output is re-run until it does, and each such re-run is
logged. No valid output is re-run. An interrupted run is resumed.

## Results (2026-11-16)

**Status of every number below: provisional.** The human check has not been done. The sheet is
`experiments/005-pooled-truth/labels.csv`.

Pre-registration commit `201c0bb`. Code `c39ad22`. Benchmark `e616e84`. Cost at list price 511.56 USD: grouping
4.54, primary verifier 367.91 (0.33 per issue), second verifier 139.11 (0.13 per issue). Data: `pool/`,
`verify/pool-fable/`, `verify/pool-opus/`, `experiments/005-pooled-truth/results.json`.

**The pool.** 2,337 comments became 1,109 issues. 651 were raised by one source only, 21 by all eight. 543 were
raised only by our two variants, and 19 only by the golden set.

**Verdicts.**

| Verifier | Confirmed | Refuted | Unverifiable | Confirmed: blocks-merge / worth-fixing / trivial |
|---|---|---|---|---|
| `claude-fable-5-2` (primary) | 990 | 107 | 12 | 59 / 516 / 415 |
| `claude-opus-5-5` | 955 | 144 | 10 | 68 / 472 / 415 |

The two agree on confirmed-or-not for 94.3% of issues, kappa 0.74. Per tool, agreement is 93% to 97%. Kappa is
0.76 to 0.82 for the competitors and the golden set, and 0.55 to 0.58 for our two variants, where almost
everything is confirmed and kappa has little to work with.

**Primary scope: all true issues, primary verifier.** 990 true issues in the pool.

| Source | Comments | True | Issues found | Pooled recall | Issues found per PR |
|---|---|---|---|---|---|
| `converge-review` (original run) | 781 | 96.3% | 740 | 74.7% | 14.8 |
| `converge-review-replay` (three-seat rule) | 387 | 98.2% | 354 | 35.8% | 7.1 |
| `coderabbit` | 318 | 84.3% | 247 | 24.9% | 4.9 |
| `augment` | 178 | 92.1% | 161 | 16.3% | 3.2 |
| `claude-code` | 173 | 94.2% | 152 | 15.4% | 3.0 |
| `cubic-v2` | 175 | 86.3% | 142 | 14.3% | 2.8 |
| `qodo-extended-v2` | 152 | 92.1% | 138 | 13.9% | 2.8 |
| golden comments | 173 | 88.4% | 149 | 15.1% | 3.0 |

**H1, recall: holds against all five.** `converge-review` minus the competitor, in points of pooled recall:

| Competitor | Primary verifier | 95% CI | Holm p | Second verifier |
|---|---|---|---|---|
| coderabbit | +49.8 | +44.7 to +55.0 | below 0.001 | +49.6 |
| claude-code | +59.4 | +55.4 to +63.1 | below 0.001 | +59.5 |
| cubic-v2 | +60.4 | +55.6 to +64.8 | below 0.001 | +61.0 |
| qodo-extended-v2 | +60.8 | +57.5 to +63.9 | below 0.001 | +60.7 |
| augment | +58.5 | +54.5 to +62.2 | below 0.001 | +58.8 |

**H2, precision: holds against all five.** `converge-review` minus the competitor, in points of truth precision:

| Competitor | Primary verifier | 95% CI | Not more than 5 below | Higher | Second verifier, with CI |
|---|---|---|---|---|---|
| coderabbit | +12.0 | +7.3 to +16.9 | yes | yes | +10.1 (+5.5 to +15.1) |
| cubic-v2 | +10.0 | +4.7 to +16.0 | yes | yes | +11.2 (+5.8 to +17.2) |
| augment | +4.2 | +0.6 to +8.2 | yes | yes | +4.1 (-0.1 to +8.8) |
| qodo-extended-v2 | +4.2 | -0.4 to +9.1 | yes | no | +1.4 (-2.8 to +6.0) |
| claude-code | +2.1 | -1.7 to +6.3 | yes | no | +0.4 (-3.3 to +4.6) |

**What may be claimed, by the pre-registered rules, once the human check passes.**

- Against `coderabbit`, `cubic-v2` and `augment`: outperforms on both. For `augment` the precision lead does not
  hold under the second verifier, so that one is the weakest of the three.
- Against `claude-code` and `qodo-extended-v2`: finds more at the same accuracy.

**Secondary scope: true and not trivial, primary verifier.** 575 such issues in the pool. Here precision is the
share of a tool's comments that are true and rated above trivial.

| Source | True and not trivial | Issues found | Pooled recall | Issues found per PR |
|---|---|---|---|---|
| `converge-review` (original run) | 58.4% | 446 | 77.6% | 8.9 |
| `converge-review-replay` (three-seat rule) | 75.5% | 267 | 46.4% | 5.3 |
| `qodo-extended-v2` | 83.6% | 125 | 21.7% | 2.5 |
| `augment` | 77.0% | 134 | 23.3% | 2.7 |
| `claude-code` | 75.1% | 119 | 20.7% | 2.4 |
| `cubic-v2` | 70.9% | 115 | 20.0% | 2.3 |
| `coderabbit` | 55.0% | 158 | 27.5% | 3.2 |
| golden comments | 69.4% | 116 | 20.2% | 2.3 |

- The recall lead is unchanged in this scope: +50 to +58 points, every interval above +45.
- The precision picture reverses. The original run is 12 to 25 points below `claude-code`, `cubic-v2`,
  `qodo-extended-v2` and `augment`, with every interval below 0, and level with `coderabbit`. About 4 in 10 of its
  true comments are rated trivial.
- The three-seat variant is level with `claude-code`, `cubic-v2` and `augment`, below `qodo-extended-v2` (-8.1,
  CI -14.7 to -1.9), and finds about twice as many non-trivial issues as any competitor.

**What the three-seat rule removes.** 378 issues appear in the original run and not in the three-seat variant.
The primary verifier confirmed 356 of them (94%). So the rule adopted in experiment 001 does not remove wrong
findings. It removes true ones, mostly low-impact: it lifts the non-trivial share from 58% to 76% and costs 31
points of non-trivial recall. Whether that trade is wanted depends on the reader, and the user has said they would
rather see the trivial issues.

**What this says about the benchmark.**

- The golden comments cover 149 of the 990 verified true issues, and 116 of the 575 rated above trivial. A tool is
  scored against a fifth of what the six tools found between them.
- The verifier confirmed 88% of the golden comments' issues (85% under the second verifier). So about 1 golden
  comment in 8 is either wrong, unverifiable from source, or was distorted by the neutral rewrite. That is also the
  floor on how strict the verifier is: it does not confirm everything.

**Limits, beyond those in the pre-registration.**

- The two tools with the highest truth precision after ours are `claude-code` and ours: all three Claude-written.
  The non-Claude tools score 84% to 92%. That is what a family bias in the verifier would look like, and also what
  a real difference would look like. Only the human check, or an outside verifier, can tell them apart.
- Pooled recall rewards volume. 543 of the 1,109 issues are ours alone, so our recall is high partly because we
  defined half the pool. The precision columns and the per-PR counts are the comparable numbers.
- Impact ratings come from one verifier call and decide the whole secondary scope. Both verifiers rated the same
  number of confirmed issues trivial (415), which is some reassurance, not a validation.

**Deviations from the pre-registration.**

- One PR was grouped alone and one was verified alone first, to check the tooling. Their outputs were kept.
- One grouping call (cal.com#11059) left a comment unassigned and was re-run once.
- Three calls of the second verifier returned malformed JSON and were re-run once each (sentry-greptile#5,
  grafana#107534, discourse-graphite#2).

**Variants and looks.** No new variant of the skill was judged. This experiment scored existing outputs on a new
measure, chosen after experiments 001 to 004.
