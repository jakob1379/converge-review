# Decide which claim the project is trying to prove

Status: wontfix

Four experiments on the merge step moved Core F1 from 28.5 to about 40 under the Opus judge. No variant beats a named competitor on F1 or F2, and the top three are 21 to 25 points ahead. The remaining gap is not wrong findings: a verifier confirmed 98% of what the skill reports. It is true findings outside the 3 or so issues per PR that the benchmark labels.

So "beat the leaders on this benchmark's F1" is not reachable by choosing or checking findings. Options:

1. **Claim recall.** The original run finds 82% of the golden comments, 16 to 36 points above each named competitor, every interval above 0. It needs a pre-registered confirmation on data not used to pick the metric, which this benchmark cannot supply, so it would be stated as a description.
2. **Compare on truth, not on the golden set.** Run the same verifier on the competitors' stored comments and compare the share of comments that are true and the number of true findings per PR. About 1,000 verifier calls. Needs issue 03 first, and a verifier from another model family would be more convincing.
3. **Imitate the leaders.** Cut the output to the 3 most important findings per PR. The verifier's impact rating is too weak for this (62%, 33%, 16% match rates), and it changes what the skill is.
4. **Stop optimising against this benchmark.** Keep the three-seat rule, which is a real and confirmed gain, and spend the effort on the fix loop, which the benchmark never measures.

## Answer

The user chose option 2, run as experiment 005, and added that trivial issues are worth finding and fixing, so all true issues are the primary scope. No outside verifier was available; the user chose Claude only for now.
