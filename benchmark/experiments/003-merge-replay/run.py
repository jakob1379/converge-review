#!/usr/bin/env python3
"""Experiment 003: replay the merge step with the adopted skill text and with one issue per finding.

Pre-registration: docs/experiments/003-merge-replay.md.
"""
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
import evalstats as es

ARMS = {"replay": ("converge-review-replay", "replay/adopted"), "atomic": ("converge-review-atomic", "replay/atomic")}
FILTER = "converge-review-k3"
RECALL_FLOOR = 60.0
MIN_EFFECT = 3.0
COMPETITORS = ("coderabbit", "claude-code", "cubic-v2", "qodo-extended-v2", "augment")


def choose(counts, urls):
    scores = {a: es.pooled(counts[a][u] for u in urls) for a in ARMS}
    ok = [a for a in ARMS if scores[a]["r"] >= RECALL_FLOOR] or ["replay"]
    return max(ok, key=lambda a: (scores[a]["f1"], a == "replay")), scores


def ledgers(arm):
    tool, folder = ARMS[arm]
    docs = [json.loads(p.read_text()) for p in sorted((ROOT / folder).glob("*.json")) if not p.name.endswith(".log.json")]
    fs = [f for d in docs for f in d["findings"]]
    main = [f for f in fs if f["verdict"] != "reject" and f["list"] == "main"]
    appendix = [f for f in fs if f["verdict"] != "reject" and f["list"] == "appendix"]
    cost = sum(json.loads(p.read_text()).get("total_cost_usd", 0) for p in (ROOT / folder).glob("*.log.json"))
    cands = {j: sum(len(c.get(tool, [])) for c in json.loads((es.RESULTS / n / "candidates.json").read_text()).values())
             for j, n in es.JUDGES.items()}
    return {"prs": len(docs), "findings": len(fs), "rejected": sum(f["verdict"] == "reject" for f in fs),
            "main": len(main), "appendix": len(appendix),
            "main_with_3_seats": sum(len(f["seats"]) >= 3 for f in main),
            "appendix_with_3_seats": sum(len(f["seats"]) >= 3 for f in appendix),
            "median_claim_words": statistics.median(len(f["claim"].split()) for f in main),
            "candidates_per_main_finding": {j: c / len(main) for j, c in cands.items()}, "merge_cost_usd": cost}


def main():
    counts = {j: {a: es.load_counts(j, t) for a, (t, _) in ARMS.items()} for j in es.JUDGES}
    filt = {j: es.load_counts(j, FILTER) for j in es.JUDGES}
    urls = list(filt["opus"])
    res = {"ledgers": {a: ledgers(a) for a in ARMS}, "in_sample": {}, "fidelity": {}, "atomic_vs_filter": {}}
    for a, d in res["ledgers"].items():
        print(f"{a:7} {d}")
    print("\nin-sample, all 50 PRs:")
    for j in es.JUDGES:
        for name, c in (("filter k3", filt[j]), ("replay", counts[j]["replay"]), ("atomic", counts[j]["atomic"])):
            res["in_sample"][f"{j}/{name}"] = es.pooled(c.values())
            print(f"  {j:6} {name:9} {es.fmt(res['in_sample'][f'{j}/{name}'])}")
        res["fidelity"][j] = es.paired_bootstrap(counts[j]["replay"], filt[j])
        res["atomic_vs_filter"][j] = es.paired_bootstrap(counts[j]["atomic"], filt[j])
    for key, label in (("fidelity", "replay minus filter k3"), ("atomic_vs_filter", "atomic minus filter k3")):
        for j, v in res[key].items():
            print(f"{label}, {j}: dF1 {v['delta']:+.1f}  95% CI {v['lo']:+.1f} to {v['hi']:+.1f}")
    folds = {}
    for repo in es.REPOS:
        a, scores = choose(counts["opus"], [u for u in urls if es.repo_of(u) != repo])
        folds[repo] = a
        print(f"held out {repo:9}: {a:7} " + "  ".join(f"{k} F1 {s['f1']:.1f} R {s['r']:.1f}" for k, s in scores.items()))
    oof = {j: {u: counts[j][folds[es.repo_of(u)]][u] for u in urls} for j in es.JUDGES}
    res["selection"] = folds
    res["atomic_vs_replay"] = es.compare(oof, {j: counts[j]["replay"] for j in es.JUDGES}, COMPETITORS, RECALL_FLOOR, MIN_EFFECT)
    (HERE / "results.json").write_text(json.dumps(res, indent=1) + "\n")
    (HERE / "counts.json").write_text(json.dumps({"arms": counts, "filter": filt}) + "\n")
    es.snapshot()


if __name__ == "__main__":
    main()
