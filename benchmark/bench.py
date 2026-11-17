#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OFFLINE = ROOT / "vendor/code-review-benchmark/offline"
DATA = OFFLINE / "results/benchmark_data.json"
MANIFEST = ROOT / "prs.json"
REPOS = ROOT / "repos"
WORK = Path(os.environ.get("BENCH_WORK") or ROOT / "work").resolve()
OUT = ROOT / "out"
TOOL = "converge-review"
SEVERITIES = {"Critical", "Important", "Minor"}
VERDICTS = {"fix", "defer", "reject"}


def pr_id(url):
    owner, repo, num = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", url).groups()
    return owner, repo, int(num), f"{owner}__{repo}__{num}"


def gh_api(path):
    req = urllib.request.Request(f"https://api.github.com{path}", headers={"Accept": "application/vnd.github+json"})
    if token := os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def cmd_manifest(_):
    prs = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    for url in json.loads(DATA.read_text()):
        if url in prs:
            continue
        owner, repo, num, pid = pr_id(url)
        pr = gh_api(f"/repos/{owner}/{repo}/pulls/{num}")
        prs[url] = {"id": pid, "repo": f"{owner}/{repo}", "number": num,
                    "base_sha": pr["base"]["sha"], "head_sha": pr["head"]["sha"]}
        MANIFEST.write_text(json.dumps(prs, indent=2) + "\n")
        print(f"{pid}: base {pr['base']['sha'][:9]} head {pr['head']['sha'][:9]}")
    print(f"{len(prs)} PRs in {MANIFEST.name}")


def cmd_repos(_):
    prs = json.loads(MANIFEST.read_text())
    by_repo = {}
    for p in prs.values():
        by_repo.setdefault(p["repo"], []).append(p)
    for repo, items in by_repo.items():
        dest = REPOS / repo.replace("/", "__")
        if not dest.exists():
            print(f"clone {repo} (blobless, bare)")
            subprocess.run(["git", "clone", "--bare", "--filter=blob:none", f"https://github.com/{repo}.git", str(dest)],
                           check=True)
        refs = []
        for p in items:
            refs += [p["base_sha"], f"+refs/pull/{p['number']}/head:refs/bench/pr-{p['number']}"]
        print(f"fetch {len(items)} PRs into {dest.name}")
        subprocess.run(["git", "-C", str(dest), "fetch", "--filter=blob:none", "origin", *refs], check=True)
        for p in items:
            head = git(dest, "rev-parse", f"refs/bench/pr-{p['number']}")
            if head != p["head_sha"]:
                sys.exit(f"{p['id']}: pull head moved to {head}, manifest says {p['head_sha']}")
            p["merge_base"] = git(dest, "merge-base", p["base_sha"], p["head_sha"])
    MANIFEST.write_text(json.dumps(prs, indent=2) + "\n")
    print("all PR heads and merge-bases resolved")


PROMPT = """/converge-review

Benchmark mode. These overrides apply to this run only and beat the skill text where they conflict:
- Base: {merge_base}. The checkout is the PR head ({head_sha}) with a clean tree. No spec.
- Write the pinned patch file and any scratch files under {scratch}, never inside the repository.
- Gate: {gate}
- Run steps 1-4 (pin, gate, round-1 full review, merge) and the Rejections rule. Stop after the merge:
  no fixes, no red tests, no rounds 2+, no edits to any file in the repository.
- Write the merged ledger as JSON to {out} with exactly this shape, and nothing else in that file:
  {{"findings": [{{"path": "repo-relative path", "line": <int or null>, "severity": "Critical|Important|Minor",
  "claim": "...", "evidence": "...", "seats": ["..."], "verdict": "fix|defer|reject", "reason": "..."}}],
  "coverage": "files skipped and axes that did not run"}}
  Every finding from the merge goes in, rejected ones too with verdict "reject".
"""

GATES = {
    "skip": "do not install dependencies or run project checks; record the gate as not run (benchmark mode).",
    "run": "discover and run the project's checks as the skill says.",
}


def run_one(url, p, args):
    out = OUT / f"{p['id']}.json"
    if out.exists() and not args.force:
        return f"{p['id']}: done already"
    bare = REPOS / p["repo"].replace("/", "__")
    wt = WORK / p["id"]
    scratch = WORK / f"{p['id']}.scratch"
    prompt = PROMPT.format(merge_base=p["merge_base"], head_sha=p["head_sha"], scratch=scratch,
                           gate=GATES[args.gate], out=out)
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--add-dir", str(OUT), "--add-dir", str(scratch),
           *args.claude_args.split()]
    if args.dry_run:
        return f"{p['id']}: would run in {wt}:\n  {' '.join(cmd[:2])} <prompt> {' '.join(cmd[3:])}\n{prompt}"
    scratch.mkdir(parents=True, exist_ok=True)
    try:
        if not wt.exists():
            git(bare, "worktree", "add", "--detach", str(wt), p["head_sha"])
        git(wt, "diff", "--no-ext-diff", p["merge_base"], p["head_sha"])
    except subprocess.CalledProcessError as e:
        return f"{p['id']}: FAILED, checkout of {p['head_sha'][:9]}: {e.stderr.strip()[-300:]}"
    log = OUT / f"{p['id']}.log.json"
    try:
        r = subprocess.run(cmd, cwd=wt, capture_output=True, text=True, timeout=args.timeout * 60,
                           env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull})
        log.write_text(r.stdout or r.stderr)
    except subprocess.TimeoutExpired:
        return f"{p['id']}: TIMEOUT after {args.timeout} min"
    if git(wt, "status", "--porcelain"):
        return f"{p['id']}: FAILED, the run edited the checkout; inspect {wt}"
    if not out.exists():
        return f"{p['id']}: FAILED, no {out.name} (exit {r.returncode}), see {log.name}"
    try:
        validate(json.loads(out.read_text()), p["id"])
    except (ValueError, KeyError, TypeError) as e:
        out.rename(out.with_suffix(".invalid.json"))
        return f"{p['id']}: FAILED, findings file does not match the schema: {e}"
    git(bare, "worktree", "remove", "--force", str(wt))
    return f"{p['id']}: ok"


def cmd_run(args):
    prs = json.loads(MANIFEST.read_text())
    if any("merge_base" not in p for p in prs.values()):
        sys.exit("run `./prepare.sh` first: merge-bases missing from prs.json")
    items = [(u, p) for u, p in prs.items() if not args.only or p["id"] in args.only][: args.limit]
    OUT.mkdir(exist_ok=True)
    with ThreadPoolExecutor(args.jobs) as ex:
        for msg in ex.map(lambda it: run_one(*it, args), items):
            print(msg, flush=True)


def validate(doc, pid):
    for f in doc["findings"]:
        if f["severity"] not in SEVERITIES or f["verdict"] not in VERDICTS or not f.get("claim"):
            raise ValueError(f"{pid}: bad finding {f}")
    return doc


def to_review(url, doc, tool=TOOL, min_seats=0, claim_only=False):
    comments = []
    for f in doc["findings"]:
        if f["verdict"] == "reject" or f.get("list") == "appendix" or len(f.get("seats") or []) < min_seats:
            continue
        body = f"[{f['severity']}] {f['claim']}"
        if f.get("evidence") and not claim_only:
            body += f"\n\n{f['evidence']}"
        comments.append({"path": f.get("path"), "line": f.get("line"), "body": body})
    return {"tool": tool, "pr_url": url, "review_comments": comments}


def ingest(data, prs, out_dir, allow_partial=False, tool=TOOL, min_seats=0, claim_only=False):
    missing = [u for u in data if u not in prs or not (out_dir / f"{prs[u]['id']}.json").exists()]
    if missing and not allow_partial:
        raise SystemExit(f"{len(missing)} PRs have no findings yet (a missing PR silently drops out of recall): "
                         + ", ".join(missing))
    for url, p in prs.items():
        f = out_dir / f"{p['id']}.json"
        if url not in data or not f.exists():
            continue
        entry = data[url]
        entry["reviews"] = [r for r in entry["reviews"] if r["tool"] != tool]
        entry["reviews"].append(to_review(url, validate(json.loads(f.read_text()), p["id"]), tool, min_seats, claim_only))
    return data


def cmd_ingest(args):
    data = ingest(json.loads(DATA.read_text()), json.loads(MANIFEST.read_text()), args.out, args.allow_partial,
                  args.tool, args.min_seats, args.claim_only)
    DATA.write_text(json.dumps(data, indent=2) + "\n")
    n = sum(1 for e in data.values() for r in e["reviews"] if r["tool"] == args.tool)
    print(f"wrote {n} {args.tool} reviews into {DATA.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(required=True)
    sub.add_parser("manifest", help="resolve base/head SHAs of the 50 PRs via the GitHub API").set_defaults(fn=cmd_manifest)
    sub.add_parser("repos", help="blobless-clone source repos, fetch PR heads, compute merge-bases").set_defaults(fn=cmd_repos)
    r = sub.add_parser("run", help="run /converge-review on each PR")
    r.add_argument("--limit", type=int)
    r.add_argument("--only", nargs="*", help="PR ids, e.g. grafana__grafana__79265")
    r.add_argument("--jobs", type=int, default=1)
    r.add_argument("--gate", choices=GATES, default="skip")
    r.add_argument("--timeout", type=int, default=60, help="minutes per PR")
    r.add_argument("--force", action="store_true", help="re-run PRs that already have findings")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--claude-args", default=os.environ.get("CLAUDE_ARGS", "--permission-mode auto"))
    r.set_defaults(fn=cmd_run)
    i = sub.add_parser("ingest", help="write findings into the benchmark's benchmark_data.json")
    i.add_argument("--allow-partial", action="store_true")
    i.add_argument("--tool", default=TOOL, help="name to ingest under; use a new name for each variant")
    i.add_argument("--min-seats", type=int, default=0, help="keep only findings raised by at least this many seats")
    i.add_argument("--claim-only", action="store_true", help="send each finding's claim without its evidence")
    i.add_argument("--out", type=Path, default=OUT, help="directory of ledgers to ingest, e.g. a replay.py output")
    i.set_defaults(fn=cmd_ingest)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
