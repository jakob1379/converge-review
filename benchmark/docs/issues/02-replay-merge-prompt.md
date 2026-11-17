# Replay the merge step on cached seat reports with a changed prompt

Status: wontfix

Two open questions, both answered by replaying step 4 on `cache/seat-reports/` and judging the output. No new reviews. Each arm needs a pre-registration.

1. **Does the orchestrator follow the reworded merge step?** Experiment 001 applied the three-seat rule as a filter on the old ledgers (Core F1 40.2 under Opus). Replay with `skill/SKILL.md` and compare.
2. **Does one issue per finding help?** Experiment 002 showed findings are compound: 181 of 282 hold more than one issue, the judge splits them, and the agreement count overstates agreement on each issue. Change the merge step to write one issue per finding and count seats per issue.

Known limit of a replay: the original orchestrator had the repository checked out and rejected 91 findings, some after reading source. A replay without the checkout can only use what is in the seat reports. Recreating the checkouts makes the replay a full agent session and costs more.

Cost per arm: one merge call per PR (about 10 to 15 USD for 50) plus judge calls (about 25 USD).

## Answer

Done in experiment 003. The orchestrator follows the reworded merge step: the replay scores within noise of the filter and puts exactly the findings with three or more seats on the main list. One issue per finding was inconclusive (+2.5 F1 under Opus, 95% CI -0.3 to +5.4) and is not adopted. See `docs/experiments/003-merge-replay.md`.
