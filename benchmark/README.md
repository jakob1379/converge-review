# converge-review benchmark

This directory scores the `converge-review` skill on Martian's offline Code Review Bench and compares it with the
stored results of the tools already on that benchmark. It holds the harness, every raw output, and every
experiment log. This README explains how the numbers were made and how to reproduce them.

Sources for everything below: `docs/methodology.md`, `docs/findings.md`, `docs/experiments/001` to `005`,
`docs/issues/01` to `11`, and the code in this directory. Where a number appears, it comes from one of those
files. Where two disagree, the text says which one is used.

- Outside verification of experiment 005 (Codex): [`validation/README.md`](validation/README.md).
- Glossary of terms (seat, ledger, finding, candidate, profile, k): [`GLOSSARY.md`](GLOSSARY.md).
- The old runbook, kept as written: [`RUNBOOK.md`](RUNBOOK.md).

## Status

| Question | Answer | Status |
|---|---|---|
| Score on the benchmark's own F1 (Core, Opus judge) | 28.5 for the original run. 37.9 to 41.0 for later variants. | Final for one review run |
| Rank on that F1 | 21 of 23 (original run). 20 of 23 with the three-seat filter. | Final for one review run |
| Win over a named competitor on F1 | None shown | Final |
| Recall of golden comments | 82.3 (Opus judge), 16 to 36 points above each named competitor | Exploratory, chosen after the results |
| Share of comments that are true, judged against source | 96.3%, against 84.3% to 94.2% for the competitors | Provisional. Human check not done; outside verifier pending |
| True issues found | 740 of 990 verified true issues, against 138 to 247 | Provisional, same reasons |

All results are one review run of 50 PRs. Run-to-run variance is unmeasured (issue 01).

## Pins

| What | Value | Source |
|---|---|---|
| Benchmark | `withmartian/code-review-benchmark@e616e849755441da38f18bf3adba2c9583b03803` (committed 2026-08-30) | `prepare.sh` |
| Competitor results, as committed upstream (sha256 prefix) | Opus judge `56e38e37ce570988`, Sonnet judge `175de256f2a1717d` | `docs/methodology.md` |
| Skill text the 50 reviews ran | `skill/SKILL.baseline.md`, sha256 prefix `4862d335574601dd` | `docs/methodology.md`, checked |
| Review model | `claude-opus-5-5`, effort high, Claude Code 2.1.322, gate skipped | `docs/methodology.md` |
| Judges | `anthropic/claude-opus-4-5-20251101` (primary), `anthropic/claude-sonnet-4-5-20250929` | `score.sh`, `evalstats.py` |
| Verifiers, experiment 005 | `claude-fable-5-2` (primary), `claude-opus-5-5`, both effort high | `docs/experiments/005-pooled-truth.md` |
| Tool versions in `nix develop` | codex 0.169.0, claude-code 2.1.326 (from `flake.lock`) | `nix eval` on the flake |

The dev shell's claude-code (2.1.326) is newer than the one the reviews ran on (2.1.322).

## The benchmark

Code Review Bench (offline) has 50 pull requests from 5 open-source projects, 10 each: discourse, sentry,
keycloak, grafana and cal.com. Some PRs live in `ai-code-review-evaluation/*-greptile` and `*-graphite` forks. In
this harness they count with their project. The manifest `prs.json` lists 7 GitHub repositories for that reason.

Each PR has golden comments: issues the benchmark's authors labelled, with a severity and a category. There are
173 in total. The upstream repository also stores the reviews of about 45 tools and their judged results under
three judges (Opus 4.5, Sonnet 4.5, GPT-5.2).

The upstream code is not vendored. `prepare.sh` clones it into `vendor/code-review-benchmark` and checks out the
pin. Do not commit `vendor/`; `.gitignore` excludes it.

## How the reviews ran

`bench.py run` reviews each PR once:

1. `bench.py repos` has made a bare, blobless clone of each source repository under `repos/` and fetched each PR
   head into `refs/bench/pr-<n>`. It checks that the head still equals `head_sha` in `prs.json` and records the
   merge-base.
2. For each PR, `git worktree add --detach work/<pr id> <head_sha>`. Then `git diff --no-ext-diff <merge_base>
   <head_sha>` runs once, which fetches the base blobs into the blobless clone before the review starts.
3. `claude -p <prompt> --output-format json --add-dir out --add-dir work/<pr id>.scratch --permission-mode auto`
   runs in the worktree, with `GIT_CONFIG_GLOBAL=/dev/null` and a 60-minute timeout. Without the empty git
   config, a global `diff.external` (difftastic) turned the patch into truncated side-by-side text.
4. The prompt starts with `/converge-review` and adds benchmark-mode overrides: base is the merge-base, no spec,
   scratch files outside the repository, the gate rule, run steps 1 to 4 and the Rejections rule, then stop. No
   fixes, no rounds 2+, no edits. Write the merged ledger to `out/<pr id>.json` in a fixed JSON shape, rejected
   findings included.
5. The run fails the PR if the worktree is dirty afterwards, if no ledger was written, or if the ledger fails the
   schema check (severity `Critical|Important|Minor`, verdict `fix|defer|reject`, non-empty claim).

The full prompt is `PROMPT` in `bench.py`.

**Skill steps 1 to 4 only.** Step 1 pins the base and writes the patch. Step 2 is the gate. Step 3 dispatches the
four seats in parallel: `open-code-review`, `superpowers`, `ponytail` and `mattpocock`. Step 4 merges: dedupes,
sets severity, and gives each finding a verdict. Steps 5 and 6 (red test, fix, scoped re-review) only check the
skill's own fixes, so they do not change which issues it reports. They are not measured.

**Gate skipped.** `--gate skip` is the default. The competitors do not run tests either, and running the gate
means installing and executing five large untrusted codebases. `--gate run` exists and was not used.

**What counts as the review.** Findings with verdict `fix` or `defer`, at every severity. `bench.py ingest` turns
each into one review comment with body `[Severity] claim`, a blank line, then the evidence. `reject` is dropped.
The original run produced 802 findings, rejected 91, and reported 711: 14.2 per PR.

**Cost.** 183.81 USD for 50 PRs at list price, from `total_cost_usd` in `out/*.log.json`. Mean 3.68 per PR,
median 3.45, range 2.07 to 9.91. Estimated split from token use: `open-code-review` 0.79, `superpowers` 0.87,
`ponytail` 0.50, `mattpocock` 0.71, orchestrator 0.79 per PR. Local judging of the baseline cost about 49 USD.

**Seat reports.** `cache_seats.py` copied each seat's final report out of the Claude Code transcripts into
`cache/seat-reports/<pr>/<seat>.md`. Experiment 003 replays the merge step on these, so it needs no new reviews.

## How the judge works

Scoring uses the benchmark's own pipeline in `vendor/code-review-benchmark/offline/code_review_benchmark/`. Our
reviews are written into the benchmark's `results/benchmark_data.json` under a tool name (`bench.py ingest`), then
three steps run for that tool only, once per judge model (`score.sh`):

| Step | Module | What it does at the pinned commit |
|---|---|---|
| 2 | `step2_extract_comments` | Joins all comment bodies of one review and asks the judge model to list the distinct issues. Each issue is a **candidate**. Path and line are not used. |
| 2.5 | `step2_5_dedup_candidates` | Asks the judge model to group candidates that state the same issue. Writes `dedup_groups.json`. |
| 3 | `step3_judge_comments` | Asks the judge model, for every golden comment and every candidate, whether they describe the same underlying issue. Returns match and confidence. |

In step 3, a golden comment is a true positive if some candidate matches it; the highest-confidence match is
kept. A candidate counts as matched if it became a golden comment's best match when it was judged, or if it is in
a dedup group with such a candidate. Every other candidate is a false positive. Unmatched golden comments are
false negatives. Note that the upstream README says line-specific comments skip extraction; the code at the pin
sends every comment through extraction.

`score.sh` checks that extraction covered every PR before going on, then rebuilds the dashboard
(`analysis/benchmark_dashboard.py`).

**Local judge proxy.** By default `score.sh` starts `judge_proxy.py` on `127.0.0.1:8787` (`JUDGE_PORT`) and points
the benchmark at it with `MARTIAN_BASE_URL=http://127.0.0.1:8787/v1 MARTIAN_API_KEY=local`. The proxy is a small
OpenAI-compatible chat-completions endpoint. For each request it runs `claude -p --model <model> --system-prompt
<system messages>` with the user messages on stdin, no tools, no settings, no MCP, thinking disabled, a
throwaway working directory, and a 120-second timeout. At most 20 calls run at once (`JUDGE_SLOTS`). It serves
`anthropic/*` models only. `MARTIAN=1` skips the proxy and uses Martian's router with `MARTIAN_API_KEY` from
`vendor/code-review-benchmark/offline/.env`; this was not used.

**Judges.** Opus 4.5 is primary, Sonnet 4.5 secondary. The two differ by up to 7 F1 points on the same reviews.

**GPT-5.2 not run.** The upstream benchmark also judges with `openai/gpt-5.2`. The local proxy cannot serve it.

**Temperature deviation.** The benchmark calls each judge at temperature 0 through Martian's router. The
`claude` CLI does not expose temperature, so our judge calls run at the CLI default. The prompts are the
benchmark's. The size of this effect is unmeasured (issue 05). Related evidence on noise: the same findings
judged from two texts differed by 0.6 F1 under Opus and 0.8 under Sonnet (experiment 002), and two ways of
applying the same rule, filter and replay, differed by 1.8 F1 under Opus (experiment 003). The docs put pipeline
noise at 1 to 2 F1 points.

## Scores

Counts per PR and tool are true positives (tp), false positives (fp) and false negatives (fn), taken from the
judge's `evaluations.json`.

| Metric | Definition |
|---|---|
| Precision P | tp / (tp + fp) |
| Recall R | tp / (tp + fn) |
| F1 | 2PR / (P + R) |
| F2 | 5PR / (4P + R). Weights recall four times as much as precision. The benchmark ranks by F2 by default. |

**Profiles.** Golden comments have categories. A profile decides which ones count.

| Profile | Categories | Golden comments |
|---|---|---|
| Strict | bug, security, concurrency, data, api | 139 |
| Core (primary here) | Strict plus perf, test_gap, doc_defect | 158 |
| All | Core plus style, speculative | 173 |

tp and fn count only golden comments inside the profile. fp is the same in every profile. A match to a golden
comment outside the profile is neither tp nor fp.

**Pooled, not per-PR.** Every metric here is computed from tp, fp and fn summed over the PRs, as the benchmark's
dashboard does. Per-PR scores are never averaged. The PR is only the unit of resampling in the tests. A PR with no
result for a tool counts as missing all its golden comments (`evalstats.load_counts`).

`python3 evalstats.py` checks that our pooled baseline numbers equal the dashboard's before any analysis.

## Statistics and the acceptance rule

From `docs/methodology.md`, implemented in `evalstats.py`.

- **Unit and groups.** The PR is the unit; the repository is the group. PRs are never split at random.
- **Selection.** Leave-one-repo-out, 5 folds. In each fold the whole selection procedure runs on the other 4
  repos, and the chosen rule is applied to the held-out repo. The out-of-fold counts of all 5 folds are pooled.
  That pooled score is the headline. In-sample scores are labelled as such.
- **Paired bootstrap, stratified by repo.** 10,000 resamples, seed 0. Within each repo, resample its PRs with
  replacement, compute the pooled metric for A and B, record the difference. The 95% CI is the 2.5th to 97.5th
  percentile. One-sided p = (differences at or below 0, plus 1) / 10,001.
- **Paired approximate randomisation.** 10,000 resamples, seed 0. Swap A's and B's counts per PR with probability
  0.5. Two-sided p. Used as a cross-check; the more conservative of the two is reported.
- **Holm correction** across the five named competitors.
- **Named competitors**, fixed before experiment 001: `coderabbit`, `claude-code`, `cubic-v2`,
  `qodo-extended-v2`, `augment`. `cubic-dev` is excluded: it was judged against an older set of 137 golden
  comments and cannot be paired.
- **A win over a competitor** means a CI lower bound above 0 under Opus after Holm, and a positive difference
  under Sonnet. Anything else is "not shown", or "comparable" at most. Each competitor is one stored run, so its
  run-to-run variance is not in the CI.

**Acceptance rule.** A change is adopted only if all hold:

1. Out-of-fold F1 minus baseline F1 has a 95% CI lower bound above 0 under the Opus judge.
2. The same difference is above 0 under the Sonnet judge.
3. The difference is at least 0 in 4 or more of the 5 held-out repos (Opus).
4. Out-of-fold pooled Core recall stays at or above the pre-registered floor (60 in every experiment so far).
5. Cost per PR rises by no more than the pre-registered amount.

Each experiment also set a minimum effect for rule 1. Otherwise the change is rejected or inconclusive.
Inconclusive does not mean adopt, and the same change is not re-tested on the same data.

**Pre-registration.** Each experiment's hypothesis, change, data, metrics, tests, acceptance rule, budget and
stopping rule were committed in `docs/experiments/NNN-*.md` before the run. Results and every deviation were
appended to the same file afterwards. One run per experiment; no re-running to chase significance.

**What these 50 PRs can resolve.** The 95% interval for one variant against another is about plus or minus 3 F1
points under Opus and 4 under Sonnet. Smaller effects cannot be confirmed here.

## Baseline result (2026-11-14)

Core profile, pooled over 50 PRs, one review run, one judge run per judge.

| Tool | Opus P | Opus R | Opus F1 | Opus F2 | Sonnet P | Sonnet R | Sonnet F1 | Sonnet F2 |
|---|---|---|---|---|---|---|---|---|
| converge-review | 17.2 | 82.3 | 28.5 | 46.9 | 12.6 | 77.2 | 21.6 | 38.1 |
| CodeRabbit | 32.6 | 59.5 | 42.2 | 51.1 | 33.8 | 58.2 | 42.8 | 50.9 |
| Claude Code | 46.3 | 48.1 | 47.2 | 47.7 | 36.5 | 41.1 | 38.7 | 40.1 |
| Cubic v2 | 61.5 | 65.8 | 63.6 | 64.9 | 56.5 | 60.8 | 58.5 | 59.9 |
| Augment | 59.5 | 65.2 | 62.2 | 64.0 | 52.4 | 61.4 | 56.6 | 59.4 |
| Qodo Extended v2 | 67.1 | 64.6 | 65.8 | 65.1 | 56.2 | 57.0 | 56.6 | 56.8 |

It ranks 21 of 23 on F1 under Opus and 22 of 23 under Sonnet. It has the highest recall and the lowest precision
in the set. It finds every golden comment on 26 of 50 PRs and none on 1; the best competitor on that count
manages 22. Further in-sample analyses (severity, seat overlap, agreement) are in `docs/findings.md`.

## Experiments

Each paragraph gives the change, the result and the decision. Full pre-registrations and results:
`docs/experiments/`. Cost is at list price.

**001, agreement threshold. Adopted.** Report only findings raised by at least k seats, k in {1, 2, 3, 4},
applied as a filter on the existing ledgers (`bench.py ingest --min-seats k`). k was chosen per fold from a
simulation that traces judged candidates back to findings by word overlap, with a recall floor of 60 and a
minimum effect of +5. Every fold chose k=3. Core F1 rose from 28.5 to 40.2 under Opus (+11.7, 95% CI +8.3 to
+14.9) and from 21.6 to 32.9 under Sonnet. Recall fell from 82.3 to 66.5; findings per PR from 14.2 to 5.6. All
five repos improved. No win over a named competitor: comparable to CodeRabbit under Opus (-1.9, CI -7.2 to +3.5),
worse under Sonnet, and 22 to 26 points behind Cubic v2, Qodo Extended v2 and Augment. The simulation was
optimistic by 4.9 F1. Judge cost 25.07 USD.

**002, claim-only comments. Rejected.** Send each finding's claim without its evidence (`--claim-only`), k=3,
minimum effect +3. Out-of-fold F1 38.5 against 40.2 under Opus (-1.8, CI -3.5 to +0.1) and 32.9 against 32.9
under Sonnet. The hypothesis was wrong: extraction makes about as many candidates per finding either way (1.44
against 1.33 under Opus). The claims themselves are compound: median 31 words, and 181 of 282 hold more than one
issue. Judge cost 24.83 USD. The Sonnet run was interrupted and resumed; nothing was re-judged.

**003, merge replay. H1 holds; H2 inconclusive, not adopted.** `replay.py` re-runs step 4 on the cached seat
reports, one `claude -p` call per PR (`claude-opus-5-5`, effort high, no tools, skill text as system prompt).
Arm `replay` uses the adopted text `skill/SKILL.md`; arm `atomic` uses `skill/SKILL.atomic.md` (one issue per
finding, seats counted per issue). H1, fidelity: `replay` is within noise of the filter, -1.8 F1 under Opus (CI
-5.4 to +2.0), +0.5 under Sonnet. The orchestrator put all 300 findings with three or more seats on the main list
and none of the others. H2: `atomic` scored 41.0 against 38.5 under Opus (+2.5, CI -0.3 to +5.4) and 35.2 against
33.4 under Sonnet. Candidates per finding fell to 1.03, but the main list grew from 300 to 343, so the CI lower
bound stayed below 0 and the effect below the +3 minimum. `replay` became the baseline. Cost 81.69 USD (merge
34.38, judge 47.31). Five merge calls returned ledgers without the `list` field and were re-run once each.

**004, verify each main-list finding. Rejected.** `verify.py` ran one fresh read-only `claude -p` session per
main-list finding of `replay/adopted` (`claude-opus-5-5`, effort high, tools Read, Grep, Glob). Only `confirmed`
findings stay. The verifier confirmed 295 of 300, so filtering changes nothing: F1 37.9 against 38.5 under Opus;
every fold kept `replay`. The main lesson: of the 204 main-list findings that match no golden comment, the
verifier confirmed 201. Low precision on this benchmark mostly counts true findings outside the 3 or so labelled
issues per PR. Impact ratings separate golden from non-golden only weakly: a finding rated blocks-merge matched a
golden comment 62% of the time, worth-fixing 33%, trivial 16%. Cost 61.46 USD (verifier 36.70, 0.12 per finding;
judge 24.76). An exploratory comparison after the run, not pre-registered: the original run's recall is 16.5 to
34.2 points above each named competitor under Opus, every 95% interval above 0 under both judges.

**005, pooled truth. Both hypotheses hold under the verifiers. Provisional.** The golden set is replaced by a
pooled set of 1,109 issues, each verified blind against source by two Claude models. Method below. Under the
primary verifier, 96.3% of the original run's comments are true, against 84.3% to 94.2% for the five
competitors, and it finds 740 of 990 true issues, against 138 to 247. By the pre-registered rules it
"outperforms on both" `coderabbit`, `cubic-v2` and `augment`, and "finds more at the same accuracy" than
`claude-code` and `qodo-extended-v2`. Counting only issues rated above trivial, the recall lead holds (446 issues
against 115 to 158), but the share of its comments that qualify (58.4%) is 12 to 25 points below four of the five
competitors. Cost 511.56 USD: grouping 4.54, primary verifier 367.91 (0.33 per issue), second verifier 139.11
(0.13 per issue). Every claim waits on the human check (issue 03) and on an outside verifier (issue 10).

Variants judged on these 50 PRs so far: 6 (baseline, k=3, k=3 claim-only, replay, atomic, verified). Simulated:
about 45.

## Experiment 005 in full: pooled truth

Why: experiment 004 showed the benchmark's precision counts true findings as errors when they fall outside the
golden set. Pooling is the usual answer when nobody can list every true answer: collect what every system found,
and judge the union.

**1. Pool** (`pool.py --out pool`). Per PR, take the Opus judge's extracted candidates for seven sources:
`converge-review` (original run, every finding), `converge-review-replay` (three-seat rule), `coderabbit`,
`claude-code`, `cubic-v2`, `qodo-extended-v2`, `augment`. Add the golden comments as an eighth source. 2,337
comments in all.

**2. Merge duplicates, blind.** The comments of one PR are shuffled (seeded by the PR id), stripped of their
source, and numbered `c1`, `c2`, and so on. One `claude -p` call per PR (`claude-opus-5-5`, effort high, no tools)
groups the comments that describe the same defect and writes one neutral claim per group: what is wrong and
where, in one or two sentences, no severity or advice. Every id must appear in exactly one group, or the call
fails. A group is an **issue**. Result: 1,109 issues. 651 were raised by one source only, 21 by all eight, 543
only by our two variants, and 19 only by the golden set.

Outputs: `pool/<pr>.json` holds the items with their source and the issues with their members.
`pool/ledgers/<pr>.json` holds only the neutral claims, in the ledger shape `verify.py` reads. Severity `Minor`,
verdict `fix` and list `main` are placeholders.

**3. Verify, blind** (`verify.py --ledgers pool/ledgers`). One fresh session per issue, working directory a
detached checkout of the PR head, plus the patch file (`git diff <merge_base> <head>`). The verifier sees the
neutral claim and the path. It never sees the source tool, the original wording, or other issues. It returns
JSON: `verdict` (`confirmed`, `refuted` or `unverifiable`), `reason`, `introduced_by_patch`, and `impact`
(`blocks-merge`, `worth-fixing` or `trivial`, assuming the claim is true). Claude runs use `--tools
Read,Grep,Glob`, `--setting-sources ""`, `--strict-mcp-config` and `--no-session-persistence`. A run fails if the
checkout is dirty afterwards. The prompt is `SYSTEM` and `TASK` in `verify.py`.

**4. Two verifiers.** Primary `claude-fable-5-2`, a different model from the reviewers. Second `claude-opus-5-5`,
the reviewers' own model. Both at effort high. The design asked for a verifier from another model family; none
was available at the time, and the user chose to proceed with Claude only. That is the reason for the outside
run in `validation/`.

| Verifier | Confirmed | Refuted | Unverifiable | Confirmed: blocks-merge / worth-fixing / trivial |
|---|---|---|---|---|
| `claude-fable-5-2` (primary) | 990 | 107 | 12 | 59 / 516 / 415 |
| `claude-opus-5-5` | 955 | 144 | 10 | 68 / 472 / 415 |

They agree on confirmed-or-not for 94.3% of issues, Cohen's kappa 0.74.

**5. Score** (`experiments/005-pooled-truth/run.py report`).

- A comment is **true** if its issue is `confirmed`. `unverifiable` counts as not true.
- **Truth precision** of a tool: its true comments over its comments, pooled over the PRs. The unit is the
  comment (the Opus judge's candidate).
- **Pooled recall** of a tool: the confirmed issues it has at least one comment in, over all confirmed issues in
  the pool from any source, golden comments included. The unit is the issue.
- Two scopes. **All true issues** is primary. **True and not trivial** (`worth-fixing` or `blocks-merge`) is
  secondary.
- Tests: the paired repo-stratified bootstrap above, on recall and on truth precision, against each of the five
  competitors, with Holm across the five.

**Decision rules, pre-registered.**

- H1, recall, holds against a competitor if the CI lower bound of the recall difference is above 0 and the
  Holm-adjusted one-sided p is below 0.025 under the primary verifier, and the difference is above 0 under the
  second verifier.
- H2, precision, holds if the CI lower bound of the precision difference is above -5 under the primary verifier.
  Precision is called higher only if that bound is above 0.
- "Outperforms on both": H1 holds and the precision bound is above 0. "Finds more at the same accuracy": H1 and
  H2 hold.
- Every claim is provisional until the human check passes: the user agrees with the primary verifier on at least
  80% of labelled issues, and no tool's share of verifier-confirmed issues that the user calls true is more than
  20 points below the highest tool's.

**Primary scope, primary verifier.** 990 true issues.

| Source | Comments | True | Issues found | Pooled recall | Issues found per PR |
|---|---|---|---|---|---|
| `converge-review` (original run) | 781 | 96.3% | 740 | 74.7% | 14.8 |
| `converge-review-replay` (three-seat rule) | 387 | 98.2% | 354 | 35.8% | 7.1 |
| `coderabbit` | 318 | 84.3% | 247 | 24.9% | 4.9 |
| `augment` | 178 | 92.1% | 161 | 16.3% | 3.2 |
| `claude-code` | 173 | 94.2% | 152 | 15.4% | 3.0 |
| `cubic-v2` | 175 | 86.3% | 142 | 14.3% | 2.8 |
| `qodo-extended-v2` | 152 | 92.1% | 138 | 13.9% | 2.8 |
| golden comments | 173 | 88.4% | 149 | 15.1% | 3.0 |

"Comments" here counts the Opus judge's candidates (781 for the original run). That differs from the 711
reported findings in the baseline section, because extraction splits some findings.

`converge-review` minus each competitor, primary verifier (second verifier in the last column):

| Competitor | Recall difference (95% CI) | Second verifier | Precision difference (95% CI) | Second verifier (95% CI) |
|---|---|---|---|---|
| coderabbit | +49.8 (+44.7 to +55.0) | +49.6 | +12.0 (+7.3 to +16.9) | +10.1 (+5.5 to +15.1) |
| claude-code | +59.4 (+55.4 to +63.1) | +59.5 | +2.1 (-1.7 to +6.3) | +0.4 (-3.3 to +4.6) |
| cubic-v2 | +60.4 (+55.6 to +64.8) | +61.0 | +10.0 (+4.7 to +16.0) | +11.2 (+5.8 to +17.2) |
| qodo-extended-v2 | +60.8 (+57.5 to +63.9) | +60.7 | +4.2 (-0.4 to +9.1) | +1.4 (-2.8 to +6.0) |
| augment | +58.5 (+54.5 to +62.2) | +58.8 | +4.2 (+0.6 to +8.2) | +4.1 (-0.1 to +8.8) |

All recall differences have Holm p below 0.001. For `augment` the precision lead does not hold under the second
verifier, so it is the weakest of the three "outperforms" claims.

**Secondary scope, true and not trivial.** 575 issues. The original run finds 446 (77.6%), against 115 to 158 for
the competitors. Its share of comments that are true and above trivial is 58.4%, against 83.6% (`qodo-extended-v2`),
77.0% (`augment`), 75.1% (`claude-code`), 70.9% (`cubic-v2`) and 55.0% (`coderabbit`). The three-seat variant is at
75.5%.

**What else 005 showed.**

- The three-seat rule is an importance filter, not a truth filter. Of the 378 issues it removes, the primary
  verifier confirmed 356 (94%).
- The golden comments cover 149 of the 990 true issues, and 116 of the 575 above trivial.
- The verifier confirmed 88% of the golden comments' issues (85% under the second verifier). So it does not
  confirm everything.
- Per-tool agreement between the two verifiers is 93% to 97%. Kappa is 0.76 to 0.82 for the competitors and the
  golden set, and 0.55 to 0.58 for our two variants, where almost everything is confirmed.

**6. Human check** (`run.py sheet`, `run.py agreement`). 90 issues, 15 per tool for six tools, up to 5 of each 15
from issues the primary verifier did not confirm. The sheet `experiments/005-pooled-truth/labels.csv` shows the
claim, path and PR only. As of this writing, 0 of 90 rows are labelled (issue 03).

**7. Outside verifier.** `run.py sample` wrote a fixed sample for an outside team: seed 0, 34 issues drawn at
random per tool from the issues each tool raised, for `converge-review` and the five competitors. Draws overlap
between tools, so the union is 181 issues over 48 PRs. It is in `validation/sample/<pr>.json` (neutral claims
only, in the ledger shape) and `validation/index.json` (the strata). `run.py external <dir>` compares an outside
run with both Claude verifiers. The checklist is [`validation/README.md`](validation/README.md).

## Outside verification with Codex: protocol differences

`verify.py --cli codex` runs each verification as:

```
codex exec --model <model> -c model_reasoning_effort="<effort>" --sandbox read-only --ephemeral \
  --ignore-user-config --skip-git-repo-check --cd <worktree> --json --output-last-message <tmp> -
```

with the prompt on stdin. It differs from the Claude runs in four ways. State them with any comparison.

1. **No system prompt.** Codex has no system-prompt flag, so `SYSTEM` is prepended to the task text. Claude runs
   pass it with `--system-prompt`.
2. **Tools.** Claude runs had Read, Grep and Glob only. Codex works through its own tools inside a read-only
   sandbox.
3. **Cost.** Codex verdicts record `cost_usd: 0` and the last JSONL event that carries `usage`. Claude verdicts
   record `cost_usd` from the CLI.
4. **Recorded fields.** Verdicts written since this change record `cli`, `model` and `effort`. The committed
   Claude verdicts predate it and do not; their models are documented above.

Other changes that apply to both CLIs: a PR with no ledger file is skipped ("no ledger, skipped"), and
`BENCH_WORK` overrides the work directory (default `benchmark/work`).

## Prior research

The project docs name these methods but cite no papers, except the benchmark itself. The references below were
checked to exist on 2026-11-17. They are background for the methods; this work does not claim to follow any of
them exactly.

| Used here | Reference |
|---|---|
| The benchmark | Martian, Code Review Bench: <https://github.com/withmartian/code-review-benchmark>. Its README names the Augment and Greptile benchmarks it replicates: <https://www.augmentcode.com/blog/introducing-augment-code-review>, <https://www.greptile.com/blog/code-review-benchmark>. |
| Pooled ground truth (005) | Zobel, J. (1998). How reliable are the results of large-scale information retrieval experiments? SIGIR '98, 307-314. <https://doi.org/10.1145/290941.291014>. On pooled relevance judgments in TREC, and how pooling overstates recall. |
| Paired bootstrap | Koehn, P. (2004). Statistical significance tests for machine translation evaluation. EMNLP 2004. <https://aclanthology.org/W04-3250/> |
| Approximate randomisation | Riezler, S. and Maxwell, J. T. (2005). On some pitfalls in automatic evaluation and significance testing for MT. ACL 2005 workshop. <https://aclanthology.org/www.mt-archive.info/05/ACL-2005-Riezler.pdf> |
| Holm correction | Holm, S. (1979). A simple sequentially rejective multiple test procedure. Scandinavian Journal of Statistics 6(2), 65-70. <https://www.jstor.org/stable/4615733> |
| Cohen's kappa | Cohen, J. (1960). A coefficient of agreement for nominal scales. Educational and Psychological Measurement 20(1), 37-46. <https://doi.org/10.1177/001316446002000104> |
| Prompt optimisers considered and not used | GEPA: <https://arxiv.org/abs/2507.19457>. MIPRO (DSPy's MIPROv2): <https://arxiv.org/abs/2406.11695>. Not used because full reviews would cost thousands of dollars per optimisation, and 173 labels cannot support a free-text search without fitting the judge. |

## Caveats and open issues

Issue numbers refer to `docs/issues/`.

| # | Caveat | Effect |
|---|---|---|
| 01 | One review run. Run-to-run variance unmeasured. Three full runs would cost about 555 USD. | No CI includes review noise. |
| 03 | Human check of experiment 005 not done (0 of 90 labelled). | Every 005 number is provisional. |
| 04 | Contamination not checked. All 50 PRs are public. | Cannot rule out that the model saw the PRs or their fixes. |
| 05 | Judge runs through the `claude` CLI, not at temperature 0. | Size unmeasured. |
| 10 | Both 005 verifiers are Claude, as were the reviewers and `claude-code`. The three Claude-written sources have the highest truth precision. | Looks like family bias or a real difference; only a human check or outside verifier can tell. |
| 11 | The shipped skill ranks findings and does not filter: `skills/converge-review/SKILL.md` equals `skill/SKILL.shipped.md`. | The F1 gain of experiment 001 came from the filter and does not transfer to the shipped text. |
| 06 | The adopted rule was applied to the author's own Nix config on an unpushed branch. | No effect on results. |

Further limits:

- The skill was tuned on this benchmark. 6 variants judged, about 45 simulated.
- Competitor results are single stored runs of possibly older tool versions.
- Benchmark mode stops after the merge. The fix loop (steps 5 and 6) is never measured.
- Experiment 005: pooled recall rewards volume (543 of 1,109 issues are ours alone); the neutral claim is a
  rewrite and may sharpen or blur a comment; the verifier reads code and does not run it; candidates come from
  the Opus judge's extraction; one review, merge, grouping and verifier run each.
- Blindness of the second verifier. The Opus verifier of experiment 005 ran with its work directory inside the
  repository, while the primary verifier's verdicts sat in `verify/pool-fable`. A verifier browsing parent
  directories could have found them. No sign that it did; this is a minor caveat. The outside run sets
  `BENCH_WORK` outside the repository for this reason.
- The versions of the four seat skills at review time are not recorded. `flake.lock` pins the versions the flake
  installs today.
- Reviews ran on Claude Code 2.1.322; the dev shell now provides 2.1.326.

## Replication

All commands run from `benchmark/` inside `nix develop` (run at the repository root). Manual equivalent: git,
Python 3.11 or later, uv, curl, and the `claude` CLI logged in. `codex` and `ocr` only where noted.

There are four levels. Level A costs nothing and reproduces every reported statistic exactly.

### A. Recompute every statistic from committed data (no model calls)

This needs only the upstream benchmark, not the source repositories.

```bash
git clone https://github.com/withmartian/code-review-benchmark.git vendor/code-review-benchmark
git -C vendor/code-review-benchmark checkout -q e616e849755441da38f18bf3adba2c9583b03803
```

A fresh upstream clone has no results for our tools. `results/opus.json` and `results/sonnet.json` hold our
tools' candidates and evaluations. Merge them into the upstream results:

```bash
python3 - <<'EOF'
import json
from pathlib import Path
R = Path("vendor/code-review-benchmark/offline/results")
for judge, name in {"opus": "anthropic_claude-opus-4-5-20251101", "sonnet": "anthropic_claude-sonnet-4-5-20250929"}.items():
    ours = json.loads(Path(f"results/{judge}.json").read_text())
    for part in ("candidates", "evaluations"):
        f = R / name / f"{part}.json"
        data = json.loads(f.read_text())
        for url, tools in ours[part].items():
            data.setdefault(url, {}).update(tools)
        f.write_text(json.dumps(data, indent=2) + "\n")
EOF
```

Then:

```bash
python3 -m unittest test_bench
python3 evalstats.py
python3 experiments/001-agreement-threshold/run.py select
python3 experiments/001-agreement-threshold/run.py report
python3 experiments/002-comment-format/run.py
python3 experiments/003-merge-replay/run.py
python3 experiments/004-verify-main-list/run.py
python3 experiments/005-pooled-truth/run.py report
git status --short -- results experiments
```

`evalstats.py` prints `matches the dashboard` for both judges. The experiment scripts rewrite their
`results.json`, `counts.json`, `selection.json` and `results/*.json` in place. On 2026-11-17 this sequence, run on
a fresh clone, reproduced every one of those files byte for byte, so `git status` shows no change.
`python3 experiments/005-pooled-truth/run.py sample` likewise regenerates `validation/` byte for byte; there is no
need to run it.

Do not run `python3 -I` on these scripts: `-I` drops the script's directory from the import path, and they import
`bench` and `evalstats`.

### B. Re-judge (judge calls only)

Needs the `claude` CLI with access to `claude-opus-4-5-20251101` and `claude-sonnet-4-5-20250929`. Use a clean
upstream clone without the merge from level A: steps 2 and 3 skip any tool that already has results.

```bash
./prepare.sh
./score.sh                                                   # converge-review, the original run
TOOL=converge-review-k3 MIN_SEATS=3 ./score.sh               # experiment 001
TOOL=converge-review-k3-claim MIN_SEATS=3 ./score.sh --claim-only     # experiment 002
TOOL=converge-review-replay ./score.sh --out replay/adopted  # experiment 003
TOOL=converge-review-atomic ./score.sh --out replay/atomic   # experiment 003
TOOL=converge-review-verified ./score.sh --out verify/adopted/ledgers # experiment 004
```

Arguments after `score.sh` go to `bench.py ingest`. `JUDGES="anthropic/claude-opus-4-5-20251101" ./score.sh`
judges with one model. Then run the level A scripts without the merge step. Expect small differences: the judge
is not deterministic. Cost reference: about 49 USD for the baseline, 24.76 to 25.07 USD per later variant.

`./prepare.sh` needs network access to github.com (clones) and PyPI (`uv sync`), and about 2 GB of disk for
`repos/` plus about 0.4 GB for `vendor/`. `prs.json` is committed and complete, so `bench.py manifest` makes no
GitHub API calls and no `GH_TOKEN` is needed. If it ever has to resolve a PR, it reads `GH_TOKEN` or
`GITHUB_TOKEN`; without one, GitHub allows 60 API calls per hour.

### C. Re-run the reviews (about 184 USD)

1. Install the skills: `nix run .` from the repository root copies `converge-review` and the four seat skills
   into `~/.claude/skills` (it keeps existing directories). Replace `~/.claude/skills/converge-review/SKILL.md`
   with `benchmark/skill/SKILL.baseline.md` to run what the 50 reviews ran. `ocr` must be on `PATH` (the dev shell
   provides it).
2. Move the committed ledgers aside, because `bench.py run` skips PRs that already have one: `mv out out.committed`.
3. `./bench.py run --limit 1`, then read `out/*.json` and `total_cost_usd` in `out/*.log.json`.
4. `./bench.py run --jobs 2`. It resumes. `--force` re-runs PRs that have findings; do not use it inside one run.
5. `python3 cache_seats.py` copies the seat reports from `~/.claude/projects` into `cache/seat-reports/`, before
   Claude Code cleans up the transcripts.
6. Score as in level B.

### D. Re-run replays, verification and the pool

Write to new directories so the committed data stays as it is. All of these resume.

```bash
python3 replay.py --skill skill/SKILL.md --out replay-new/adopted          # 003, merge calls
python3 replay.py --skill skill/SKILL.atomic.md --out replay-new/atomic    # 003
python3 verify.py --ledgers replay/adopted --out verify-new/adopted        # 004
python3 pool.py --out pool-new                                             # 005, grouping
python3 verify.py --ledgers pool/ledgers --out verify-new/pool-fable --model claude-fable-5-2   # 005, primary
python3 verify.py --ledgers pool/ledgers --out verify-new/pool-opus                            # 005, second
```

`pool.py` reads the Opus judge's candidates for all seven sources, so `converge-review` and
`converge-review-replay` must be judged (level B) or merged (level A) first. `verify.py` needs `./prepare.sh`
(the source repositories). Set `BENCH_WORK` to a directory outside the repository so verifiers cannot browse to
earlier verdicts. `run.py report` reads the fixed paths `pool/` and `verify/pool-*`; to score new runs, point
`POOL` and `VERIFIERS` in `experiments/005-pooled-truth/run.py` at them.

Cost references (list price): merge replay 16.31 and 18.07 USD per arm; verifier on 300 findings 36.70 USD;
grouping 4.54 USD; verifiers on 1,109 issues 367.91 USD (Fable) and 139.11 USD (Opus).

## Files and data

| Path | What |
|---|---|
| `prepare.sh` | Clones the upstream benchmark at the pin, runs `uv sync`, resolves the manifest, clones the source repos, dry-runs one PR. Resumes. |
| `bench.py` | `manifest` (PR SHAs via the GitHub API), `repos` (bare blobless clones, PR heads, merge-bases), `run` (one review per PR), `ingest` (ledgers into `benchmark_data.json`; `--tool`, `--min-seats`, `--claim-only`, `--out`). `BENCH_WORK` sets the work directory. |
| `score.sh` | Ingest, then extract, dedup and judge for one tool under each judge; rebuilds the dashboard. |
| `judge_proxy.py` | Local OpenAI-compatible endpoint that answers through `claude -p`. Anthropic models only. |
| `evalstats.py` | Per-PR counts, pooled metrics, paired bootstrap, randomisation, Holm, fold selection, acceptance checks, results snapshot. |
| `cache_seats.py` | Copies seat reports out of Claude Code transcripts. |
| `replay.py` | Replays step 4 on cached seat reports with a given skill text. |
| `verify.py` | One read-only verifier per main-list finding; `--cli claude` or `--cli codex`. |
| `pool.py` | Pools all sources' candidates per PR and groups them into issues. |
| `experiments/<id>/run.py` | Selection, scoring and tests for each experiment. 005 also has `sheet`, `agreement`, `sample` and `external`. |
| `experiments/005-pooled-truth/chart.py` | Renders the 005 chart as HTML. |
| `test_bench.py` | Unit tests of `bench.ingest`. |
| `prs.json` | The 50 PRs: id, repo, number, base, head and merge-base SHAs. |
| `skill/` | `SKILL.baseline.md` (the 50 reviews), `SKILL.md` (adopted in 001), `SKILL.atomic.md` (003 arm), `SKILL.shipped.md` (shipped; equals `../skills/converge-review/SKILL.md`). |
| `out/<pr>.json`, `out/<pr>.log.json` | The 50 review ledgers and the CLI logs with `total_cost_usd`. |
| `cache/seat-reports/<pr>/<seat>.md` | 200 seat reports, four per PR. |
| `results/opus.json`, `results/sonnet.json` | Our tools' judge candidates and evaluations, copied from the upstream working tree. |
| `replay/adopted/`, `replay/atomic/` | Experiment 003 ledgers and logs; `*.failed1.log.json` are the re-run calls. |
| `verify/adopted/` | Experiment 004 verdicts, `<pr>/<n>.json`, and `ledgers/`. |
| `pool/<pr>.json`, `pool/ledgers/` | Experiment 005 pool and neutral-claim ledgers. `calcom__cal.com__11059.failed.txt` is the failed first grouping call. |
| `verify/pool-fable/`, `verify/pool-opus/` | Experiment 005 verdicts and ledgers. Three `*.failed.txt` in `pool-opus` are the malformed calls that were re-run. |
| `experiments/<id>/results.json`, `counts.json` | Every metric, CI and p-value; per-PR counts. 001 also has `selection.json`. |
| `experiments/005-pooled-truth/labels.csv`, `labels.key.json` | The blind human-check sheet and its key. Do not open the key before labelling. |
| `validation/sample/`, `validation/index.json` | The fixed outside-verifier sample. |
| `docs/` | Methodology, findings, experiment logs, issues, outreach drafts. |

Not committed: `vendor/`, `repos/`, `work/`, `.env`, `judge_proxy.log`, `repos.log`.

## Gaps in this directory's docs

- `docs/adr/` is empty.
- `docs/outreach/linkedin-post.md` mentions a sample of about 200 issues. The sample has 181.
