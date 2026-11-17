#!/usr/bin/env python3
"""Per-PR counts from the benchmark's judge results, pooled metrics and paired tests. See docs/methodology.md."""
import importlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OFFLINE = ROOT / "vendor/code-review-benchmark/offline"
RESULTS = OFFLINE / "results"
sys.path.insert(0, str(OFFLINE / "analysis"))
bd = importlib.import_module("benchmark_dashboard")

JUDGES = {"opus": "anthropic_claude-opus-4-5-20251101", "sonnet": "anthropic_claude-sonnet-4-5-20250929"}
REPOS = ("discourse", "sentry", "keycloak", "grafana", "cal.com")
BASELINE = "converge-review"


def repo_of(url):
    return next(r for r in REPOS if r in url)


def evaluations(judge):
    return json.loads((RESULTS / JUDGES[judge] / "evaluations.json").read_text())


def load_counts(judge, tool, profile="core"):
    """{pr_url: (tp, fp, fn)} with the benchmark's own profile filter. A PR the tool has no result for misses every golden comment."""
    cats = bd._load_golden_categories(RESULTS)
    out = {}
    for url, tools in evaluations(judge).items():
        ref = bd._compute_profile_metrics(tools[BASELINE], cats)[profile]
        e = tools.get(tool)
        if e and not e.get("skipped"):
            m = bd._compute_profile_metrics(e, cats)[profile]
            if m["tp"] + m["fn"] != ref["tp"] + ref["fn"]:
                raise ValueError(f"{tool} was judged against a different golden set on {url}; it cannot be paired")
            out[url] = (m["tp"], m["fp"], m["fn"])
        else:
            out[url] = (0, 0, ref["tp"] + ref["fn"])
    return out


def pooled(counts):
    counts = list(counts)
    tp, fp, fn = (sum(c[i] for c in counts) for i in range(3))
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"p": 100 * p, "r": 100 * r, "f1": 200 * p * r / (p + r) if p + r else 0.0,
            "f2": 500 * p * r / (4 * p + r) if p + r else 0.0, "tp": tp, "fp": fp, "fn": fn}


def paired_bootstrap(a, b, n=10000, seed=0, metric="f1"):
    """Repo-stratified PR resampling of metric(a) - metric(b). Returns the delta, its 95% CI and a one-sided p."""
    rng = random.Random(seed)
    strata = {}
    for u in a:
        strata.setdefault(repo_of(u), []).append(u)
    deltas = []
    for _ in range(n):
        s = [u for us in strata.values() for u in rng.choices(us, k=len(us))]
        deltas.append(pooled(a[u] for u in s)[metric] - pooled(b[u] for u in s)[metric])
    deltas.sort()
    return {"delta": pooled(a.values())[metric] - pooled(b[u] for u in a)[metric],
            "lo": deltas[int(0.025 * n)], "hi": deltas[int(0.975 * n) - 1],
            "p": (sum(d <= 0 for d in deltas) + 1) / (n + 1)}


def randomisation(a, b, n=10000, seed=0, metric="f1"):
    """Paired approximate randomisation, two-sided."""
    rng = random.Random(seed)
    urls = list(a)
    obs = abs(pooled(a[u] for u in urls)[metric] - pooled(b[u] for u in urls)[metric])
    hits = 0
    for _ in range(n):
        swap = [rng.random() < 0.5 for _ in urls]
        x = pooled((b if s else a)[u] for u, s in zip(urls, swap))[metric]
        y = pooled((a if s else b)[u] for u, s in zip(urls, swap))[metric]
        hits += abs(x - y) >= obs
    return (hits + 1) / (n + 1)


def holm(pvals):
    out, running = {}, 0.0
    for i, (k, p) in enumerate(sorted(pvals.items(), key=lambda kv: kv[1])):
        running = max(running, min(1.0, (len(pvals) - i) * p))
        out[k] = running
    return out


def select_folds(counts, default, recall_floor):
    """Leave one repo out. counts: {arm: {url: counts}}. Per fold, the arm with the best pooled F1 on the other
    repos among those at or above the recall floor; a tie keeps the default. Returns {repo: arm}."""
    folds = {}
    for repo in REPOS:
        scores = {a: pooled(c[u] for u in c if repo_of(u) != repo) for a, c in counts.items()}
        ok = [a for a in counts if scores[a]["r"] >= recall_floor] or [default]
        folds[repo] = max(ok, key=lambda a: (scores[a]["f1"], a == default))
        print(f"held out {repo:9}: {folds[repo]:9} " + "  ".join(f"{a} F1 {s['f1']:.1f} R {s['r']:.1f}" for a, s in scores.items()))
    return folds


def fmt(m):
    return f"P {m['p']:.1f} R {m['r']:.1f} F1 {m['f1']:.1f} F2 {m['f2']:.1f}"


def compare(oof, base, competitors, recall_floor, min_effect):
    """oof, base: {judge: {url: counts}}. Scores, paired tests and the acceptance checks of docs/methodology.md."""
    res = {}
    for judge in JUDGES:
        o, b = oof[judge], base[judge]
        r = res[judge] = {"baseline": pooled(b.values()), "oof": pooled(o.values()),
                          "vs_baseline": {**paired_bootstrap(o, b), "randomisation_p": randomisation(o, b)},
                          "per_repo_delta": {repo: pooled(o[u] for u in o if repo_of(u) == repo)["f1"]
                                             - pooled(b[u] for u in b if repo_of(u) == repo)["f1"] for repo in REPOS},
                          "competitors": {}}
        for c in competitors:
            cc = load_counts(judge, c)
            r["competitors"][c] = {"score": pooled(cc.values()), **paired_bootstrap(o, cc),
                                   "randomisation_p": randomisation(o, cc)}
        for c, p in holm({c: v["p"] for c, v in r["competitors"].items()}).items():
            r["competitors"][c]["p_holm"] = p
        v = r["vs_baseline"]
        print(f"\n== {judge} judge, Core profile\nbaseline     {fmt(r['baseline'])}\nout-of-fold  {fmt(r['oof'])}")
        print(f"out-of-fold vs baseline: dF1 {v['delta']:+.1f}  95% CI {v['lo']:+.1f} to {v['hi']:+.1f}  p {v['p']:.4f}  randomisation p {v['randomisation_p']:.4f}")
        print("per-repo dF1: " + "  ".join(f"{k} {d:+.1f}" for k, d in r["per_repo_delta"].items()))
        for c, v in r["competitors"].items():
            print(f"vs {c:17} {fmt(v['score'])} | dF1 {v['delta']:+.1f}  CI {v['lo']:+.1f} to {v['hi']:+.1f}  p {v['p']:.4f}  Holm {v['p_holm']:.4f}  rand {v['randomisation_p']:.4f}")
    o, s = res["opus"], res["sonnet"]
    res["acceptance"] = {
        "1 CI lower bound above 0 (Opus)": o["vs_baseline"]["lo"] > 0,
        "2 dF1 above 0 (Sonnet)": s["vs_baseline"]["delta"] > 0,
        "3 dF1 at least 0 in 4 of 5 repos (Opus)": sum(d >= 0 for d in o["per_repo_delta"].values()) >= 4,
        f"4 recall at least {recall_floor:.0f} (Opus)": o["oof"]["r"] >= recall_floor,
        f"minimum effect: dF1 at least {min_effect:.0f} (Opus)": o["vs_baseline"]["delta"] >= min_effect,
    }
    print("\nacceptance:" + "".join(f"\n  {'pass' if v else 'FAIL'}  {k}" for k, v in res["acceptance"].items()))
    return res


def snapshot():
    """Copy our tools' candidates and evaluations out of the vendored benchmark into results/."""
    (ROOT / "results").mkdir(exist_ok=True)
    for judge, name in JUDGES.items():
        doc = {}
        for part in ("candidates", "evaluations"):
            data = json.loads((RESULTS / name / f"{part}.json").read_text())
            doc[part] = {u: {t: v for t, v in tools.items() if t.startswith(BASELINE)} for u, tools in data.items()}
        (ROOT / "results" / f"{judge}.json").write_text(json.dumps(doc) + "\n")


if __name__ == "__main__":
    for judge, name in JUDGES.items():
        mine = pooled(load_counts(judge, BASELINE).values())
        theirs = bd.load_all_models(RESULTS)[name]["overall_metrics"][BASELINE]["core"]
        for k, kk in (("p", "precision"), ("r", "recall"), ("f1", "f1"), ("f2", "f2")):
            assert round(mine[k], 1) == theirs[kk], (judge, k, mine[k], theirs[kk])
        print(f"{judge}: baseline P {mine['p']:.1f} R {mine['r']:.1f} F1 {mine['f1']:.1f} F2 {mine['f2']:.1f}, matches the dashboard")
    assert holm({"a": 0.01, "b": 0.04, "c": 0.03}) == {"a": 0.03, "c": 0.06, "b": 0.06}
