#!/usr/bin/env python3
"""chart.py <results.json> <theme|fixed> > chart.html"""
import json
import sys
from html import escape

ROWS = (("converge-review", "converge-review"), ("coderabbit", "CodeRabbit"), ("augment", "Augment"),
        ("claude-code", "Claude Code"), ("cubic-v2", "Cubic v2"), ("qodo-extended-v2", "Qodo Extended v2"),
        ("golden", "Benchmark's own labels"))
VARS = {"theme": "--ink:var(--foreground);--ink2:var(--muted-foreground);--hl:var(--destructive);"
                 "--s1:var(--chart-1);--s2:color-mix(in srgb,var(--chart-1) 42%,transparent);",
        "fixed": "--ink:#f0efec;--ink2:#a9a8a0;--hl:#e66767;--s1:#3987e5;--s2:#184f95;"}
CSS = """
.v{%s font:13px/1.35 var(--font-sans,system-ui,-apple-system,"Segoe UI",sans-serif);color:var(--ink)}
.v h3{margin:0 0 2px;font-size:15px;font-weight:600}
.v p{margin:0;color:var(--ink2);font-size:12px}
.v section+section{margin-top:28px}
.key{display:flex;gap:16px;margin:8px 0 10px;color:var(--ink2);font-size:12px}
.key i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px}
.rows{display:grid;grid-template-columns:max-content 1fr;column-gap:12px;row-gap:9px;align-items:center}
.rows .n{text-align:right;white-space:nowrap}
.rows .ref{color:var(--ink2)}
.hl{grid-column:1/-1;height:2px;border-radius:1px;background:var(--hl)}
.t{display:flex;align-items:center;gap:2px;min-width:0}
.t b{display:block;height:18px;flex:none}
.t .a{background:var(--s1)}
.t .b{background:var(--s2);border-radius:0 4px 4px 0}
.t span{margin-left:6px;white-space:nowrap;font-variant-numeric:tabular-nums}
.t small{color:var(--ink2);font-size:12px}
@media (max-width:480px){.rows{grid-template-columns:1fr;row-gap:3px}.rows .n{text-align:left;margin-top:6px}}
"""


def panel(title, sub, rows, top, fmt):
    out = [f"<section><h3>{title}</h3><p>{sub}</p>",
           '<div class="key"><span><i style="background:var(--s1)"></i>Above trivial</span>'
           '<span><i style="background:var(--s2)"></i>Trivial</span></div><div class="rows">']
    for name, a, total in rows:
        ref = " ref" if name.startswith("Benchmark") else ""
        tip = f"{name}: {fmt(total)} in all, {fmt(a)} above trivial, {fmt(total - a)} trivial"
        out.append(f'<div class="n{ref}">{escape(name)}</div><div class="t" title="{escape(tip)}">'
                   f'<b class="a" style="width:{68 * a / top:.2f}%"></b>'
                   f'<b class="b" style="width:{68 * (total - a) / top:.2f}%"></b>'
                   f'<span>{fmt(total)} <small>({fmt(a)} above trivial)</small></span></div>'
                   + ('<div class="hl"></div>' if name == "converge-review" else ""))
    return "".join(out) + "</div></section>"


def main(path, mode):
    sc = json.load(open(path))["fable"]["scopes"]
    every, real = sc["all true issues"]["tools"], sc["true and not trivial"]["tools"]
    found = [(n, real[t]["issues_found_per_pr"], every[t]["issues_found_per_pr"]) for t, n in ROWS]
    share = [(n, real[t]["precision"], every[t]["precision"]) for t, n in ROWS]
    pool = every["converge-review"]["issues_in_pool"]
    print(f"<style>{CSS % VARS[mode]}</style><div class=\"v\">"
          + panel("True issues found per pull request",
                  f"Out of {pool} issues confirmed against source over 50 pull requests.",
                  found, max(r[2] for r in found), lambda x: f"{x:.1f}")
          + panel("Share of each tool's comments that are true",
                  "A comment counts as true when the issue it raises was confirmed against source.",
                  share, 100, lambda x: f"{x:.0f}%")
          + '<p style="margin-top:22px">Provisional: every issue was verified by Claude models only. '
          '50 pull requests from the Martian Code Review Bench.</p></div>')


if __name__ == "__main__":
    main(*sys.argv[1:])
