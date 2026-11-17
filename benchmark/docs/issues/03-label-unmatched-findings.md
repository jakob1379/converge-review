# Label the blind sheet of 90 issues for experiment 005

Status: ready-for-human

Every result of experiment 005 is provisional until a person checks the verifier. The sheet is `experiments/005-pooled-truth/labels.csv`: 90 issues, 15 sampled for each of six tools, in random order, with no tool names and no verdicts.

For each row, open the pull request, find the code the claim describes, and fill in `true_or_false` with `true` or `false`. `impact` and `notes` are optional. Do not open `labels.key.json` first.

Then run `python3 experiments/005-pooled-truth/run.py agreement`. The check passes if you agree with the primary verifier on at least 80% of rows, and no tool's verifier-confirmed issues are true much less often than another's (a gap above 20 points fails).

This replaces the earlier plan to label 30 unmatched findings.
