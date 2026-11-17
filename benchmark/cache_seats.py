#!/usr/bin/env python3
"""Copy each seat's final report out of the Claude Code session transcripts into cache/seat-reports/<pr>/<seat>.md.

The transcripts live under ~/.claude/projects and are cleaned up over time; the cache lets a merge-step variant be
replayed on the same reviewer output without paying for new reviews.
"""
import glob
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECTS = os.path.expanduser("~/.claude/projects")
SEATS = {"open-code-review": "open-code-review", "superpowers:requesting": "superpowers",
         "ponytail": "ponytail", "mattpocock": "mattpocock"}


def first_and_last(path):
    first = last = None
    for line in open(path):
        r = json.loads(line)
        c = r.get("message", {}).get("content")
        if r.get("type") == "user" and first is None:
            first = c if isinstance(c, str) else json.dumps(c)
        if r.get("type") == "assistant":
            text = "".join(b.get("text", "") for b in c if b.get("type") == "text")
            handback = [b["input"]["message"] for b in c if b.get("name") == "SubagentHandback"]
            last = "".join(handback) or text or last
    return first or "", last


def main():
    missing = []
    for log in sorted(glob.glob(str(ROOT / "out/*.log.json"))):
        pid = Path(log).name.removesuffix(".log.json")
        sid = json.loads(Path(log).read_text())["session_id"]
        found = {}
        for sub in glob.glob(f"{PROJECTS}/*/{sid}/subagents/*.jsonl"):
            first, last = first_and_last(sub)
            seat = next((name for key, name in SEATS.items() if key in first[:600].lower()), None)
            if seat and last:
                found[seat] = last
        dest = ROOT / "cache/seat-reports" / pid
        dest.mkdir(parents=True, exist_ok=True)
        for seat, text in found.items():
            (dest / f"{seat}.md").write_text(text + "\n")
        missing += [f"{pid}: {s}" for s in SEATS.values() if s not in found]
    print(f"{len(missing)} seat reports missing" + "".join(f"\n  {m}" for m in missing))


if __name__ == "__main__":
    main()
