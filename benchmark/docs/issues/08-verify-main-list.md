# Verify each main-list finding against the source before reporting it

Status: wontfix

After experiments 001 to 003, precision is 28 to 30 on findings that three seats agree on. Agreement and format are used up as levers, and the gap to the top tools is 21 to 25 F1 points.

The skill's own precision device never runs in the benchmark: step 5 makes each finding red with a failing test, and benchmark mode stops after the merge. The merge replay cannot disprove anything either, because it has no repository.

Hypothesis: a fresh verifier per main-list finding, with the checkout and the patch, that confirms the finding against source or refutes it, raises precision at a small cost in recall. Report only confirmed findings.

It also answers issue 03. If the verifier confirms most findings that match no golden comment, the precision gap is the golden set being incomplete, and no merge rule will close it.

Needs: the PR checkouts recreated under `work/`, a pre-registration, and a decision on effect size. With an interval of plus or minus 3 F1 on 50 PRs, only an effect of 4 points or more can be confirmed.

## Answer

Done in experiment 004 and rejected. The verifier confirmed 295 of 300 main-list findings, including 201 of the 204 that match no golden comment. The precision gap is true findings outside the golden set, not false findings. See `docs/experiments/004-verify-main-list.md`.
