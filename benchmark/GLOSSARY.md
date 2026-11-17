# Glossary

- **Seat**: one reviewer agent in round 1 of converge-review. There are four: `open-code-review`, `superpowers`,
  `ponytail` and `mattpocock`. The first two are correctness seats, the last two advisory seats.
- **Seat report**: the text one seat hands back. Cached in `cache/seat-reports/<pr>/<seat>.md`.
- **Merge step**: step 4 of the skill. The orchestrator dedupes the four seat reports, sets severity and gives each
  finding a verdict.
- **Finding**: one entry in the merged output, with a path, a severity, the seats that raised it and a verdict of
  `fix`, `defer` or `reject`.
- **Ledger**: the merged findings for one PR, in `out/<pr>.json`.
- **Reported finding**: a finding with verdict `fix` or `defer`. Only these are sent to the benchmark.
- **Agreement**: the number of seats that raised a finding, from 1 to 4.
- **k**: the agreement threshold. A variant with threshold k reports only findings raised by at least k seats.
- **Variant**: a changed way of producing the reported findings, scored under its own tool name such as
  `converge-review-k3`. The **baseline** is `converge-review`, which is k=1.
- **Golden comment**: an issue the benchmark's authors labelled on a PR. There are 173 across the 50 PRs.
- **Candidate**: one issue the benchmark's extraction step pulls out of a tool's review text. Candidates, not
  findings, are what the judge scores.
- **Judge**: the benchmark's LLM pipeline that extracts candidates, dedupes them and matches each to a golden
  comment. We use two: Opus 4.5 (primary) and Sonnet 4.5.
- **Profile**: the set of golden-comment categories that count. **Core** is the primary profile (158 golden
  comments). Strict and All are secondary.
- **Pooled metric**: precision, recall, F1 or F2 computed from counts summed over PRs, not averaged per PR.
- **In-sample**: a score for a rule that was chosen using the same PRs it is scored on. An upper bound.
- **Out-of-fold**: a score where each repo is scored with a rule chosen on the other four repos. The headline
  number.
