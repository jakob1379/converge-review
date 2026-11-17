# Findings

What is known so far. All numbers are pooled over 50 PRs, Core profile, one review run and one judge run per
judge. Analyses marked "simulated" trace each judged candidate back to its finding by word overlap; they are
approximate and in-sample.

## Baseline (2026-11-14)

Skill `skill/SKILL.baseline.md`, `claude-opus-5-5` at high effort, gate skipped. 183.81 USD for 50 PRs: 3.68 per
PR on average, median 3.45, range 2.07 to 9.91. Local judging cost about 49 USD.

| Tool | Opus P | Opus R | Opus F1 | Opus F2 | Sonnet P | Sonnet R | Sonnet F1 | Sonnet F2 |
|---|---|---|---|---|---|---|---|---|
| converge-review | 17.2 | 82.3 | 28.5 | 46.9 | 12.6 | 77.2 | 21.6 | 38.1 |
| CodeRabbit | 32.6 | 59.5 | 42.2 | 51.1 | 33.8 | 58.2 | 42.8 | 50.9 |
| Claude Code | 46.3 | 48.1 | 47.2 | 47.7 | 36.5 | 41.1 | 38.7 | 40.1 |
| Cubic v2 | 61.5 | 65.8 | 63.6 | 64.9 | 56.5 | 60.8 | 58.5 | 59.9 |
| Augment | 59.5 | 65.2 | 62.2 | 64.0 | 52.4 | 61.4 | 56.6 | 59.4 |
| Qodo Extended v2 | 67.1 | 64.6 | 65.8 | 65.1 | 56.2 | 57.0 | 56.6 | 56.8 |

- converge-review ranks 21 of 23 on F1 under Opus and 22 of 23 under Sonnet.
- It has the highest recall in the set and the lowest precision. It reports about 14 findings per PR (711 over 50
  PRs); the others report 3 to 7.5.
- It finds every golden comment on 26 of 50 PRs and none on 1. The best competitor on that count manages 22.

## Severity labels do not rank the findings

Simulated, Opus judge.

| Severity given by the merge step | Findings | Precision |
|---|---|---|
| Critical | 22 | 73% |
| Important | 210 | 27% |
| Minor | 528 | 12% |

- Critical is trustworthy, but it is 3% of the output.
- 46% of the matched golden comments were filed as Minor, including 4 the benchmark rates Critical and 14 it rates
  High.
- Dropping Minor would raise precision to about 31% and roughly halve recall.

## Seats overlap, and agreement ranks the findings

Simulated, Opus judge. "Alone" scores only the findings a seat took part in.

| Seat | Findings | Only this seat | Alone P | Alone R | Alone F1 | Recall lost if removed | Cost per PR |
|---|---|---|---|---|---|---|---|
| open-code-review | 388 | 18 | 28.3 | 75.3 | 41.2 | 1.3 | 0.79 |
| superpowers | 466 | 54 | 24.1 | 76.6 | 36.7 | 1.9 | 0.87 |
| ponytail | 350 | 90 | 22.2 | 52.5 | 31.2 | 1.3 | 0.50 |
| mattpocock | 417 | 61 | 23.3 | 65.2 | 34.3 | 0.6 | 0.71 |

The orchestrator costs a further 0.79 per PR. The cost split is estimated from token use in the transcripts.

| Raised by | Findings | Golden comments matched | Precision, Opus | Precision, Sonnet |
|---|---|---|---|---|
| 1 seat | 223 | 8 | 3.4% | 2.7% |
| 2 seats | 206 | 17 | 7.9% | 5.7% |
| 3 seats | 142 | 36 | 23.4% | 15.0% |
| 4 seats | 140 | 69 | 44.8% | 31.2% |

- No single seat is essential. Removing any one costs at most 1.9 recall points.
- 223 findings came from one seat only, and 8 matched a golden comment.
- The advisory seats do not stay in their lanes. `ponytail` is specified as "over-engineering only" and takes part
  in 350 findings. `mattpocock` checks spec and standards, and the benchmark runs have no spec.
- Agreement separates matches from non-matches far better than severity does. The skill text calls agreement
  between seats "weak evidence".

## Not known

- Run-to-run variance of the reviews (issue 01).
- Whether the findings that match no golden comment are real bugs, trivia or wrong (issue 03).
- Whether the model saw these PRs in training (issue 04).
- The effect of judging through the local CLI instead of the benchmark's API settings (issue 05).
- Whether steps 5 and 6 of the skill, the fix loop, work. The benchmark stops after the merge.

## Experiments

Log: `docs/experiments/README.md`.

- **001, agreement threshold: adopted.** Reporting only findings raised by three or more seats lifts Core F1 from
  28.5 to 40.2 under Opus (gain +11.7, 95% CI +8.3 to +14.9) and from 21.6 to 32.9 under Sonnet. Recall falls from
  82.3 to 66.5, and findings per PR from 14.2 to 5.6. No win over a named competitor is shown: comparable to
  CodeRabbit under Opus, worse under Sonnet, and 22 to 26 points behind Cubic v2, Augment and Qodo Extended v2.
- **002, claim-only comments: rejected.** Dropping the evidence text changes nothing: out-of-fold F1 38.5 against
  40.2 under Opus (difference -1.8, 95% CI -3.5 to +0.1) and 32.9 against 32.9 under Sonnet.
- **Findings are compound.** The benchmark's extraction step makes 1.33 candidates per finding at k=3 under Opus
  and 1.91 under Sonnet, and the extra candidates count as false positives. The cause is the claims, not the
  evidence: the median claim is 31 words and 181 of 282 hold more than one issue. The merge step folds related
  issues into one finding. It also means the agreement count is taken on compound findings and overstates
  agreement on any single issue. One issue per finding, with seats counted per issue, is the next lever (issue 02).
- **Judge noise, first reading.** The same findings judged from two different texts differ by 0.6 F1 under Opus
  and 0.8 under Sonnet.
- **003, merge replay: the prompt works.** Replaying step 4 with the adopted skill text scores F1 38.5 under Opus
  and 33.4 under Sonnet, within noise of the filter (40.2 and 32.9). The orchestrator put every finding with
  three or more seats on the main list and nothing else.
- **003, one issue per finding: inconclusive, not adopted.** F1 41.0 against 38.5 under Opus (difference +2.5,
  95% CI -0.3 to +5.4) and 35.2 against 33.4 under Sonnet. The judge now makes 1.03 candidates per finding, as
  intended, but splitting also lengthens the main list from 300 to 343 findings.
- **What these 50 PRs can resolve.** The 95% interval for one variant against another is about plus or minus 3 F1
  points under Opus and 4 under Sonnet. Changes worth less than that cannot be confirmed on this data.
- **004, verify each finding against source: rejected.** A fresh read-only verifier confirmed 295 of the 300
  main-list findings, so filtering on its verdict changes nothing (F1 37.9 against 38.5 under Opus).
- **The findings are true; most are not in the golden set.** Of the 204 main-list findings that match no golden
  comment, the verifier confirmed 201. Precision on this benchmark does not measure wrong findings. It measures
  how many true findings fall outside the 3 or so issues per PR that the benchmark's authors labelled. The
  verifier is the same model family as the reviewers, so this needs a human-labelled sample to stand (issue 03).
- **Impact ratings separate golden from non-golden only weakly.** A finding the verifier rated blocks-merge
  matched a golden comment 62% of the time, worth-fixing 33%, trivial 16%.
- **Recall is the one clear lead (exploratory).** The original run finds 82% of the golden comments. That is 16
  to 36 points more than each of the five named competitors, with every 95% interval above 0 under both judges.
  This comparison was chosen after seeing the results, so it is a description, not a tested claim.
- **005, compared on verified truth: provisional, pending the human check.** Every tool's comments were pooled
  into 1,109 issues and each was verified blind against source by two Claude models. Under the primary verifier,
  96% of the original run's comments are true, against 84% to 94% for the five competitors, and it finds 740 of
  the 990 true issues, against 138 to 247. By the pre-registered rules it outperforms `coderabbit`, `cubic-v2` and
  `augment` on both, and finds more at the same accuracy than `claude-code` and `qodo-extended-v2`.
- **The lead is thinner on issues above trivial.** About 4 in 10 of the original run's true comments are rated
  trivial. Counting only the rest, it still finds 446 issues against 115 to 158, but the share of its comments
  that qualify (58%) is 12 to 25 points below four of the five competitors.
- **The three-seat rule is an importance filter, not a truth filter.** 94% of the findings it removes are true.
  It raises the non-trivial share from 58% to 76% and costs 31 points of non-trivial recall. The user has said
  they would rather see the trivial issues, which argues against the rule as the default.
- **The golden set covers a fifth of the true issues.** 149 of 990, and 116 of the 575 rated above trivial. The
  verifier confirmed 88% of the golden comments themselves.
- **Where the skill stands on the benchmark's own F1.** F1 38 to 41 under Opus, depending on the variant. No win over a named competitor is
  shown. CodeRabbit (42.2) is within noise under Opus and ahead under Sonnet. Cubic v2, Augment and Qodo Extended
  v2 are 21 to 25 points ahead. Precision is still 28 to 30 on findings that three seats agree on, so agreement
  alone will not close that gap.
