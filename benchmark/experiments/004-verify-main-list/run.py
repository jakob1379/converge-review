#!/usr/bin/env python3
"""Experiment 004: report only main-list findings a verifier confirmed against source.

Pre-registration: docs/experiments/004-verify-main-list.md.
"""
import collections
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
import evalstats as es

ARMS = {"replay": "converge-review-replay", "verified": "converge-review-verified"}
LEDGERS = ROOT / "verify/adopted/ledgers"
RECALL_FLOOR = 60.0
MIN_EFFECT = 4.0
COMPETITORS = ("coderabbit", "claude-code", "cubic-v2", "qodo-extended-v2", "augment")
CORE = es.bd.PROFILE_CATEGORIES["core"]
PRS = json.loads((ROOT / "prs.json").read_text())


def words(s):
    return set(re.findall(r"[a-z0-9_]{3,}", s.lower()))


def traced(judge):
    """Per PR: the verified findings, each with the Core golden matches and false positives the judge gave the
    replay arm, traced to the finding by word overlap. Returns {url: (findings, core golden count)}."""
    out = {}
    for url, tools in es.evaluations(judge).items():
        r = tools[ARMS["replay"]]
        fs = [dict(f, tp=0, fp=0) for f in json.loads((LEDGERS / f"{PRS[url]['id']}.json").read_text())["findings"] if "verifier" in f]
        ws = [words(f["claim"] + " " + (f.get("evidence") or "") + " " + (f.get("path") or "")) for f in fs]

        def owner(text):
            w = words(text)
            return fs[max(range(len(fs)), key=lambda i: len(w & ws[i]) / (len(w) or 1))]

        core = [t for t in r["true_positives"] if t["category"] in CORE]
        for t in core:
            owner(t.get("matched_candidate") or "")["tp"] += 1
        for t in r["false_positives"]:
            owner(t["candidate"])["fp"] += 1
        out[url] = (fs, len(core) + sum(t["category"] in CORE for t in r["false_negatives"]))
    return out


def simulate(tr, keep):
    counts = {}
    for url, (fs, golden) in tr.items():
        tp = sum(f["tp"] for f in fs if keep(f))
        counts[url] = (tp, sum(f["fp"] for f in fs if keep(f)), golden - tp)
    return es.pooled(counts.values())


def main():
    tr = traced("opus")
    fs = [f for v in tr.values() for f in v[0]]
    res = {"verifier": {
        "findings": len(fs),
        "verdicts": collections.Counter(f["verifier"]["verdict"] for f in fs),
        "impact_of_confirmed": collections.Counter(f["verifier"]["impact"] for f in fs if f["verifier"]["verdict"] == "confirmed"),
        "not_introduced_by_patch": sum(not f["verifier"]["introduced_by_patch"] for f in fs),
        "cost_usd": sum(f["verifier"]["cost_usd"] for f in fs),
        "verdict_by_match": {m: collections.Counter(f["verifier"]["verdict"] for f in fs if bool(f["tp"]) == (m == "matched"))
                             for m in ("matched", "unmatched")},
        "impact_by_match": {m: collections.Counter(f["verifier"]["impact"] for f in fs if bool(f["tp"]) == (m == "matched"))
                            for m in ("matched", "unmatched")}}}
    for k, v in res["verifier"].items():
        print(f"{k}: {dict(v) if isinstance(v, collections.Counter) else v}")

    counts = {j: {a: es.load_counts(j, t) for a, t in ARMS.items()} for j in es.JUDGES}
    res["in_sample"] = {}
    print("\nin-sample, all 50 PRs:")
    for j in es.JUDGES:
        for a in ARMS:
            res["in_sample"][f"{j}/{a}"] = es.pooled(counts[j][a].values())
            print(f"  {j:6} {a:9} {es.fmt(res['in_sample'][f'{j}/{a}'])}")
    folds = es.select_folds(counts["opus"], "replay", RECALL_FLOOR)
    urls = list(counts["opus"]["replay"])
    oof = {j: {u: counts[j][folds[es.repo_of(u)]][u] for u in urls} for j in es.JUDGES}
    res["selection"] = folds
    res["verified_vs_replay"] = es.compare(oof, {j: counts[j]["replay"] for j in es.JUDGES}, COMPETITORS, RECALL_FLOOR, MIN_EFFECT)

    confirmed = lambda f: f["verifier"]["verdict"] == "confirmed"
    rules = {"all main-list findings": lambda f: True, "confirmed": confirmed,
             "confirmed, not trivial": lambda f: confirmed(f) and f["verifier"]["impact"] != "trivial",
             "confirmed, blocks-merge": lambda f: confirmed(f) and f["verifier"]["impact"] == "blocks-merge",
             "confirmed, introduced by the patch": lambda f: confirmed(f) and f["verifier"]["introduced_by_patch"],
             "not refuted": lambda f: f["verifier"]["verdict"] != "refuted"}
    res["exploratory_simulation"] = {}
    print("\nexploratory, simulated from the replay arm's Opus judge results (in-sample, not a result):")
    for name, keep in rules.items():
        m = simulate(tr, keep)
        res["exploratory_simulation"][name] = dict(m, findings=sum(keep(f) for f in fs))
        print(f"  {name:36} findings {sum(keep(f) for f in fs):3}  {es.fmt(m)}")
    (HERE / "results.json").write_text(json.dumps(res, indent=1) + "\n")
    (HERE / "counts.json").write_text(json.dumps(counts) + "\n")
    es.snapshot()


if __name__ == "__main__":
    main()
