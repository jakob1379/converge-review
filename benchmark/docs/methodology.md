# Methodology

How we change the converge-review skill and decide whether a change is real. Adapted from the handoff in the T3
thread "Prompt Optimizer Framework Comparison" (`da1a1aba-1884-406d-b582-00a9873d1507`), 2026-11-16.

## What we can and cannot measure

- The only labelled data is the benchmark: 50 PRs from 5 repos (10 each), 173 golden comments, 158 in the Core
  profile.
- The grader is fixed. It is the benchmark's judge pipeline, and the 45 competitor tools were scored with it.
- Precision, recall, F1 and F2 are set metrics. The order of findings does not change the score; only which
  findings are reported does.
- A finding that matches no golden comment counts as a false positive, even when it is a real bug.
- With 50 PRs, a lead of a few F1 points over a competitor is unlikely to be significant.

## Pins

| What | Value |
|---|---|
| Benchmark | `withmartian/code-review-benchmark@e616e849755441da38f18bf3adba2c9583b03803` |
| Competitor results (sha256 prefix, as committed upstream) | Opus judge `56e38e37ce570988`, Sonnet judge `175de256f2a1717d` |
| Baseline skill | `skill/SKILL.baseline.md`, sha256 prefix `4862d335574601dd` |
| Review model | `claude-opus-5-5`, effort high, Claude Code 2.1.322, gate skipped |
| Judges | `anthropic/claude-opus-4-5-20251101` (primary), `anthropic/claude-sonnet-4-5-20250929` |
| Raw reviewer output | `cache/seat-reports/`, one run per PR |

## Known deviations from the competitors' scoring

- **Judge transport.** The benchmark calls the judge at temperature 0 through Martian's router. We call the same
  models through the local `claude` CLI (`judge_proxy.py`), which does not expose temperature. The prompts are the
  benchmark's. The size of this effect is unmeasured (issue 05).
- **GPT-5.2 judge.** Not run. The local proxy serves Anthropic models only.
- **cubic-dev.** Judged upstream against an older set of 137 golden comments. It cannot be paired with our counts
  and is left out of every test.

## Cached inputs

- Seat reports: `cache/seat-reports/<pr>/<seat>.md`. A merge-step variant is replayed on these, so it costs merge
  and judge calls only, and every variant sees the same reviewer output.
- Ledgers: `out/<pr>.json`.
- Our judge results: `results/<judge>.json`, a copy of our tools' candidates and evaluations from the vendored
  benchmark's working tree.
- Per-PR counts for each experiment: `experiments/<id>/counts.json`.

`python3 evalstats.py` must reproduce the dashboard's baseline numbers before any analysis.

## Splitting

- The PR is the unit and the repo is the group. Never split PRs at random.
- Use leave-one-repo-out cross-validation, 5 folds. In each fold, run the whole selection procedure on the other 4
  repos, apply the chosen rule to the held-out repo, and pool the out-of-fold counts over all 5 folds.
- The pooled out-of-fold score is the headline. Report which rule each fold chose.
- Keep the project to 2 or 3 discrete knobs in total: the agreement threshold k, a severity floor, a top-N cap.
  Every knob value tried counts, discarded ones included, and goes in the log.
- New unlabelled PRs cannot measure F1. Use them only for findings per PR, the share of PRs with nothing reported,
  and run-to-run stability.

## Test for "A beats B"

Both tools have per-PR counts on the same 50 PRs. `evalstats.py` implements both tests.

1. **Paired bootstrap, stratified by repo.** 10,000 resamples. Within each repo, sample its PRs with replacement,
   compute pooled F1 for A and B, and record the difference. The 95% CI is the 2.5th to 97.5th percentile. The
   one-sided p is (number of differences at or below 0, plus 1) / 10,001.
2. **Paired approximate randomisation** as a cross-check. Swap A's and B's counts per PR with probability 0.5,
   10,000 times. Report the more conservative of the two.

A win over a competitor means: the CI lower bound is above 0 under the Opus judge after a Holm correction across
the named competitors, and the difference is above 0 under the Sonnet judge. Competitors are named before the run.
Each competitor has one stored run, so its run-to-run variance is missing from the CI. Say so.

## Repeats and noise

Not done yet (issue 01). The plan from the handoff:

- Review all 50 PRs 3 times and re-run each judge twice on one run's output.
- Compute the spread of pooled F1 across review runs and across judge repeats, and the half-width h of the PR
  bootstrap CI.
- Use the smallest number of review runs R where spread / sqrt(R) is at most h / 4.

Until then, every result is one review run and one judge run per judge, and the log says so.

## Before each experiment: pre-registration

Commit `docs/experiments/NNN-<slug>.md` before running. It states:

- the hypothesis in one line, its direction, and the minimum effect worth adopting;
- the exact change, one per experiment;
- the data: PR list, folds, which cached reviewer run;
- the metrics: primary is out-of-fold pooled Core F1 under the Opus judge; secondary are Sonnet F1, precision,
  recall, F2 and findings per PR;
- the comparison: the baseline, and the named competitors for a claim;
- the test, the number of resamples, the seed, and the number of review runs and judge repeats;
- the acceptance rule, copied from below;
- a budget cap and the stopping rule: one run per experiment, no re-running to chase significance.

## After each experiment: the log

Append to the same file, and add a row to `docs/experiments/README.md`:

- date, commit SHAs, model IDs and cost;
- the path to the per-PR counts, all metrics, CIs and p-values;
- the rule each fold chose;
- every deviation from the pre-registration, and why;
- the decision: adopt, reject or inconclusive;
- the running total of variants tried on these 50 PRs.

## Acceptance rule

Adopt a change only if all hold:

1. Out-of-fold F1 minus baseline F1 has a 95% CI lower bound above 0 under the Opus judge.
2. The same difference is above 0 under the Sonnet judge.
3. The difference is at least 0 in 4 or more of the 5 held-out repos.
4. Pooled recall stays at or above the floor set in the pre-registration.
5. Cost per PR rises by no more than the amount set in the pre-registration.

Otherwise the change is rejected or inconclusive. Inconclusive does not mean adopt. Do not re-test the same change
on the same data unless the pre-registration said so.

## Optimisers

GEPA and MIPROv2 are not used. On full reviews they would cost thousands of dollars per optimisation. On cached
seat reports cost is fine, but 173 labels cannot support a free-text search: it would learn the judge's quirks.
The merge step is treated as a small decision rule, searched as a grid inside the cross-validation. Hand-edit the
merge prompt only for behaviour the rule cannot express, one change per experiment.

## What we may claim

- "On Code Review Bench (50 PRs, benchmark `<SHA>`, judge Opus 4.5), skill `<SHA>` scored F1 x (95% CI a to b);
  under the Sonnet 4.5 judge, y. Paired bootstrap against `<competitor>`'s stored results: difference d (CI), p."
- The headline is the out-of-fold estimate. An in-sample figure may be shown only when labelled as such.
- Always disclose: the skill was tuned on this benchmark; the number of variants tried; competitor results are
  single stored runs of possibly older versions; the two judges differ by up to 7 points; the judge transport
  deviation above.

## What we may not claim

- Better code review in general, or on unseen repos.
- That low precision means real false positives. The golden set is incomplete.
- A win over a competitor that is not significant under the Opus judge and positive under Sonnet. Say "comparable
  to" at most.
- Any standing against a tool we did not run the test against.

## Contamination

All 50 PRs are public, and the review model may have seen them, their fixes or their review threads. Issue 04
checks merge dates against training cutoffs and looks for near-verbatim copies of golden comments. Until it is
done, state that contamination cannot be ruled out.
