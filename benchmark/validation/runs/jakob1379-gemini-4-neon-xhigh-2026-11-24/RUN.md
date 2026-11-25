# Gemini 4 Neon xhigh verification run, 2026-11-24 to 2026-11-25

Run status: **complete.** All 181 sampled issues across the 48 ledgers have a verdict, and `run.py external` compares all
181. This is the re-run of `validation/runs/jakob1379-gemini-4-neon-2026-11-21/`, which was patch-blind: there Gemini
never saw `change.patch`. Here the patch is sent with the prompt, and a reply saying the files could not be read fails
the call instead of becoming a verdict.

The fix held: no verdict reason says the files could not be read, and both `unverifiable` verdicts are about facts
outside the repository (whether commons-text 1.15.0 exists on Maven Central, `keycloak__keycloak__37429/4`; whether a
GitHub label exists, `keycloak__keycloak__37634/4`). No reason cites `change.patch` line numbers; that is expected,
because the patch arrives as embedded content without a file to cite, and reasons cite source files instead.

## Pins

| Pin | Value |
|---|---|
| Repository commit | `4a0e722` (`fix(verify): resolve the patch path before making it a file URI`, on top of `f9959bb`) |
| Backend | `verify.py --cli gemini`: Antigravity ACP server (`agy_acp_server`), as in the 11-21 run |
| Account | Google AI Pro, cached Google login, as in the 11-21 run |
| Model | `gemini-4-neon-xhigh`, set with `session/set_model` (`--model gemini-4-neon --effort xhigh`) |
| Patch delivery | `change.patch` sent as an embedded ACP `resource` (`text/x-diff`) in the prompt |
| Parallelism | `verify.py` defaults: `--pr-jobs 2`, `--jobs 4` |
| Timeout | `verify.py` default: 20 minutes per finding |
| Sample checksum | `48254a6eccedc13b103fd26c143b15c7e75144381777f625ef8c68a28e00aa20`, as in the README (rechecked after the run) |

## Commands

`BENCH_WORK` was set to a directory outside the repository (a session scratch directory). Times are from
`times.txt` and `rounds.log`.

1. Pilot, 11-24 12:43 to 12:45:
   `python3 verify.py --cli gemini --model gemini-4-neon --effort xhigh --ledgers validation/sample --out "$RUN" --only calcom__cal.com__8330`.
   Result: `ok, 4 of 4 confirmed`.
2. Full run and every resumed round: the same command without `--only`, started by an automated runner (below)
   whenever a quota probe succeeded. Output in `verify.log`; rounds and probes in `rounds.log`.
3. Frozen in the commit `chore(validation): complete gemini-4-neon xhigh verification run`, then
   `python3 experiments/005-pooled-truth/run.py external "$RUN" | tee "$RUN/external.txt"`.

## Failures

Every failed call raised `ValueError: substring not found`: the reply held no JSON object. None raised
`verifier could not read the files`. Each one is kept as `<n>.failed.txt` (102 files; a later verdict sits beside it
as `<n>.json`, and every `.failed.txt` has one).

| Time (start) | verify.py call | Open failures at start | Outcome |
|---|---|---|---|
| 11-24 12:43 | pilot (`--only calcom__cal.com__8330`) | 0 | 4 verdicts |
| 11-24 12:46 | full run | 0 | ended 13:22: 79 verdicts; 102 failed; next probe: limit reached, reset in 4 hours, 20 minutes |
| 11-24 18:48 | resumed round | 102 | stopped after 40 PR lines without a summary; 147 verdicts at the next round |
| 11-24 21:48 | resumed round | 34 | ended 22:01: 173 verdicts; 8 failed; next probe: limit reached, reset in 1 hour, 46 minutes |
| 11-25 00:48 | resumed round | 8 | ended 00:51: 181 verdicts, no failures |

`rounds.log` numbers each of the resumed rounds `round 1`, so each was started by a fresh runner process: the runner
did not survive its sleeps, and the scheduled checks restarted it. The 18:48 round stopped without a summary and left
no record of its own failures; it ran from 79 to 147 verdicts.

Totals: 110 logged failed calls (102 + 8), plus any in the stopped round. 3 re-runs of the full-run command after
the first, 5 `verify.py` calls in all. Both failure bursts ended with the quota probe reporting the usage limit, and the
last round had none, so the failures are quota, not reply-format, failures.

## Quota windows used

| Window | Verdicts |
|---|---|
| 11-24 12:43 to 13:22 | 0 to 79 |
| 11-24 18:48 to 22:01 (probe at 13:22 said reset in 4 hours, 20 minutes) | 79 to 173 |
| 11-25 00:48 to 00:51 (probe at 22:02 said reset in 1 hour, 46 minutes) | 173 to 181 |

## Usage

ACP returned no token usage: `usage` is `null` in every verdict. Gemini asked to run shell commands (`execute`, 203
times), fetch URLs (`fetch`, 8) and other tools (`other`, 6); all were rejected. Search requests (22) were allowed.
File reads needed no permission. No checkout was edited.

## Deviations from the checklist

1. **The backend was fixed and re-run in the same session.** `f9959bb` and `4a0e722` were written and committed
   immediately before the run, after the 11-21 run turned out patch-blind, and are reviewed in the same pull request
   as the run. `4a0e722` was committed at 12:46:35, between the pilot (12:43 to 12:45) and the full run (12:46:50);
   the pilot ran from the working tree with that change in place.
2. **Patch delivery was proven before the run**: given a real patch as embedded content, Gemini quoted its lines 1 and
   3 verbatim without any tool call.
3. **No `nix develop`.** Run with the system Python and git. `codex` is not involved.
4. **Source repositories were linked, not prepared.** `repos/` is a symlink to the clones used for experiment 005,
   which hold the same PR heads; `prepare.sh` was not run.
5. **Rounds were resumed by an automated runner**, not by hand. Before each round it probed the quota with a
   one-line prompt (`Reply with the word ok.`) through `verify.ask_gemini` at `gemini-4-neon-low`, slept until the
   reported reset (or one hour) while the limit held, then ran the unchanged full-run command.

## Result

| Comparison, same 181 issues | Agreement | Kappa |
|---|---|---|
| Gemini against Fable 5.2 | 93.4% | 0.66 |
| Gemini against Opus 5.5 | 91.7% | 0.57 |
| Fable 5.2 against Opus 5.5 (reference) | 97.2% | 0.86 |

Gemini confirms 162 of 181, Fable 160, Opus 161. Gemini and Fable disagree on 12 issues: Gemini confirms 7 that
Fable refutes and refutes 5 that Fable confirms. Most turn on reachability. Gemini confirms defects that Fable refutes
as unreachable in practice (an unsynchronised `||=` that boot already initialises, a String locale no caller passes, a
nil request the decorator rejects first, which Gemini itself notes), and refutes two that Fable confirms because a
guard elsewhere makes the harm unreachable (a permission class in front of the gate, cascade deletes behind the early
return). Others turn on whether the harm is a regression or matters at all (a format check the old validator never
had, a mock signature TypeScript accepts). The rest are
judgement calls on trivial claims, including one miss: Gemini says Grafana has no capitalised-log-message convention,
while `contribute/backend/instrumentation.md` asks for one.

| Tool (n=34 each) | Gemini | Fable | Opus |
|---|---|---|---|
| converge-review | 91.2% | 97.1% | 94.1% |
| CodeRabbit | 82.4% | 82.4% | 82.4% |
| Claude Code | 88.2% | 91.2% | 94.1% |
| Cubic v2 | 91.2% | 82.4% | 79.4% |
| Qodo Extended v2 | 94.1% | 91.2% | 94.1% |
| Augment | 97.1% | 94.1% | 97.1% |

The patch-blind 11-21 run agreed with Fable on 88.4% (kappa 0.47) and with Opus on 86.7% (kappa 0.38).
