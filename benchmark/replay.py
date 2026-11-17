#!/usr/bin/env python3
"""Replay step 4 of the skill (merge) on the cached seat reports, with a given skill text.

    ./replay.py --skill skill/SKILL.md --out replay/adopted

One `claude -p` call per PR, no tools, the skill text as the system prompt. Resumes: a PR with a ledger is skipped.
The ledgers have the shape `bench.py ingest --out <dir>` reads, plus "list": "main" or "appendix" per finding.
"""
import argparse
import json
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from bench import MANIFEST, ROOT, validate

SEATS = ROOT / "cache/seat-reports"
CWD = tempfile.mkdtemp(prefix="replay-")
TASK = """Benchmark replay of step 4. Steps 1 to 3 are done: the inputs are pinned, the gate was not run (benchmark
mode), and the four seats have reported. Their reports follow, one per seat, unedited.

Do step 4 (Merge) and apply the Rejections rule, then stop. No fixes and no rounds 2+.
You have no repository access and cannot dispatch agents. Where the Rejections rule calls for a verifier, keep the
finding and write "unverified" in its reason. Reject only what the seat reports themselves disprove.

Reply with one JSON object and nothing else, in exactly this shape:
{"findings": [{"path": "repo-relative path", "line": <int or null>, "severity": "Critical|Important|Minor",
"claim": "...", "evidence": "...", "seats": ["..."], "verdict": "fix|defer|reject", "reason": "...",
"list": "main|appendix"}], "coverage": "files skipped and axes that did not run"}
Every finding from the merge goes in: rejected ones with verdict "reject", appendix ones with list "appendix".
Name each seat exactly as its report is labelled below.
"""


def prompt(pid):
    reports = sorted((SEATS / pid).glob("*.md"))
    if len(reports) != 4:
        raise ValueError(f"{pid}: expected 4 seat reports, found {len(reports)}")
    return TASK + "".join(f'\n<seat-report seat="{r.stem}">\n{r.read_text()}</seat-report>\n' for r in reports)


def run_one(pid, args):
    out = args.out / f"{pid}.json"
    if out.exists():
        return f"{pid}: done already"
    cmd = ["claude", "-p", "--model", args.model, "--effort", args.effort, "--system-prompt", args.skill.read_text(),
           "--setting-sources", "", "--tools", "", "--strict-mcp-config", "--no-session-persistence",
           "--output-format", "json"]
    try:
        r = subprocess.run(cmd, input=prompt(pid), capture_output=True, text=True, cwd=CWD, timeout=args.timeout * 60)
    except subprocess.TimeoutExpired:
        return f"{pid}: TIMEOUT after {args.timeout} min"
    (args.out / f"{pid}.log.json").write_text(r.stdout or r.stderr)
    try:
        text = json.loads(r.stdout)["result"]
        doc = validate(json.loads(text[text.index("{"): text.rindex("}") + 1]), pid)
        for f in doc["findings"]:
            if f.get("list") not in ("main", "appendix") or not isinstance(f.get("seats"), list):
                raise ValueError(f"{pid}: bad finding {f}")
    except (ValueError, KeyError, TypeError) as e:
        return f"{pid}: FAILED, {type(e).__name__}: {str(e)[:200]}; see {pid}.log.json"
    out.write_text(json.dumps(doc, indent=1) + "\n")
    return f"{pid}: ok, {len(doc['findings'])} findings"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skill", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--only", nargs="*", help="PR ids")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--timeout", type=int, default=20, help="minutes per PR")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    pids = [p["id"] for p in json.loads(MANIFEST.read_text()).values() if not args.only or p["id"] in args.only]
    with ThreadPoolExecutor(args.jobs) as ex:
        for msg in ex.map(lambda pid: run_one(pid, args), pids):
            print(msg, flush=True)


if __name__ == "__main__":
    main()
