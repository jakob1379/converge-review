import re
import sys
from pathlib import Path

OUT = Path(sys.argv[1])

SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"

THEMES = {
    "light": dict(
        bg0="#ffffff", bg1="#eef4fc", card="#f6f8fa", cardline="#d0d7de", grid="#d8dee4",
        ink="#1f2328", ink2="#59636e", ink3="#818b98", edge="#c4cbd3",
        blue="#2a78d6", blue2="#9cc2ee", violet="#6250d6", red="#cf222e", green="#1a7f37",
        ref="#8c959f", ref2="#d0d7de", glow="#2a78d6", dots="#c9d3de",
    ),
    "dark": dict(
        bg0="#0d1117", bg1="#111c2e", card="#161b22", cardline="#30363d", grid="#262c35",
        ink="#e6edf3", ink2="#9198a1", ink3="#6e7681", edge="#3a424d",
        blue="#3987e5", blue2="#24508a", violet="#9085e9", red="#f85149", green="#3fb950",
        ref="#6e7681", ref2="#3a424d", glow="#58a6ff", dots="#1f2a3a",
    ),
}

REDUCED = "@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; } }"


def fill(tpl, t):
    out = re.sub(r"\{\{(\w+)\}\}", lambda m: t[m.group(1)], tpl)
    assert "{{" not in out
    return out


def hero(t):
    nodes = [
        (600, 62, "open-code-review", "blue", -1),
        (800, 62, "superpowers", "blue", -1),
        (600, 178, "ponytail", "violet", 1),
        (800, 178, "mattpocock", "violet", 1),
    ]
    cx, cy = 700, 120
    paths, comets, dots, labels = [], [], [], []
    for i, (x, y, name, col, side) in enumerate(nodes):
        qx = x + (cx - x) * 0.15
        qy = cy + (y - cy) * 0.1
        d = f"M{x},{y} Q{qx},{qy} {cx},{cy}"
        paths.append(f'<path class="edge" d="{d}" pathLength="100" style="animation-delay:{0.5 + i * 0.12:.2f}s"/>')
        comets.append(
            f'<path class="comet" d="{d}" pathLength="100" stroke="{{{{{col}}}}}" style="animation-delay:{2.0 + i * 0.6:.1f}s"/>'
        )
        dots.append(
            f'<g class="pop" style="animation-delay:{0.2 + i * 0.12:.2f}s"><circle cx="{x}" cy="{y}" r="11" fill="{{{{bg0}}}}" stroke="{{{{{col}}}}}" stroke-width="2"/>'
            f'<circle cx="{x}" cy="{y}" r="4.5" fill="{{{{{col}}}}}"/></g>'
        )
        ly = y - 22 if side < 0 else y + 31
        labels.append(f'<text class="mono fade" x="{x}" y="{ly}" text-anchor="middle" style="animation-delay:{0.5 + i * 0.12:.2f}s">{name}</text>')
    tpl = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 880 240" width="880" height="240" role="img" aria-labelledby="t">
<title id="t">converge-review: four independent reviewers converge on one ranked list</title>
<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{{{{bg0}}}}"/><stop offset="1" stop-color="{{{{bg1}}}}"/></linearGradient>
<radialGradient id="halo" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="{{{{glow}}}}" stop-opacity="0.22"/><stop offset="1" stop-color="{{{{glow}}}}" stop-opacity="0"/></radialGradient>
<pattern id="dots" width="16" height="16" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="{{{{dots}}}}"/></pattern>
<linearGradient id="fadeR" x1="0" x2="1"><stop offset="0.35" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#fff" stop-opacity="1"/></linearGradient>
<mask id="m"><rect width="880" height="240" fill="url(#fadeR)"/></mask>
<filter id="soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.2"/></filter>
</defs>
<style>
text {{ font-family: {SANS}; }}
.mono {{ font-family: {MONO}; font-size: 11.5px; fill: {{{{ink2}}}}; }}
.edge {{ fill: none; stroke: {{{{edge}}}}; stroke-width: 1.5; stroke-dasharray: 100; stroke-dashoffset: 0; animation: draw 1.1s cubic-bezier(.2,.7,.2,1) both; }}
.comet {{ fill: none; stroke-width: 3; stroke-linecap: round; stroke-dasharray: 16 200; stroke-dashoffset: -100; opacity: 0; animation: travel 2.4s cubic-bezier(.45,0,.25,1) infinite; }}
.pop {{ transform-box: fill-box; transform-origin: center; animation: pop .7s cubic-bezier(.2,1.4,.4,1) both; }}
.fade {{ animation: fade .9s ease-out both; }}
.rise {{ animation: rise .9s cubic-bezier(.2,.7,.2,1) both; }}
.orbit {{ transform-box: fill-box; transform-origin: center; animation: spin 60s linear infinite; }}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}
.ring {{ transform-box: fill-box; transform-origin: center; opacity: 0; animation: ring 2.4s ease-out 2.9s infinite; }}
@keyframes draw {{ from {{ stroke-dashoffset: 100; }} to {{ stroke-dashoffset: 0; }} }}
@keyframes travel {{ 0% {{ stroke-dashoffset: 10; opacity: 0; }} 8% {{ opacity: 1; }} 42% {{ stroke-dashoffset: -96; opacity: 1; }} 50%, 100% {{ stroke-dashoffset: -100; opacity: 0; }} }}
@keyframes pop {{ from {{ opacity: 0; transform: scale(.4); }} to {{ opacity: 1; transform: scale(1); }} }}
@keyframes fade {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
@keyframes rise {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: none; }} }}
@keyframes ring {{ 0% {{ opacity: .55; transform: scale(1); }} 70%, 100% {{ opacity: 0; transform: scale(2.1); }} }}
{REDUCED}
</style>
<rect width="880" height="240" rx="18" fill="url(#bg)"/>
<rect width="880" height="240" rx="18" fill="url(#dots)" mask="url(#m)"/>
<rect x="0.5" y="0.5" width="879" height="239" rx="17.5" fill="none" stroke="{{{{cardline}}}}"/>
<circle cx="{cx}" cy="{cy}" r="90" fill="url(#halo)"/>
<circle class="orbit" cx="{cx}" cy="{cy}" r="36" fill="none" stroke="{{{{edge}}}}" stroke-width="1" stroke-dasharray="2 6"/>
<g class="rise"><text x="44" y="104" font-size="46" font-weight="700" letter-spacing="-1.2" fill="{{{{ink}}}}">converge-review</text></g>
<g class="rise" style="animation-delay:.15s">
<text x="46" y="140" font-size="17" fill="{{{{ink2}}}}">Four blind reviewers. One list, ranked by agreement.</text>
<text x="46" y="164" font-size="17" fill="{{{{ink2}}}}">Fixes behind red tests, re-reviewed until clean.</text>
</g>
<g class="rise" style="animation-delay:.3s">
<rect x="46" y="184" width="150" height="28" rx="14" fill="{{{{card}}}}" stroke="{{{{cardline}}}}"/>
<text x="121" y="203" text-anchor="middle" style="font-family:{MONO}" font-size="13" fill="{{{{ink}}}}">/converge-review</text>
<text x="212" y="203" font-size="13" fill="{{{{ink3}}}}">a Claude Code skill</text>
</g>
{"".join(paths)}
<g filter="url(#soft)" opacity=".9">{"".join(comets)}</g>
{"".join(comets)}
{"".join(dots)}
{"".join(labels)}
<circle class="ring" cx="{cx}" cy="{cy}" r="15" fill="none" stroke="{{{{blue}}}}" stroke-width="1.5"/>
<g class="pop" style="animation-delay:.9s">
<circle cx="{cx}" cy="{cy}" r="15" fill="{{{{blue}}}}"/>
<path d="M{cx - 6},{cy} l4,4.5 l8,-9" fill="none" stroke="{{{{bg0}}}}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
</g>
</svg>
'''
    return fill(tpl, t)


def flow(t):
    seats = [("open-code-review", "blue"), ("superpowers", "blue"), ("ponytail", "violet"), ("mattpocock", "violet")]
    T = 16.0
    sy = [74, 120, 166, 212]

    def comet(d, delay, cls="comet"):
        return f'<path class="{cls}" d="{d}" pathLength="100" style="animation-delay:{delay:.1f}s"/>'

    def glow(x, y, w, h, delay, rx=10):
        return f'<rect class="glow" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" style="animation-delay:{delay:.1f}s"/>'

    edges, comets, glows, seat_svg = [], [], [], []
    for i, (name, col) in enumerate(seats):
        c = sy[i] + 17
        out = f"M116,160 C140,160 136,{c} 160,{c}"
        inn = f"M330,{c} C356,{c} 352,160 378,160"
        edges += [out, inn]
        comets += [comet(out, 0.0), comet(inn, 2.4)]
        glows.append(glow(160, sy[i], 170, 34, 1.2 + i * 0.1, rx=17))
        seat_svg.append(
            f'<rect x="160" y="{sy[i]}" width="170" height="34" rx="17" fill="{{{{card}}}}" stroke="{{{{cardline}}}}"/>'
            f'<circle cx="179" cy="{sy[i] + 17}" r="4.5" fill="{{{{{col}}}}}"/>'
            f'<text class="mono" x="192" y="{sy[i] + 21.5}">{name}</text>'
        )
    straight = {
        "mf": "M538,160 L578,160",
        "fr": "M706,160 L746,160",
        "rc": "M856,160 L890,160",
    }
    loop = "M801,202 C801,268 642,268 642,206"
    edges += list(straight.values())
    comets += [
        comet(straight["mf"], 4.8),
        comet(straight["fr"], 7.2),
        comet(loop, 9.6, "comet red"),
        comet(straight["fr"], 12.0),
        comet(straight["rc"], 14.4),
    ]
    glows += [
        glow(378, 104, 160, 112, 3.6),
        glow(578, 118, 128, 84, 6.0),
        glow(746, 118, 110, 84, 8.4),
        glow(578, 118, 128, 84, 10.8),
        glow(746, 118, 110, 84, 13.2),
        f'<circle class="glow" cx="916" cy="160" r="24" style="animation-delay:15.0s"/>',
    ]
    caps = [(70, "PATCH"), (245, "4 SEATS, BLIND"), (458, "MERGE"), (642, "FIX"), (801, "RE-REVIEW"), (916, "CONVERGED")]
    cap_svg = "".join(f'<text class="cap" x="{x}" y="40" text-anchor="middle">{s}</text>' for x, s in caps)
    edge_svg = "".join(f'<path class="edge" d="{d}"/>' for d in edges)
    tpl = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 320" width="960" height="320" role="img" aria-labelledby="t">
<title id="t">The converge-review loop: patch, four blind seats, merge and rank by agreement, fix behind red tests, scoped re-review, converged</title>
<defs>
<marker id="arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,1 L8,5 L0,9" fill="none" stroke="{{{{ink3}}}}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></marker>
<filter id="soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.4"/></filter>
</defs>
<style>
text {{ font-family: {SANS}; fill: {{{{ink}}}}; }}
.mono {{ font-family: {MONO}; font-size: 12.5px; }}
.cap {{ font-size: 11px; font-weight: 600; letter-spacing: 1.4px; fill: {{{{ink3}}}}; }}
.sub {{ font-size: 12.5px; fill: {{{{ink2}}}}; }}
.edge {{ fill: none; stroke: {{{{edge}}}}; stroke-width: 1.5; }}
.comet {{ fill: none; stroke: {{{{glow}}}}; stroke-width: 3; stroke-linecap: round; stroke-dasharray: 12 200; stroke-dashoffset: -100; opacity: 0; animation: travel {T}s linear infinite; }}
.comet.red {{ stroke: {{{{red}}}}; }}
.glow {{ fill: {{{{glow}}}}; fill-opacity: .07; stroke: {{{{glow}}}}; stroke-width: 1.5; opacity: 0; animation: glow {T}s ease-in-out infinite; }}
.fail {{ opacity: 0; animation: fail {T}s step-end infinite; }}
@keyframes travel {{ 0% {{ stroke-dashoffset: 12; opacity: 0; }} 1% {{ opacity: 1; }} 7% {{ stroke-dashoffset: -98; opacity: 1; }} 7.6%, 100% {{ stroke-dashoffset: -100; opacity: 0; }} }}
@keyframes glow {{ 0% {{ opacity: 0; }} 2.5%, 8% {{ opacity: 1; }} 13%, 100% {{ opacity: 0; }} }}
@keyframes fail {{ 0% {{ opacity: 1; }} 7% {{ opacity: 0; }} }}
{REDUCED}
</style>
{cap_svg}
{edge_svg}
<path class="edge" d="{loop}" marker-end="url(#arrow)"/>
<text class="sub" x="721" y="290" text-anchor="middle">not clean: another fix round, at most three</text>
<rect x="24" y="128" width="92" height="64" rx="10" fill="{{{{card}}}}" stroke="{{{{cardline}}}}"/>
<path d="M50,146 h16 l6,6 v20 h-22 z M66,146 v6 h6" fill="none" stroke="{{{{ink3}}}}" stroke-width="1.4" stroke-linejoin="round"/>
<path d="M54,158 h12 M54,163 h9 M54,168 h12" stroke="{{{{ink3}}}}" stroke-width="1.4" stroke-linecap="round"/>
<text class="sub" x="70" y="214" text-anchor="middle">pinned once</text>
{"".join(seat_svg)}
<circle cx="174" cy="266" r="4" fill="{{{{blue}}}}"/><text class="sub" x="183" y="270">correctness</text>
<circle cx="268" cy="266" r="4" fill="{{{{violet}}}}"/><text class="sub" x="277" y="270">advisory</text>
<rect x="378" y="104" width="160" height="112" rx="10" fill="{{{{card}}}}" stroke="{{{{cardline}}}}"/>
<text x="394" y="132" font-size="14" font-weight="600">Rank by agreement</text>
<rect x="394" y="148" width="5" height="20" rx="2" fill="{{{{blue}}}}"/>
<text x="407" y="163" font-size="12.5">3+ seats: main list</text>
<rect x="394" y="180" width="5" height="20" rx="2" fill="{{{{blue2}}}}"/>
<text class="sub" x="407" y="195">1-2 seats: appendix</text>
<rect x="578" y="118" width="128" height="84" rx="10" fill="{{{{card}}}}" stroke="{{{{cardline}}}}"/>
<text x="642" y="146" font-size="15" font-weight="600" text-anchor="middle">Fix</text>
<rect x="594" y="160" width="96" height="26" rx="13" fill="{{{{green}}}}" fill-opacity=".14" stroke="{{{{green}}}}" stroke-opacity=".6"/>
<circle cx="609" cy="173" r="4" fill="{{{{green}}}}"/><text class="mono" x="619" y="177" font-size="11.5" style="font-size:11.5px">test pass</text>
<g class="fail" style="animation-delay:6.0s"><rect x="594" y="160" width="96" height="26" rx="13" fill="{{{{card}}}}"/><rect x="594" y="160" width="96" height="26" rx="13" fill="{{{{red}}}}" fill-opacity=".14" stroke="{{{{red}}}}" stroke-opacity=".6"/>
<circle cx="609" cy="173" r="4" fill="{{{{red}}}}"/><text class="mono" x="619" y="177" style="font-size:11.5px">test red</text></g>
<g class="fail" style="animation-delay:10.8s"><rect x="594" y="160" width="96" height="26" rx="13" fill="{{{{card}}}}"/><rect x="594" y="160" width="96" height="26" rx="13" fill="{{{{red}}}}" fill-opacity=".14" stroke="{{{{red}}}}" stroke-opacity=".6"/>
<circle cx="609" cy="173" r="4" fill="{{{{red}}}}"/><text class="mono" x="619" y="177" style="font-size:11.5px">test red</text></g>
<rect x="746" y="118" width="110" height="84" rx="10" fill="{{{{card}}}}" stroke="{{{{cardline}}}}"/>
<text x="801" y="146" font-size="15" font-weight="600" text-anchor="middle">Re-review</text>
<text class="sub" x="801" y="168" text-anchor="middle">fix diff only,</text>
<text class="sub" x="801" y="186" text-anchor="middle">fresh agents</text>
<circle cx="916" cy="160" r="22" fill="{{{{green}}}}" fill-opacity=".14" stroke="{{{{green}}}}" stroke-width="1.5"/>
<path d="M906,160 l7,7 l12,-14" fill="none" stroke="{{{{green}}}}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
{"".join(glows)}
<g filter="url(#soft)">{"".join(comets)}</g>
{"".join(comets)}
</svg>
'''
    return fill(tpl, t)


ROWS = [
    ("converge-review", 14.8, 8.9, "main"),
    ("CodeRabbit", 4.9, 3.2, ""),
    ("Augment", 3.2, 2.7, ""),
    ("Claude Code", 3.0, 2.4, ""),
    ("Cubic v2", 2.8, 2.3, ""),
    ("Qodo Extended v2", 2.8, 2.5, ""),
    ("Benchmark's own labels", 3.0, 2.3, "ref"),
]


def chart(t):
    x0, unit, bh = 214, 32, 22
    ys = [150, 206, 246, 286, 326, 366, 406]
    rows = []
    for i, ((name, tot, above, kind), y) in enumerate(zip(ROWS, ys)):
        wa, wt = above * unit, (tot - above) * unit
        ca, ct = ("ref", "ref2") if kind == "ref" else ("blue", "blue2")
        name_fill = "ink3" if kind == "ref" else "ink"
        weight = ' font-weight="700"' if kind == "main" else ""
        d = 0.25 + i * 0.12
        rows.append(
            f'<text x="{x0 - 16}" y="{y + 16}" text-anchor="end" font-size="15"{weight} fill="{{{{{name_fill}}}}}">{name}</text>'
            f'<g class="grow" style="animation-delay:{d:.2f}s">'
            f'<rect x="{x0}" y="{y}" width="{wa - 1:.1f}" height="{bh}" rx="4" fill="{{{{{ca}}}}}"/>'
            f'<rect x="{x0 + wa + 1:.1f}" y="{y}" width="{wt - 1:.1f}" height="{bh}" rx="4" fill="{{{{{ct}}}}}"/></g>'
            f'<text class="val" x="{x0 + tot * unit + 12:.1f}" y="{y + 16}" font-size="15" style="animation-delay:{d + 0.7:.2f}s">'
            f'<tspan font-weight="600" fill="{{{{ink}}}}">{tot:.1f}</tspan><tspan dx="6" fill="{{{{ink2}}}}">({above:.1f} above trivial)</tspan></text>'
        )
    ticks = "".join(
        f'<line x1="{x0 + v * unit}" y1="140" x2="{x0 + v * unit}" y2="438" stroke="{{{{grid}}}}" stroke-dasharray="2 4"/>'
        f'<text x="{x0 + v * unit}" y="456" text-anchor="middle" font-size="12" fill="{{{{ink3}}}}">{v}</text>'
        for v in (0, 5, 10, 15)
    )
    tpl = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 880 520" width="880" height="520" role="img" aria-labelledby="t">
<title id="t">True issues found per pull request: converge-review 14.8 (8.9 above trivial); CodeRabbit 4.9 (3.2); Augment 3.2 (2.7); Claude Code 3.0 (2.4); Cubic v2 2.8 (2.3); Qodo Extended v2 2.8 (2.5); benchmark's own labels 3.0 (2.3)</title>
<style>
text {{ font-family: {SANS}; }}
.grow {{ transform-box: fill-box; transform-origin: left center; animation: grow 1.1s cubic-bezier(.16,1,.3,1) both; }}
.rule {{ transform-box: fill-box; transform-origin: left center; animation: grow .9s cubic-bezier(.16,1,.3,1) .5s both; }}
.val {{ animation: fade .6s ease-out both; }}
@keyframes grow {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
@keyframes fade {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
{REDUCED}
</style>
<rect x="0.5" y="0.5" width="879" height="519" rx="16" fill="{{{{card}}}}" stroke="{{{{cardline}}}}"/>
<text x="40" y="58" font-size="22" font-weight="700" fill="{{{{ink}}}}">True issues found per pull request</text>
<text x="40" y="86" font-size="15" fill="{{{{ink2}}}}">Out of 990 issues confirmed against source over 50 pull requests.</text>
<rect x="40" y="106" width="12" height="12" rx="3" fill="{{{{blue}}}}"/><text x="60" y="117" font-size="13.5" fill="{{{{ink2}}}}">Above trivial</text>
<rect x="160" y="106" width="12" height="12" rx="3" fill="{{{{blue2}}}}"/><text x="180" y="117" font-size="13.5" fill="{{{{ink2}}}}">Trivial</text>
{ticks}
<rect class="rule" x="40" y="187" width="800" height="2" rx="1" fill="{{{{red}}}}"/>
{"".join(rows)}
<text x="40" y="494" font-size="13" fill="{{{{ink3}}}}">Provisional: every issue was verified by Claude models only. 50 pull requests from Martian's Code Review Bench.</text>
</svg>
'''
    return fill(tpl, t)


for name, fn in [("hero", hero), ("loop", flow), ("results", chart)]:
    for theme, t in THEMES.items():
        (OUT / f"{name}-{theme}.svg").write_text(fn(t))
