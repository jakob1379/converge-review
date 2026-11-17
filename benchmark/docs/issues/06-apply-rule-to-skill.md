# Apply the adopted merge rule to the installed skill

Status: ready-for-human

The installed skill is managed by home-manager and is read-only here. Experiment 001 was adopted: apply the diff between `skill/SKILL.baseline.md` and `skill/SKILL.md` to the Nix config. The rule was tested as a filter on existing ledgers; whether the orchestrator follows the reworded step is issue 02.

## Progress

Branch `feat/converge-review-agreement-ranking` in `jakob1379/nix-config` (commit 878d752) changes `dotfiles/skills/converge-review/SKILL.md`. The text is `skill/SKILL.shipped.md`, not `skill/SKILL.md`: the appendix is fixed after the main list instead of left unfixed (issue 11). Not pushed: the local GitHub login does not work from here. Waiting on: the user to push and open the PR.
