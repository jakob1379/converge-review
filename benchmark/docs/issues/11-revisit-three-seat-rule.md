# Decide whether the three-seat rule stays the default

Status: wontfix

Experiment 001 adopted the rule because it raised the benchmark's F1 by 11.7 points. Experiment 005 shows 94% of the findings it removes are true. It raises the share of comments rated above trivial from 58% to 76% and costs 31 points of recall on those issues. The user has said they would rather find and fix trivial issues than leave them out.

Options: keep the main list and appendix as they are in `skill/SKILL.md` (nothing is deleted, the appendix still lists every finding); or restore the baseline text; or order the report by the verifier's impact rating and drop the split.

Waiting on: the user's choice. It should follow the human check (issue 03), since the 94% rests on the verifier.

## Answer

Rank, don't filter. The user's preference is to find and fix trivial issues, so the shipped skill (`skill/SKILL.shipped.md`) keeps the main list and appendix but fixes both, main list first. The benchmark's F1 gain came from the filter and does not transfer to this text.
