#!/usr/bin/env python3
"""Experiment 005: compare tools on verified truth, not on the golden set.

Pre-registration: docs/experiments/005-pooled-truth.md.

    run.py report      scores, tests, verifier agreement
    run.py sheet       write the blind labelling sheet for the human check
    run.py agreement   compare the filled-in sheet with the verifiers
    run.py sample      write the fixed sample for an outside verifier to validation/sample/
    run.py external D  compare an outside verifier's verify.py output in D with the Claude verifiers
"""
import argparse
import collections
import csv
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
import evalstats as es

POOL = ROOT / "pool"
VERIFIERS = {"fable": ROOT / "verify/pool-fable/ledgers", "opus": ROOT / "verify/pool-opus/ledgers"}
PRIMARY = "fable"
OURS = ("converge-review", "converge-review-replay")
COMPETITORS = ("coderabbit", "claude-code", "cubic-v2", "qodo-extended-v2", "augment")
SCOPES = {"all true issues": lambda v: v["verdict"] == "confirmed",
          "true and not trivial": lambda v: v["verdict"] == "confirmed" and v["impact"] != "trivial"}
PER_TOOL, SEED = 15, 0
SAMPLE, PER_STRATUM = ROOT / "validation/sample", 34


def load(verifier):
    """[(url, items, {issue id: members}, {issue id: verdict})] per PR."""
    out = []
    for p in sorted(POOL.glob("*.json")):
        doc = json.loads(p.read_text())
        led = json.loads((VERIFIERS[verifier] / p.name).read_text())
        out.append((doc["pr_url"], doc["items"], {i["id"]: i["members"] for i in doc["issues"]},
                    {f["issue"]: f["verifier"] for f in led["findings"]}))
    return out


def counts(prs, tool, keep):
    """Per PR: precision counts over the tool's comments, recall counts over the pool's kept issues."""
    prec, rec = {}, {}
    for url, items, issues, verdicts in prs:
        mine = {it["id"] for it in items if it["source"] == tool}
        good = {i for i in issues if keep(verdicts[i])}
        owner = {m: i for i, ms in issues.items() for m in ms}
        hit = sum(owner[c] in good for c in mine)
        found = sum(bool(mine & set(issues[i])) for i in good)
        prec[url], rec[url] = (hit, len(mine) - hit, 0), (found, 0, len(good) - found)
    return prec, rec


def kappa(a, b):
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((sum(x == v for x in a) / n) * (sum(y == v for y in b) / n) for v in (True, False))
    return po, (po - pe) / (1 - pe) if pe < 1 else 1.0


def cmd_report(_):
    res = {}
    for verifier in VERIFIERS:
        prs = load(verifier)
        vs = [v for pr in prs for v in pr[3].values()]
        r = res[verifier] = {"issues": len(vs), "verdicts": collections.Counter(v["verdict"] for v in vs),
                             "impact_of_confirmed": collections.Counter(v["impact"] for v in vs if v["verdict"] == "confirmed"),
                             "cost_usd": sum(v["cost_usd"] for v in vs), "scopes": {}}
        print(f"\n===== verifier {verifier}: {r['issues']} issues, {dict(r['verdicts'])}, confirmed impact {dict(r['impact_of_confirmed'])}, cost {r['cost_usd']:.2f}")
        for scope, keep in SCOPES.items():
            sc = r["scopes"][scope] = {"tools": {}, "tests": {}}
            c = {t: counts(prs, t, keep) for t in OURS + COMPETITORS + ("golden",)}
            print(f"\n-- {scope}")
            for t, (prec, rec) in c.items():
                p, rc = es.pooled(prec.values()), es.pooled(rec.values())
                sc["tools"][t] = {"comments": p["tp"] + p["fp"], "true_comments": p["tp"], "precision": p["p"],
                                  "issues_found": rc["tp"], "issues_in_pool": rc["tp"] + rc["fn"], "recall": rc["r"],
                                  "issues_found_per_pr": rc["tp"] / len(prs)}
                d = sc["tools"][t]
                print(f"  {t:24} comments {d['comments']:4}  true {d['precision']:5.1f}%  issues found {d['issues_found']:4} of {d['issues_in_pool']} ({d['recall']:4.1f}%)  per PR {d['issues_found_per_pr']:.1f}")
            for ours in OURS:
                for metric, idx, label in (("p", 0, "precision"), ("r", 1, "recall")):
                    tests = {comp: es.paired_bootstrap(c[ours][idx], c[comp][idx], metric=metric) for comp in COMPETITORS}
                    for comp, ph in es.holm({k: v["p"] for k, v in tests.items()}).items():
                        tests[comp]["p_holm"] = ph
                    sc["tests"][f"{ours}/{label}"] = tests
                    print(f"  {ours} {label} minus: " + "  ".join(f"{comp} {v['delta']:+.1f} [{v['lo']:+.1f},{v['hi']:+.1f}] Holm {v['p_holm']:.3f}" for comp, v in tests.items()))
    a, b = load("fable"), load("opus")
    pairs = [(va[i]["verdict"] == "confirmed", vb[i]["verdict"] == "confirmed", {it["source"] for it in items if it["id"] in ms[i]})
             for (_, items, ms, va), (_, _, _, vb) in zip(a, b) for i in ms]
    res["agreement"] = {"all": kappa([x for x, _, _ in pairs], [y for _, y, _ in pairs])}
    for t in OURS + COMPETITORS + ("golden",):
        sub = [(x, y) for x, y, src in pairs if t in src]
        res["agreement"][t] = kappa([x for x, _ in sub], [y for _, y in sub])
    print("\nverifier agreement on confirmed or not (share agreeing, kappa):")
    for k, (po, kp) in res["agreement"].items():
        print(f"  {k:24} {100 * po:5.1f}%  kappa {kp:.2f}")
    (HERE / "results.json").write_text(json.dumps(res, indent=1) + "\n")


def cmd_sheet(_):
    prs, rng, rows, key, used = load(PRIMARY), random.Random(SEED), [], {}, set()
    for tool in ("converge-review",) + COMPETITORS:
        mine = [(url, i, v[i]["verdict"] == "confirmed") for url, items, ms, v in prs for i in ms
                if (url, i) not in used and any(it["source"] == tool and it["id"] in ms[i] for it in items)]
        rng.shuffle(mine)
        rest = [m for m in mine if not m[2]][:5]
        pick = rest + [m for m in mine if m[2]][:PER_TOOL - len(rest)]
        used |= {(u, i) for u, i, _ in pick}
        rows += [(u, i, tool) for u, i, _ in pick]
    rng.shuffle(rows)
    led = {p.name: json.loads(p.read_text()) for p in VERIFIERS[PRIMARY].glob("*.json")}
    pid = {v["pr_url"]: p.name for p in POOL.glob("*.json") for v in [json.loads(p.read_text())]}
    with open(HERE / "labels.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "pull_request", "path", "claim", "true_or_false", "impact", "notes"])
        for n, (url, i, tool) in enumerate(rows, 1):
            f_ = next(x for x in led[pid[url]]["findings"] if x["issue"] == i)
            w.writerow([f"L{n:02}", url, f_["path"] or "", f_["claim"], "", "", ""])
            key[f"L{n:02}"] = {"pr_url": url, "issue": i, "sampled_for": tool}
    (HERE / "labels.key.json").write_text(json.dumps(key, indent=1) + "\n")
    print(f"wrote {len(rows)} rows to {HERE / 'labels.csv'}; do not open labels.key.json before labelling")


def cmd_agreement(_):
    key = json.loads((HERE / "labels.key.json").read_text())
    human = {r["id"]: r["true_or_false"].strip().lower() for r in csv.DictReader(open(HERE / "labels.csv"))}
    human = {k: v.startswith("t") for k, v in human.items() if v[:1] in ("t", "f")}
    print(f"{len(human)} of {len(key)} rows labelled true or false")
    for verifier in VERIFIERS:
        verdict = {(u, i): v[i]["verdict"] == "confirmed" for u, _, ms, v in load(verifier) for i in ms}
        rows = [(human[k], verdict[(d["pr_url"], d["issue"])], d["sampled_for"]) for k, d in key.items() if k in human]
        print(f"\nverifier {verifier}: agreement with the human, all rows {100 * sum(h == v for h, v, _ in rows) / len(rows):.0f}%")
        for tool in ("converge-review",) + COMPETITORS:
            sub = [(h, v) for h, v, t in rows if t == tool]
            conf = [h for h, v in sub if v]
            if sub:
                print(f"  {tool:18} agreement {100 * sum(h == v for h, v in sub) / len(sub):3.0f}% of {len(sub)};"
                      f" of {len(conf)} the verifier confirmed, the human says true for {sum(conf)}")


def cmd_sample(_):
    rng, rows, index, chosen = random.Random(SEED), [], {}, collections.defaultdict(set)
    for p in sorted(POOL.glob("*.json")):
        doc = json.loads(p.read_text())
        src = {it["id"]: it["source"] for it in doc["items"]}
        rows += [(p.stem, i["id"], {src[m] for m in i["members"]}) for i in doc["issues"]]
    for tool in ("converge-review",) + COMPETITORS:
        index[tool] = sorted(rng.sample([(pid, i) for pid, i, s in rows if tool in s], PER_STRATUM))
        for pid, i in index[tool]:
            chosen[pid].add(i)
    SAMPLE.mkdir(parents=True, exist_ok=True)
    for pid, ids in chosen.items():
        led = json.loads((POOL / "ledgers" / f"{pid}.json").read_text())
        led["findings"] = [f for f in led["findings"] if f["issue"] in ids]
        (SAMPLE / f"{pid}.json").write_text(json.dumps(led, indent=1) + "\n")
    (SAMPLE.parent / "index.json").write_text(json.dumps(index, indent=1) + "\n")
    print(f"{sum(map(len, chosen.values()))} issues over {len(chosen)} PRs, {PER_STRATUM} drawn per tool")


def verdicts(ledgers):
    return {(p.stem, f["issue"]): f["verifier"]["verdict"] == "confirmed"
            for p in Path(ledgers).glob("*.json") for f in json.loads(p.read_text())["findings"] if "verifier" in f}


def cmd_external(args):
    index = {t: [tuple(k) for k in ks] for t, ks in json.loads((SAMPLE.parent / "index.json").read_text()).items()}
    ext, ref = verdicts(Path(args.dir) / "ledgers"), {n: verdicts(d) for n, d in VERIFIERS.items()}
    keys = sorted({k for ks in index.values() for k in ks} & set(ext))
    print(f"{len(keys)} of {len({k for ks in index.values() for k in ks})} sampled issues have an outside verdict")
    if not keys:
        return
    res = {"agreement": {}, "confirmed_share": {}}
    for n, r in ref.items():
        po, kp = kappa([ext[k] for k in keys], [r[k] for k in keys])
        res["agreement"][n] = {"share": po, "kappa": kp}
        print(f"outside verifier against {n}: agree on {100 * po:.1f}%, kappa {kp:.2f}")
    print("share of each tool's sampled issues confirmed, by verifier:")
    for tool, ks in index.items():
        ks = [k for k in ks if k in ext]
        if ks:
            row = {"n": len(ks), "outside": sum(ext[k] for k in ks) / len(ks),
                   **{n: sum(r[k] for k in ks) / len(ks) for n, r in ref.items()}}
            res["confirmed_share"][tool] = row
            print(f"  {tool:18} n={len(ks):2}  " + "  ".join(f"{n} {100 * v:5.1f}%" for n, v in row.items() if n != "n"))
    (Path(args.dir) / "comparison.json").write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(required=True)
    for name, fn in (("report", cmd_report), ("sheet", cmd_sheet), ("agreement", cmd_agreement), ("sample", cmd_sample)):
        sub.add_parser(name).set_defaults(fn=fn)
    ext = sub.add_parser("external")
    ext.add_argument("dir")
    ext.set_defaults(fn=cmd_external)
    args = ap.parse_args()
    args.fn(args)
