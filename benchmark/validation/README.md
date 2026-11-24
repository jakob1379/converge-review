# Outside verification with Codex: checklist

This is the procedure for an outside team to re-verify a fixed sample of experiment 005 with an OpenAI model
through Codex. Follow it in order. Background: [`../README.md`](../README.md), section "Experiment 005 in full".

## What this run checks

Experiment 005 pooled every tool's review comments on 50 pull requests into 1,109 issues, each stated as a neutral
claim with no tool name. Two Claude models then checked each claim against the source code. Claude also wrote
some of the reviews being checked. Your run checks a fixed sample of 181 of those claims with a non-Claude model,
using the same prompt, so the two sets of verdicts can be compared.

The question is whether an OpenAI verifier agrees with the Claude verifiers, overall and per tool. No pass or fail
threshold was pre-registered for this run. Report the result as it comes out.

## Rules

1. **Stay blind until you submit.** Do not open `verify/`, `pool/`, `results/` or
   `experiments/005-pooled-truth/results.json`, and do not open `experiments/005-pooled-truth/labels.key.json`.
   They hold Claude's verdicts and which tool wrote what. `docs/` and the top-level README report aggregate
   results; do not paste anything from them into a prompt.
2. **Do not tune.** Do not edit `verify.py`, its prompt, or the sample. Do not run `run.py sample`; the sample is
   already generated and must not change.
3. **One run.** Every verdict that came back valid stands. Never delete or overwrite a verdict file to try again.
   `verify.py` has no `--force` flag; do not imitate one by deleting files.
4. **Report everything.** Every failure, every re-run, every deviation from this checklist, and the result whether
   it agrees with Claude or not.

## The sample

| File | Content |
|---|---|
| `sample/<pr id>.json` | One ledger per PR, 48 PRs, 181 findings in all. Each finding is one issue. |
| `index.json` | The strata: `{"<tool>": [["<pr id>", "<issue id>"], ...]}`, 34 entries for each of `converge-review`, `coderabbit`, `claude-code`, `cubic-v2`, `qodo-extended-v2` and `augment`. |

The sample was drawn with seed 0: 34 issues at random per tool, from the issues that tool raised. One issue can be
drawn for several tools, so the union is 181, not 204. Two PRs have no sampled issue:
`keycloak__keycloak__36882` and `ai-code-review-evaluation__keycloak-greptile__1`.

A finding in `sample/<pr id>.json`:

```json
{
 "issue": "i1",
 "path": "app/models/optimized_image.rb",
 "line": null,
 "severity": "Minor",
 "claim": "`self.downsize` is defined twice in OptimizedImage. ...",
 "evidence": null,
 "seats": [],
 "verdict": "fix",
 "list": "main"
}
```

`issue` is the issue's id in the pool. `severity`, `verdict`, `seats` and `list` are placeholders that make
`verify.py` treat the finding as one to check. The verifier is given the patch path, the location (`path`), the
`claim`, and the evidence (`none`). Nothing else.

## Pins

Agree these before the pilot and write them into `RUN.md` (step 12). Change none of them during the run.

| Pin | Value |
|---|---|
| Repository commit | The commit named in the hand-off message. Record `git rev-parse HEAD`. |
| Codex CLI | 0.169.0, as provided by `nix develop`. Record `codex --version`. |
| Model | The exact model id you pass to `--model`. Agree it with us first. |
| Reasoning effort | `high` |
| Parallelism | `verify.py` defaults: `--pr-jobs 2`, `--jobs 4` (up to 8 Codex sessions at once). Lower them only if rate-limited, and record it. |
| Timeout | `verify.py` default: 20 minutes per finding. |

## Checklist

### 1. Clone and check out the agreed commit

```bash
git clone https://github.com/jakob1379/converge-review.git
cd converge-review
git checkout <agreed commit>
git rev-parse HEAD
```

### 2. Enter the environment

```bash
nix develop
cd benchmark
codex --version          # expect 0.169.0
python3 --version
git --version
```

Without Nix, install: git, Python 3.11 or later, uv, and Codex CLI 0.169.0. The `claude` CLI is not needed for
this run.

### 3. Authenticate Codex

Log in the way your organisation uses Codex (for example `codex login`). `verify.py` passes no credentials. It
runs Codex with `--ignore-user-config`, so your `config.toml` is not read. If you keep personal instructions in
`~/.codex/AGENTS.md`, move them aside for the run or record that they were present.

### 4. Prepare

```bash
./prepare.sh
```

What it does:

- Clones `withmartian/code-review-benchmark` into `vendor/code-review-benchmark`, checks out
  `e616e849755441da38f18bf3adba2c9583b03803`, and runs `uv sync` there. `run.py external` imports a module from
  this clone.
- `bench.py manifest`: `prs.json` is committed and lists all 50 PRs, so this makes no GitHub API calls. No
  `GH_TOKEN` is needed. If it ever has to resolve a PR, it reads `GH_TOKEN` or `GITHUB_TOKEN`; unauthenticated,
  GitHub allows 60 API calls per hour.
- `bench.py repos`: makes bare, blobless clones of the 7 source repositories under `repos/` and fetches each PR
  head. It stops with `pull head moved` if a PR head no longer matches `prs.json`; report that if it happens.
- `bench.py run --dry-run --limit 1`: prints one review command. It calls no model.

Network: github.com (git over HTTPS) and PyPI. Disk: about 2 GB for `repos/` and about 0.4 GB for `vendor/`. The
clones are blobless, so the verification run also fetches file contents from github.com when it checks out each
PR.

Expected last lines of `bench.py`'s output: `50 PRs in prs.json`, then `all PR heads and merge-bases resolved`,
then the dry run.

### 5. Confirm the sample is unchanged

```bash
git status --short -- prs.json validation
(cd validation && find sample index.json -type f | LC_ALL=C sort | xargs sha256sum | sha256sum)
```

`git status` prints nothing. The checksum is
`48254a6eccedc13b103fd26c143b15c7e75144381777f625ef8c68a28e00aa20`.

### 6. Set the work directory and the run directory

```bash
export BENCH_WORK="$HOME/converge-review-work"
MODEL="<agreed model id>"
RUN="validation/runs/<org>-$MODEL-$(date +%F)"
mkdir -p "$RUN"
```

`BENCH_WORK` must be outside the repository. `verify.py` checks out each PR there and writes the patch next to
it, and the verifier works from that checkout. Kept outside the repository, it cannot reach Claude's verdicts in
`verify/` or the source map in `pool/` by browsing parent directories. The read-only sandbox does not stop
reading elsewhere on disk, so this reduces the chance of a leak; it does not enforce blindness. For stronger
isolation, run `verify.py` from a second clone in which `verify/`, `pool/` and `results/` are deleted, then copy
`$RUN` into the main clone for step 11.

Use the date the run starts, and keep `$RUN` the same for the pilot, the full run and every re-run.

### 7. Pilot on one PR

```bash
python3 verify.py --cli codex --model "$MODEL" --effort high \
  --ledgers validation/sample --out "$RUN" \
  --only calcom__cal.com__8330 2>&1 | tee -a "$RUN/verify.log"
```

This PR has 4 sampled issues. Expected output: one line, `calcom__cal.com__8330: ok, <k> of 4 confirmed`.

Sum the Codex usage the pilot recorded:

```bash
python3 - "$RUN" <<'EOF'
import collections, json, sys
from pathlib import Path
total, n = collections.Counter(), 0
for f in Path(sys.argv[1]).glob("*/*.json"):
    if f.parent.name == "ledgers":
        continue
    u = json.loads(f.read_text()).get("usage") or {}
    u = u.get("usage", u)
    total.update({k: v for k, v in u.items() if isinstance(v, (int, float))})
    n += 1
print(n, "verdicts", dict(total))
EOF
```

Send us: the token totals, the wall time, any `*.failed.txt`, and how much of your Codex usage limit the pilot
used, if your plan shows it. The full run is about 181 / 4 = 45 times the pilot.

### 8. Agree the budget

We agree a usage cap for the full run before it starts. Cost reference: the Claude primary verifier
(`claude-fable-5-2`) cost 367.91 USD at list price for all 1,109 issues, about 0.33 USD per issue. On these 181
issues it cost 56.23 USD, and the second verifier (`claude-opus-5-5`) 21.64 USD. Codex usage is unknown until the
pilot.

The pilot's verdicts are kept and count as part of the run. If the pins change after the pilot, start a new run
directory and report the discarded one.

### 9. Full run

Same command, without `--only`:

```bash
python3 verify.py --cli codex --model "$MODEL" --effort high \
  --ledgers validation/sample --out "$RUN" 2>&1 | tee -a "$RUN/verify.log"
```

It skips findings that already have a verdict, so the pilot PR is not run again. Expected output: one line per PR
in `prs.json`, 50 in all:

- `<pr id>: ok, <k> of <n> confirmed` for each of the 48 sampled PRs;
- `<pr id>: no ledger, skipped` for the 2 PRs without sampled issues;
- `<pr id>: <m> of <n> findings have no verdict; run again to resume` if some calls failed;
- `<pr id>: FAILED, checkout: ...` if the source repositories are not prepared;
- `<pr id>: FAILED, a verifier edited the checkout` should not happen under the read-only sandbox. If it does,
  stop and report it. Do not re-run that PR: a re-run would accept its verdicts without the check.

If usage reaches the agreed cap, stop. Submit what exists; step 11 handles a partial run.

### 10. Re-run failures only

A failed call leaves `$RUN/<pr id>/<n>.failed.txt` with the error, and no `<n>.json`. Before each re-run, record
the failures:

```bash
find "$RUN" -name '*.failed.txt' | sort | while read -r f; do echo "$f: $(cat "$f")"; done
```

Then run the step 9 command again, unchanged. It re-runs only findings without a verdict. A successful retry
leaves the old `.failed.txt` in place; do not delete it, it is the record of the failure. Repeat until every
sampled PR prints `ok`, or until the cap. Write each round (failures, re-run, outcome) into `RUN.md`.

Check completeness:

```bash
ls "$RUN/ledgers" | wc -l                                  # 48
find "$RUN" -mindepth 2 -name '*.json' -not -path '*/ledgers/*' | wc -l   # 181
```

### 11. Freeze, then compare

Commit the run on your branch before you look at any comparison:

```bash
git checkout -b validation/<org>-$MODEL
git add "$RUN"
git commit -m "chore(validation): add $MODEL verification run"
```

Then:

```bash
python3 experiments/005-pooled-truth/run.py external "$RUN" | tee "$RUN/external.txt"
```

It prints how many of the 181 sampled issues have an outside verdict, the agreement and Cohen's kappa with each
Claude verifier (`fable` is the primary, `opus` the second), and, per tool, the share of its sampled issues that
each verifier confirmed. It writes `$RUN/comparison.json`. After this point, do not re-run or change any verdict.

### 12. Write `RUN.md` and submit

Add `$RUN/RUN.md` with:

- the pins table above, filled in, with the outputs of `git rev-parse HEAD` and `codex --version`;
- the exact commands run, in order, with start and end times;
- every failure and every re-run (step 10);
- usage totals for the pilot and for the whole run (the step 7 snippet works on the full run too);
- any deviation from this checklist.

Commit `RUN.md`, `external.txt` and `comparison.json`, and open a pull request against
`jakob1379/converge-review`. The raw run directory is required. An HTML report is welcome as
`$RUN/report.html`; it does not replace the JSON.

## Expected output

```
validation/runs/<org>-<model>-<YYYY-MM-DD>/
  <pr id>/<n>.json          one verdict per sampled finding, 181 in all
  <pr id>/<n>.failed.txt    only for calls that failed; kept after a successful retry
  ledgers/<pr id>.json      48 files: the sample ledger with a "verifier" entry per finding
  verify.log                stdout and stderr of every verify.py run
  external.txt              stdout of run.py external
  comparison.json           written by run.py external
  RUN.md                    pins, commands, failures, re-runs, usage
  report.html               optional
```

`<n>` is the finding's position (from 0) in `validation/sample/<pr id>.json`, not the issue id.

**Verdict file** `<pr id>/<n>.json`:

| Field | Type | Meaning |
|---|---|---|
| `verdict` | `"confirmed"`, `"refuted"` or `"unverifiable"` | Whether the claim is true of the code as the patch leaves it. `unverifiable`: the source here cannot settle it. |
| `reason` | string | One or two sentences citing file:line. |
| `introduced_by_patch` | boolean | Whether the patch introduced or exposed the problem. |
| `impact` | `"blocks-merge"`, `"worth-fixing"` or `"trivial"` | Severity, assuming the claim is true. |
| `cost_usd` | number | Always `0` for Codex. |
| `usage` | object or null | The last JSONL event from `codex exec --json` that contains `usage`, as Codex emitted it. |
| `cli` | `"codex"` | |
| `model` | string | The `--model` value. |
| `effort` | string | The `--effort` value. |

Any other keys the model put in its JSON reply are kept as they came. `verify.py` rejects a reply whose
`verdict`, `impact` or `introduced_by_patch` is invalid and records it as a failure.

**Ledger file** `ledgers/<pr id>.json`: the sample ledger, with the verdict copied into each finding as
`"verifier": {...}`. Findings not confirmed have `"list": "appendix"`. `run.py external` reads only these files and
matches them to the sample by `issue`.

**`comparison.json`**:

```json
{
 "agreement": {
  "fable": {"share": 0.0, "kappa": 0.0},
  "opus": {"share": 0.0, "kappa": 0.0}
 },
 "confirmed_share": {
  "<tool>": {"n": 34, "outside": 0.0, "fable": 0.0, "opus": 0.0}
 }
}
```

Shares are fractions from 0 to 1. Agreement is on confirmed versus not confirmed; `refuted` and `unverifiable`
both count as not confirmed. `n` is the number of that tool's sampled issues with an outside verdict.

`run.py external` was checked by feeding it the Opus verifier's own verdicts as the outside run: it reported
100.0% agreement with Opus and 97.2% with Fable, as expected.

## How this run differs from the Claude runs

Same prompt text, same sample, same checkouts and patches. Differences, to be stated with any comparison:

1. Codex has no system-prompt flag, so `verify.py` prepends the system prompt to the task text. The Claude runs
   passed it as a system prompt.
2. The Claude runs had the Read, Grep and Glob tools only. Codex uses its own tools inside `--sandbox read-only`.
3. Codex runs with `--ephemeral --ignore-user-config --skip-git-repo-check --json`. Claude runs used
   `--setting-sources ""`, `--strict-mcp-config` and `--no-session-persistence`.
4. Cost is recorded as token usage, not USD.

The full Codex command, as `verify.py` builds it:

```
codex exec --model <model> -c model_reasoning_effort="high" --sandbox read-only --ephemeral \
  --ignore-user-config --skip-git-repo-check --cd <BENCH_WORK>/<pr id> --json \
  --output-last-message <temporary file> -
```

## Gemini

A Gemini pass is its own run directory, for example `validation/runs/<org>-<gemini model>-<YYYY-MM-DD>/`.
`verify.py --cli gemini` drives Antigravity's ACP server (`agy_acp_server`, JSON-RPC over stdio): one fresh server
and session per finding, signed in with the cached Google login (`authenticate` with `oauth-personal`), and the
model set with `session/set_model` to `<--model>-<--effort>`, for example `gemini-4-neon-xhigh`. Run it exactly as
steps 7 to 11, with `--cli gemini --model gemini-4-neon --effort xhigh`.

Differences from the Claude runs, besides those listed for Codex:

1. ACP has no system-prompt field, so the system prompt is prepended to the task, as for Codex.
2. The session runs in Antigravity's default permission mode. Every permission request for a tool whose kind is
   not `read`, `search` or `think` is rejected; each request is recorded in the verdict as `permission_requests`.
   Tools that Antigravity runs without asking are not restricted by `verify.py`; the dirty-checkout check after
   each PR is the guard against edits.
3. `usage` is the `usage` (or `_meta`) of the `session/prompt` result, as Antigravity returned it.
4. Antigravity cannot read files outside the session's working directory, which is the checkout, so the patch is
   also sent as an embedded `resource` block in the prompt. The path in the task text is the resource's URI.
5. A reply that is `unverifiable` because the verifier could not read the files (`NO_ACCESS` in `verify.py`) is a
   failed call, kept as `<n>.failed.txt` and re-run, not a verdict. This applies to every backend.
