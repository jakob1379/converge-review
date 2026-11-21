#!/usr/bin/env python3
"""Verify each main-list finding of a set of ledgers against the source, one fresh agent per finding.

    ./verify.py --ledgers replay/adopted --out verify/adopted

Per PR: check out the PR head under work/ ($BENCH_WORK overrides it), write the patch, run one read-only agent per
finding (`claude -p`, `codex exec` with --cli codex, or Antigravity's ACP server with --cli gemini), remove the
checkout. Resumes: a finding with a result is skipped. Writes <out>/<pr>/<n>.json per finding and, once a PR is
complete, <out>/ledgers/<pr>.json: the input ledger with a "verifier" entry per main-list finding and every
finding that was not confirmed moved to the appendix.
"""
import argparse
import itertools
import json
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from bench import MANIFEST, REPOS, WORK, git

VERDICTS = {"confirmed", "refuted", "unverifiable"}
IMPACTS = {"blocks-merge", "worth-fixing", "trivial"}
READ_KINDS = {"read", "search", "think"}
SYSTEM = ("You verify one code-review claim against source code. You report a verdict; you do not fix anything, "
          "edit files, or review anything beyond the one claim.")
TASK = """Verify one code-review claim. The repository is checked out in the current directory at the head of the
change. The whole change is in the patch file {patch}. Read the patch and the source around it.

Claim ({where}): {claim}

Evidence given with the claim: {evidence}

Decide whether the claim is true of the code as this patch leaves it.
- "confirmed": you read the code and the claim is correct.
- "refuted": you read the code and the claim is wrong, or the problem does not exist in the changed code.
- "unverifiable": the source here cannot settle it. It needs a running system, an external service, or code that
  is not in the repository.

Reply with one JSON object and nothing else:
{{"verdict": "confirmed|refuted|unverifiable", "reason": "one or two sentences citing file:line",
"introduced_by_patch": true|false, "impact": "blocks-merge|worth-fixing|trivial"}}
"introduced_by_patch": true if this patch introduces or exposes the problem, false if it lies in code the patch
did not touch.
"impact", assuming the claim is true: "blocks-merge" for wrong behaviour, data loss, a security hole or a crash a
user can hit; "worth-fixing" for a real but limited problem; "trivial" for style, naming or a nit.
"""


def targets(doc):
    return [i for i, f in enumerate(doc["findings"]) if f["verdict"] != "reject" and f.get("list") == "main"]


def ask_claude(task, wt, patch, args):
    cmd = ["claude", "-p", "--model", args.model, "--effort", args.effort, "--system-prompt", SYSTEM,
           "--setting-sources", "", "--tools", "Read,Grep,Glob", "--strict-mcp-config", "--no-session-persistence",
           "--output-format", "json", "--add-dir", str(patch.parent)]
    r = subprocess.run(cmd, input=task, capture_output=True, text=True, cwd=wt, timeout=args.timeout * 60)
    log = json.loads(r.stdout)
    return log["result"], {"cost_usd": log.get("total_cost_usd", 0)}


def ask_codex(task, wt, patch, args):
    with tempfile.TemporaryDirectory() as tmp:
        last = Path(tmp) / "last.txt"
        cmd = ["codex", "exec", "--model", args.model, "-c", f"model_reasoning_effort={json.dumps(args.effort)}",
               "--sandbox", "read-only", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check",
               "--cd", str(wt), "--json", "--output-last-message", str(last), "-"]
        r = subprocess.run(cmd, input=SYSTEM + "\n\n" + task, capture_output=True, text=True, timeout=args.timeout * 60)
        usage = [ln for ln in r.stdout.splitlines() if '"usage"' in ln]
        return last.read_text(), {"cost_usd": 0, "usage": json.loads(usage[-1]) if usage else None}


def ask_gemini(task, wt, patch, args):
    with subprocess.Popen(["agy_acp_server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, text=True, cwd=wt) as p:
        timer = threading.Timer(args.timeout * 60, p.kill)
        timer.start()
        ids, chunks, tools = itertools.count(1), [], []

        def send(msg):
            p.stdin.write(json.dumps({"jsonrpc": "2.0", **msg}) + "\n")
            p.stdin.flush()

        def call(method, params):
            n = next(ids)
            send({"id": n, "method": method, "params": params})
            for line in p.stdout:
                m = json.loads(line)
                if m.get("id") == n and "method" not in m:
                    if "error" in m:
                        raise ValueError(f"{method}: {m['error']}")
                    return m["result"]
                if m.get("method") == "session/update":
                    u = m["params"]["update"]
                    if u.get("sessionUpdate") == "agent_message_chunk" and u["content"].get("type") == "text":
                        chunks.append(u["content"]["text"])
                elif m.get("method") == "session/request_permission":
                    kind = m["params"]["toolCall"].get("kind")
                    want = "allow_once" if kind in READ_KINDS else "reject_once"
                    option = next(o["optionId"] for o in m["params"]["options"] if o["kind"] == want)
                    tools.append({"kind": kind, "allowed": want == "allow_once"})
                    send({"id": m["id"], "result": {"outcome": {"outcome": "selected", "optionId": option}}})
                elif "id" in m and "method" in m:
                    send({"id": m["id"], "error": {"code": -32601, "message": "not supported"}})
            raise TimeoutError(f"ACP server exited during {method}")

        try:
            call("initialize", {"protocolVersion": 1, "clientCapabilities": {
                "fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False}})
            call("authenticate", {"methodId": "oauth-personal"})
            sid = call("session/new", {"cwd": str(wt), "mcpServers": []})["sessionId"]
            call("session/set_config_option", {"sessionId": sid, "configId": "model", "value": args.model})
            call("session/set_config_option", {"sessionId": sid, "configId": "thinking_level", "value": args.effort})
            done = call("session/prompt", {"sessionId": sid, "prompt": [{"type": "text", "text": SYSTEM + "\n\n" + task}]})
        finally:
            timer.cancel()
            p.kill()
        return "".join(chunks), {"cost_usd": 0, "usage": done.get("usage") or done.get("_meta"), "permission_requests": tools}


def verify_one(f, dest, wt, patch, args):
    if dest.exists():
        return
    where = ":".join(str(x) for x in (f.get("path"), f.get("line")) if x) or "location not given"
    task = TASK.format(patch=patch, where=where, claim=f["claim"], evidence=f.get("evidence") or "none")
    try:
        text, meta = {"claude": ask_claude, "codex": ask_codex, "gemini": ask_gemini}[args.cli](task, wt, patch, args)
        v = json.loads(text[text.index("{"): text.rindex("}") + 1])
        if v["verdict"] not in VERDICTS or v["impact"] not in IMPACTS or not isinstance(v["introduced_by_patch"], bool):
            raise ValueError(f"bad verdict {v}")
    except (subprocess.TimeoutExpired, ValueError, KeyError, TypeError, OSError) as e:
        dest.with_suffix(".failed.txt").write_text(f"{type(e).__name__}: {e}\n")
        return
    v.update(meta, cli=args.cli, model=args.model, effort=args.effort)
    dest.write_text(json.dumps(v, indent=1) + "\n")


def run_pr(p, args):
    pid = p["id"]
    if not (args.ledgers / f"{pid}.json").exists():
        return f"{pid}: no ledger, skipped"
    doc = json.loads((args.ledgers / f"{pid}.json").read_text())
    todo = targets(doc)
    out = args.out / pid
    out.mkdir(parents=True, exist_ok=True)
    if any(not (out / f"{i}.json").exists() for i in todo):
        bare, wt, scratch = REPOS / p["repo"].replace("/", "__"), WORK / pid, WORK / f"{pid}.verify"
        scratch.mkdir(parents=True, exist_ok=True)
        patch = scratch / "change.patch"
        try:
            if not wt.exists():
                git(bare, "worktree", "add", "--detach", str(wt), p["head_sha"])
            patch.write_text(git(wt, "diff", "--no-ext-diff", p["merge_base"], p["head_sha"]) + "\n")
        except subprocess.CalledProcessError as e:
            return f"{pid}: FAILED, checkout: {e.stderr.strip()[-300:]}"
        with ThreadPoolExecutor(args.jobs) as ex:
            list(ex.map(lambda i: verify_one(doc["findings"][i], out / f"{i}.json", wt, patch, args), todo))
        dirty = git(wt, "status", "--porcelain")
        git(bare, "worktree", "remove", "--force", str(wt))
        if dirty:
            return f"{pid}: FAILED, a verifier edited the checkout"
    missing = [i for i in todo if not (out / f"{i}.json").exists()]
    if missing:
        return f"{pid}: {len(missing)} of {len(todo)} findings have no verdict; run again to resume"
    for i in todo:
        v = json.loads((out / f"{i}.json").read_text())
        doc["findings"][i]["verifier"] = v
        if v["verdict"] != "confirmed":
            doc["findings"][i]["list"] = "appendix"
    (args.out / "ledgers").mkdir(exist_ok=True)
    (args.out / "ledgers" / f"{pid}.json").write_text(json.dumps(doc, indent=1) + "\n")
    return f"{pid}: ok, {sum(doc['findings'][i]['list'] == 'main' for i in todo)} of {len(todo)} confirmed"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledgers", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--only", nargs="*", help="PR ids")
    ap.add_argument("--pr-jobs", type=int, default=2)
    ap.add_argument("--jobs", type=int, default=4, help="verifiers in parallel within one PR")
    ap.add_argument("--cli", choices=("claude", "codex", "gemini"), default="claude")
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--timeout", type=int, default=20, help="minutes per finding")
    args = ap.parse_args()
    args.ledgers, args.out = args.ledgers.resolve(), args.out.resolve()
    prs = [p for p in json.loads(MANIFEST.read_text()).values() if not args.only or p["id"] in args.only]
    with ThreadPoolExecutor(args.pr_jobs) as ex:
        for msg in ex.map(lambda p: run_pr(p, args), prs):
            print(msg, flush=True)


if __name__ == "__main__":
    main()
