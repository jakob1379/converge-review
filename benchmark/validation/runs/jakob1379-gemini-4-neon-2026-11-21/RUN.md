# Gemini 4 Neon verification run, 2026-11-21: partial

Status: **incomplete.** 29 of the 181 sampled issues have a verdict; 24 of them are on PRs whose every sampled
issue is done, which is what `run.py external` compares. The Google AI Pro quota ran out about 30 minutes into the
full run. Resume with the step 9 command after the quota resets; it re-runs only the issues without a verdict.

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
3. Frozen in commit `0ec2f6c`, then `python3 experiments/005-pooled-truth/run.py external "$RUN"`.

## Failures

152 calls failed with `ValueError: substring not found`: the reply held no JSON object. One manual prompt after the
run (`Reply with the word ok.`) got: "Usage Limit Reached. You have reached your current quota for this period. Your
limit will reset in 4 hours, 23 minutes." Every failure is kept as `<n>.failed.txt`. No re-run has been made.

## Usage

ACP returned no token usage: `usage` is `null` in every verdict. The quota covered about 29 verifications at
`thinking_level` high, at 7 to 8 minutes each with up to 8 at once.

## Deviations from the checklist

1. **The backend was not reviewed before the run.** It was written and committed (`093b974`) in this session
   immediately before the pilot, and is reviewed in the same pull request as the run.
2. **No `nix develop`.** Run with the system Python and git. `codex` is not involved.
3. **Source repositories were linked, not prepared.** `repos/` is a symlink to the clones used for experiment 005,
   which hold the same PR heads; `prepare.sh` was not run.
4. **The run is partial** (quota). The comparison covers 24 of 181 issues, 3 to 6 per tool.
5. Gemini asked to run shell commands (`execute`, 42 times) and other tools (`other`, 22); all were rejected.
   Search requests (8) were allowed. File reads needed no permission. No checkout was edited.
