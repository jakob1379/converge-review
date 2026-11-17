#!/usr/bin/env python3
"""Pool every tool's judged comments per PR, merge duplicates into unique issues, and write them for verify.py.

    ./pool.py --out pool

Per PR: the Opus judge's candidates for each tool, plus the golden comments, shuffled and stripped of their source.
One `claude -p` call groups the ones that describe the same defect and writes a neutral claim per group. Resumes: a
PR with a pool file is skipped. Writes <out>/<pr>.json (items with their source, issues with their members) and
<out>/ledgers/<pr>.json (the neutral claims only, in the shape verify.py reads).
"""
import argparse
import json
import random
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from bench import DATA, MANIFEST, OFFLINE

TOOLS = ("converge-review", "converge-review-replay", "coderabbit", "claude-code", "cubic-v2", "qodo-extended-v2",
         "augment")
CANDIDATES = OFFLINE / "results/anthropic_claude-opus-4-5-20251101/candidates.json"
CWD = tempfile.mkdtemp(prefix="pool-")
SYSTEM = "You group code-review comments that describe the same defect. You do not judge whether they are right."
TASK = """Below are code-review comments on one pull request, collected from several reviewers and shuffled. Each
has an id.

Group the comments that describe the same defect: the same thing wrong, for the same reason, in the same place.
Comments about different defects stay apart, even in the same file or function. A comment that holds two defects
goes with the one it is mainly about.

For each group write one neutral claim: what is wrong and where, in one or two plain sentences, stated as a fact
that can be checked against the code. Use only what the comments in the group say. Leave out severity, advice,
hedging and praise. Give the file path if any comment in the group names it.

Reply with one JSON object and nothing else:
{"issues": [{"claim": "...", "path": "file path or null", "members": ["c1", "c7"]}]}
Every id must appear in exactly one group. A comment with no match is a group of one.

"""


def items(url, pid, data, cands):
    out = [{"source": t, "text": c["text"]} for t in TOOLS for c in cands[url].get(t, [])]
    out += [{"source": "golden", "text": g["comment"]} for g in data[url]["golden_comments"]]
    random.Random(pid).shuffle(out)
    return [{"id": f"c{i + 1}", **it} for i, it in enumerate(out)]


def pool_one(url, p, data, cands, args):
    pid = p["id"]
    dest = args.out / f"{pid}.json"
    if dest.exists():
        return f"{pid}: done already"
    its = items(url, pid, data, cands)
    cmd = ["claude", "-p", "--model", args.model, "--effort", args.effort, "--system-prompt", SYSTEM,
           "--setting-sources", "", "--tools", "", "--strict-mcp-config", "--no-session-persistence",
           "--output-format", "json"]
    try:
        r = subprocess.run(cmd, input=TASK + "\n".join(f"{it['id']}: {it['text']}" for it in its),
                           capture_output=True, text=True, cwd=CWD, timeout=args.timeout * 60)
        log = json.loads(r.stdout)
        text = log["result"]
        issues = json.loads(text[text.index("{"): text.rindex("}") + 1])["issues"]
        seen = [m for i in issues for m in i["members"]]
        if sorted(seen) != sorted(it["id"] for it in its) or any(not i["claim"] for i in issues):
            raise ValueError(f"{len(seen)} member ids for {len(its)} items, or an empty claim")
    except (subprocess.TimeoutExpired, ValueError, KeyError, TypeError) as e:
        (args.out / f"{pid}.failed.txt").write_text(f"{type(e).__name__}: {e}\n")
        return f"{pid}: FAILED, {type(e).__name__}: {str(e)[:160]}"
    issues = [{"id": f"i{n + 1}", "claim": i["claim"], "path": i.get("path"), "members": i["members"]}
              for n, i in enumerate(issues)]
    dest.write_text(json.dumps({"pr_url": url, "cost_usd": log.get("total_cost_usd", 0), "items": its,
                                "issues": issues}, indent=1) + "\n")
    ledger = {"findings": [{"issue": i["id"], "path": i["path"], "line": None, "severity": "Minor", "claim": i["claim"],
                            "evidence": None, "seats": [], "verdict": "fix", "list": "main"} for i in issues],
              "coverage": "pooled issues; severity and verdict are placeholders"}
    (args.out / "ledgers" / f"{pid}.json").write_text(json.dumps(ledger, indent=1) + "\n")
    return f"{pid}: ok, {len(its)} comments in {len(issues)} issues"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--only", nargs="*", help="PR ids")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--timeout", type=int, default=20, help="minutes per PR")
    args = ap.parse_args()
    (args.out / "ledgers").mkdir(parents=True, exist_ok=True)
    data, cands = json.loads(DATA.read_text()), json.loads(CANDIDATES.read_text())
    prs = [(u, p) for u, p in json.loads(MANIFEST.read_text()).items() if not args.only or p["id"] in args.only]
    with ThreadPoolExecutor(args.jobs) as ex:
        for msg in ex.map(lambda up: pool_one(*up, data, cands, args), prs):
            print(msg, flush=True)


if __name__ == "__main__":
    main()
