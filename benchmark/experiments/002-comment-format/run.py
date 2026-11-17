#!/usr/bin/env python3
"""Experiment 002: send each finding's claim without its evidence. Pre-registration: docs/experiments/002-comment-format.md."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
import evalstats as es

VARIANTS = {"evidence": "converge-review-k3", "claim": "converge-review-k3-claim"}
RECALL_FLOOR = 60.0
MIN_EFFECT = 3.0
COMPETITORS = ("coderabbit", "claude-code", "cubic-v2", "qodo-extended-v2", "augment")
FINDINGS = 282


def choose(counts, urls):
    scores = {v: es.pooled(counts[v][u] for u in urls) for v in VARIANTS}
    ok = [v for v in VARIANTS if scores[v]["r"] >= RECALL_FLOOR] or ["evidence"]
    return max(ok, key=lambda v: (scores[v]["f1"], v == "evidence")), scores


def main():
    counts = {j: {v: es.load_counts(j, t) for v, t in VARIANTS.items()} for j in es.JUDGES}
    urls = list(counts["opus"]["evidence"])
    folds = {}
    for repo in es.REPOS:
        v, scores = choose(counts["opus"], [u for u in urls if es.repo_of(u) != repo])
        folds[repo] = v
        print(f"held out {repo:9}: {v:8}  " + "  ".join(f"{k} F1 {s['f1']:.1f} R {s['r']:.1f}" for k, s in scores.items()))
    oof = {j: {u: counts[j][folds[es.repo_of(u)]][u] for u in urls} for j in es.JUDGES}
    res = es.compare(oof, {j: counts[j]["evidence"] for j in es.JUDGES}, COMPETITORS, RECALL_FLOOR, MIN_EFFECT)
    res["selection"] = folds
    res["in_sample"], res["candidates_per_finding"] = {}, {}
    print("\nin-sample, all 50 PRs:")
    for j, name in es.JUDGES.items():
        cands = json.loads((es.RESULTS / name / "candidates.json").read_text())
        for v, t in VARIANTS.items():
            m = es.pooled(counts[j][v].values())
            cpf = sum(len(c.get(t, [])) for c in cands.values()) / FINDINGS
            res["in_sample"][f"{j}/{v}"], res["candidates_per_finding"][f"{j}/{v}"] = m, cpf
            print(f"  {j:6} {v:8} {es.fmt(m)}  candidates per finding {cpf:.2f}")
    (HERE / "results.json").write_text(json.dumps(res, indent=1) + "\n")
    (HERE / "counts.json").write_text(json.dumps(counts) + "\n")
    es.snapshot()


if __name__ == "__main__":
    main()
