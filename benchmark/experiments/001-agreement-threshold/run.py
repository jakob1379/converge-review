#!/usr/bin/env python3
"""Experiment 001: report only findings raised by at least k seats. Pre-registration: docs/experiments/001-agreement-threshold.md."""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
import evalstats as es

KS = (1, 2, 3, 4)
RECALL_FLOOR = 60.0
MIN_EFFECT = 5.0
COMPETITORS = ("coderabbit", "claude-code", "cubic-v2", "qodo-extended-v2", "augment")
CORE = es.bd.PROFILE_CATEGORIES["core"]
PRS = json.loads((ROOT / "prs.json").read_text())


def tool(k):
    return es.BASELINE if k == 1 else f"{es.BASELINE}-k{k}"


def words(s):
    return set(re.findall(r"[a-z0-9_]{3,}", s.lower()))


def kept(url):
    return [f for f in json.loads((ROOT / "out" / f"{PRS[url]['id']}.json").read_text())["findings"] if f["verdict"] != "reject"]


def simulate(judge):
    """{k: {url: (tp, fp, fn)}} from the baseline judge results: each judged candidate is traced to its finding by word overlap."""
    out = {k: {} for k in KS}
    for url, tools in es.evaluations(judge).items():
        r = tools[es.BASELINE]
        fs = [(len(f["seats"]), words(f["claim"] + " " + (f.get("evidence") or "") + " " + (f.get("path") or ""))) for f in kept(url)]

        def seats(text):
            w = words(text)
            return max(fs, key=lambda f: len(w & f[1]) / (len(w) or 1))[0]

        tps = [seats(t.get("matched_candidate") or "") for t in r["true_positives"] if t["category"] in CORE]
        fps = [seats(t["candidate"]) for t in r["false_positives"]]
        golden = len(tps) + sum(t["category"] in CORE for t in r["false_negatives"])
        for k in KS:
            tp = sum(s >= k for s in tps)
            out[k][url] = (tp, sum(s >= k for s in fps), golden - tp)
    return out


def choose(sim, urls):
    scores = {k: es.pooled(sim[k][u] for u in urls) for k in KS}
    ok = [k for k in KS if scores[k]["r"] >= RECALL_FLOOR] or [1]
    return max(ok, key=lambda k: (scores[k]["f1"], -k)), scores


def cmd_select(_):
    sim = simulate("opus")
    urls = list(sim[1])
    assert sim[1] == es.load_counts("opus", es.BASELINE), "k=1 must reproduce the baseline counts"
    folds = {}
    for repo in es.REPOS:
        k, scores = choose(sim, [u for u in urls if es.repo_of(u) != repo])
        folds[repo] = {"k": k, "train": {str(j): {m: round(v, 1) for m, v in s.items()} for j, s in scores.items()}}
        print(f"held out {repo:9}: k={k}  " + "  ".join(f"k{j} F1 {s['f1']:.1f} R {s['r']:.1f}" for j, s in scores.items()))
    k_all, _ = choose(sim, urls)
    (HERE / "selection.json").write_text(json.dumps({"folds": folds, "in_sample_k": k_all}, indent=1) + "\n")
    need = sorted({f["k"] for f in folds.values()} | {k_all} - {1})
    print(f"in-sample choice on all 50 PRs: k={k_all}\nvariants to judge: {[tool(k) for k in need if k != 1]}")


def fmt(m):
    return f"P {m['p']:.1f} R {m['r']:.1f} F1 {m['f1']:.1f} F2 {m['f2']:.1f}"


def cmd_report(_):
    sel = json.loads((HERE / "selection.json").read_text())
    kfold = {r: f["k"] for r, f in sel["folds"].items()}
    res, counts = {"selection": kfold, "in_sample_k": sel["in_sample_k"]}, {}
    n_findings = sum(sum(len(f["seats"]) >= kfold[es.repo_of(u)] for f in kept(u)) for u in PRS) / len(PRS)
    res["findings_per_pr"] = {"baseline": sum(len(kept(u)) for u in PRS) / len(PRS), "oof": n_findings}
    for judge in es.JUDGES:
        base = es.load_counts(judge, es.BASELINE)
        variants = {k: es.load_counts(judge, tool(k)) for k in set(kfold.values()) | {sel["in_sample_k"]}}
        oof = {u: variants[kfold[es.repo_of(u)]][u] for u in base}
        ins = variants[sel["in_sample_k"]]
        sim = simulate(judge)[sel["in_sample_k"]]
        counts[judge] = {"baseline": base, "oof": oof, "in_sample": ins}
        r = res[judge] = {"baseline": es.pooled(base.values()), "oof": es.pooled(oof.values()),
                          "in_sample": es.pooled(ins.values()), "in_sample_simulated": es.pooled(sim.values())}
        r["vs_baseline"] = {**es.paired_bootstrap(oof, base), "randomisation_p": es.randomisation(oof, base)}
        r["per_repo_delta"] = {repo: es.pooled(oof[u] for u in oof if es.repo_of(u) == repo)["f1"]
                               - es.pooled(base[u] for u in base if es.repo_of(u) == repo)["f1"] for repo in es.REPOS}
        r["competitors"] = {}
        for c in COMPETITORS:
            cc = es.load_counts(judge, c)
            counts[judge][c] = cc
            r["competitors"][c] = {"score": es.pooled(cc.values()), **es.paired_bootstrap(oof, cc),
                                   "randomisation_p": es.randomisation(oof, cc)}
        for c, p in es.holm({c: v["p"] for c, v in r["competitors"].items()}).items():
            r["competitors"][c]["p_holm"] = p
        print(f"\n== {judge} judge, Core profile")
        print(f"baseline             {fmt(r['baseline'])}")
        print(f"out-of-fold          {fmt(r['oof'])}")
        print(f"in-sample k={sel['in_sample_k']}       {fmt(r['in_sample'])}   (simulated: {fmt(r['in_sample_simulated'])})")
        v = r["vs_baseline"]
        print(f"out-of-fold vs baseline: dF1 {v['delta']:+.1f}  95% CI {v['lo']:+.1f} to {v['hi']:+.1f}  p {v['p']:.4f}  randomisation p {v['randomisation_p']:.4f}")
        print("per-repo dF1: " + "  ".join(f"{k} {d:+.1f}" for k, d in r["per_repo_delta"].items()))
        for c, v in r["competitors"].items():
            print(f"vs {c:17} {fmt(v['score'])} | dF1 {v['delta']:+.1f}  CI {v['lo']:+.1f} to {v['hi']:+.1f}  p {v['p']:.4f}  Holm {v['p_holm']:.4f}  rand {v['randomisation_p']:.4f}")
    o, s = res["opus"], res["sonnet"]
    res["acceptance"] = {
        "1 CI lower bound above 0 (Opus)": o["vs_baseline"]["lo"] > 0,
        "2 dF1 above 0 (Sonnet)": s["vs_baseline"]["delta"] > 0,
        "3 dF1 at least 0 in 4 of 5 repos (Opus)": sum(d >= 0 for d in o["per_repo_delta"].values()) >= 4,
        f"4 recall at least {RECALL_FLOOR:.0f} (Opus)": o["oof"]["r"] >= RECALL_FLOOR,
        "5 cost per PR does not rise": True,
        f"minimum effect: dF1 at least {MIN_EFFECT:.0f} (Opus)": o["vs_baseline"]["delta"] >= MIN_EFFECT,
    }
    print("\nacceptance:")
    for k, v in res["acceptance"].items():
        print(f"  {'pass' if v else 'FAIL'}  {k}")
    print(f"findings per PR: baseline {res['findings_per_pr']['baseline']:.1f}, out-of-fold {n_findings:.1f}")
    (HERE / "results.json").write_text(json.dumps(res, indent=1) + "\n")
    (HERE / "counts.json").write_text(json.dumps(counts) + "\n")
    snap = ROOT / "results"
    snap.mkdir(exist_ok=True)
    for judge, name in es.JUDGES.items():
        doc = {}
        for part in ("candidates", "evaluations"):
            data = json.loads((es.RESULTS / name / f"{part}.json").read_text())
            doc[part] = {u: {t: v for t, v in tools.items() if t.startswith(es.BASELINE)} for u, tools in data.items()}
        (snap / f"{judge}.json").write_text(json.dumps(doc) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(required=True)
    sub.add_parser("select", help="choose k per held-out repo from the simulation; costs nothing").set_defaults(fn=cmd_select)
    sub.add_parser("report", help="score the judged variants and test them").set_defaults(fn=cmd_report)
    args = ap.parse_args()
    args.fn(args)
