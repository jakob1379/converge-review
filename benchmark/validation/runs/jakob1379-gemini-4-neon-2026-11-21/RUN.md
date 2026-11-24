# Gemini 4 Neon verification run, 2026-11-21 to 2026-11-23

Status: **complete.** All 181 sampled issues across the 48 ledgers have a verdict, and `run.py external` compares all
181. The Google AI Pro quota ran out several times; the run was resumed across four quota windows by re-running the
unchanged step 9 command, which re-runs only the issues without a verdict.

## Pins

| Pin | Value |
|---|---|
| Repository commit | `093b974bb09b3269ce24c76012bc5d224a61f244` (adds the Gemini backend; run from this commit) |
| Backend | `verify.py --cli gemini`: Antigravity ACP server `antigravity-acp-1.4.1` (`agy_acp_server`) |
| Account | Google AI Pro (`g1-pro-tier`), cached Google login (`authenticate` with `oauth-personal`) |
| Model | `gemini-4-neon` |
| Reasoning effort | `high` (session option `thinking_level`) |
| Parallelism | `verify.py` defaults: `--pr-jobs 2`, `--jobs 4` |
| Timeout | `verify.py` default: 20 minutes per finding |
| Sample checksum | `48254a6eccedc13b103fd26c143b15c7e75144381777f625ef8c68a28e00aa20`, as in the README |

## Commands

`BENCH_WORK` was set to a directory outside the repository (a session scratch directory). Times are from
`times.txt`.

1. Pilot, 14:37 to 14:45:
   `python3 verify.py --cli gemini --model gemini-4-neon --effort high --ledgers validation/sample --out "$RUN" --only calcom__cal.com__8330`.
   Result: `ok, 4 of 4 confirmed`.
2. Full run, 14:45 to 15:14: the same command without `--only`. Result: 5 PRs `ok`, 2 `no ledger, skipped`,
   43 with missing verdicts.
3. Partial run frozen in commit `0ec2f6c` and compared in `b99e961`.
4. Resumed rounds, 2026-11-21 21:58 to 2026-11-23 23:40: the same full-run command, started by an automated runner
   (below) whenever a quota probe succeeded. Output appended to `verify.log`; rounds and probes in `rounds.log`.
5. Frozen in the commit `chore(validation): complete gemini-4-neon verification run`, then
   `python3 experiments/005-pooled-truth/run.py external "$RUN" | tee "$RUN/external.txt"`.

## Failures

Every failed call raised `ValueError: substring not found`: the reply held no JSON object. Each one is kept as
`<n>.failed.txt` (152 files: a later failure of the same issue overwrites the file; a later verdict sits beside it as
`<n>.json`).

| Time (start) | verify.py call | Open failures at start | Outcome |
|---|---|---|---|
| 11-21 14:37 | pilot (`--only calcom__cal.com__8330`) | 0 | 4 verdicts |
| 11-21 14:45 | full run | 0 | 29 verdicts total; 152 failed; manual prompt: "Usage Limit Reached ... reset in 4 hours, 23 minutes" |
| 11-21 21:58 | resumed round | 152 | stopped after 14 PR lines without a summary; 57 verdicts at the next round |
| 11-22 00:58 | resumed round | 124 | stopped after 26 PR lines without a summary; 86 verdicts at the next round |
| 11-22 03:58 | resumed round | 95 | ended 04:16: 106 verdicts; 75 failed; next probe: limit reached, reset in 1 hour, 21 minutes |
| 11-22 06:13 | resumed round | 75 | ended 06:43: 141 verdicts; 40 failed; next probe: limit reached, reset in 6 days, 7 hours |
| 11-22 07:43 | resumed round (probe had succeeded) | 40 | ended 07:44: 141 verdicts; all 40 failed within about a minute |
| 11-23 23:06 | resumed round | 40 | ended 23:40: 181 verdicts, no failures |

The two rounds that stopped without a summary left no record of their own failures; the runner logged a new round
with a lower open-failure count three hours later. `rounds.log` also shows gaps longer than the runner's one-hour
sleep (11-22 16:46 to 11-23 07:01, 11-23 13:31 to 23:06).

Totals: 307 logged failed calls (152 + 75 + 40 + 40), plus any in the two stopped rounds. 6 re-runs of the step 9
command after the first full run, 8 `verify.py` calls in all. Every failure burst ended with the quota probe or a
manual prompt reporting the usage limit, and the last round had none, so the failures are quota, not reply-format,
failures.

## Quota windows used

| Window | Verdicts |
|---|---|
| 11-21 14:37 to 15:14 | 0 to 29 |
| 11-21 21:58 to 11-22 04:16 (probe at 18:58 said reset in 39 minutes) | 29 to 106 |
| 11-22 06:13 to 06:43 (probe at 04:16 said reset in 1 hour, 21 minutes) | 106 to 141 |
| 11-23 23:06 to 23:40 | 141 to 181 |

From 11-22 06:43 the probe reported a multi-day limit ("reset in 6 days, 7 hours", counting down to "5 days, 1 hour"
at 11-23 13:31). The probe at 11-23 23:06 succeeded anyway; why the limit lifted early is not known.

## Usage

ACP returned no token usage: `usage` is `null` in every verdict. The quota windows covered 29, 77, 35 and 40 verifications at
`thinking_level` high, with up to 8 at once.

## Deviations from the checklist

1. **The backend was not reviewed before the run.** It was written and committed (`093b974`) in this session
   immediately before the pilot, and is reviewed in the same pull request as the run.
2. **No `nix develop`.** Run with the system Python and git. `codex` is not involved.
3. **Source repositories were linked, not prepared.** `repos/` is a symlink to the clones used for experiment 005,
   which hold the same PR heads; `prepare.sh` was not run.
4. **The run was first partial** (quota): commit `b99e961` compared 24 of 181 issues, 3 to 6 per tool. The completed
   run supersedes it.
5. In the first pass (to 15:14 on 11-21), Gemini asked to run shell commands (`execute`, 42 times) and other tools (`other`, 22); all were rejected.
   Search requests (8) were allowed. File reads needed no permission. No checkout was edited.
6. **Rounds were resumed by an automated runner**, not by hand. Before each round it probed the quota with a
   one-line prompt (`Reply with the word ok.`) through `verify.ask_gemini` at `thinking_level` low, slept until the
   reported reset (or one hour) while the limit held, then ran the unchanged step 9 command.
