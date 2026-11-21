import json
import tempfile
import unittest
from pathlib import Path

from bench import TOOL, ingest

URL = "https://github.com/grafana/grafana/pull/1"
PRS = {URL: {"id": "grafana__grafana__1"}}


def data():
    return {URL: {"golden_comments": [], "reviews": [{"tool": "coderabbit", "review_comments": []},
                                                   {"tool": TOOL, "review_comments": [{"body": "stale"}]}]}}


class IngestTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def write(self, findings):
        (self.dir / "grafana__grafana__1.json").write_text(json.dumps({"findings": findings}))

    def test_drops_rejected_and_replaces_previous_run(self):
        self.write([
            {"path": "a.go", "line": 3, "severity": "Critical", "claim": "nil deref", "evidence": "x", "verdict": "fix"},
            {"path": "b.go", "line": None, "severity": "Minor", "claim": "nit", "verdict": "reject"},
        ])
        reviews = ingest(data(), PRS, self.dir)[URL]["reviews"]
        ours = [r for r in reviews if r["tool"] == TOOL]
        self.assertEqual(len(ours), 1)
        self.assertEqual(ours[0]["review_comments"],
                         [{"path": "a.go", "line": 3, "body": "[Critical] nil deref\n\nx"}])
        self.assertIn("coderabbit", [r["tool"] for r in reviews])

    def test_variant_keeps_findings_with_enough_seats_and_leaves_baseline(self):
        self.write([
            {"severity": "Minor", "claim": "solo", "verdict": "fix", "seats": ["a"]},
            {"severity": "Minor", "claim": "agreed", "verdict": "fix", "seats": ["a", "b", "c"]},
        ])
        reviews = ingest(data(), PRS, self.dir, tool="variant", min_seats=3)[URL]["reviews"]
        by_tool = {r["tool"]: [c["body"] for c in r["review_comments"]] for r in reviews}
        self.assertEqual(by_tool["variant"], ["[Minor] agreed"])
        self.assertEqual(by_tool[TOOL], ["stale"])

    def test_claim_only_drops_the_evidence(self):
        self.write([{"severity": "Minor", "claim": "nil deref", "evidence": "x", "verdict": "fix"}])
        reviews = ingest(data(), PRS, self.dir, tool="variant", claim_only=True)[URL]["reviews"]
        self.assertEqual([c["body"] for r in reviews if r["tool"] == "variant" for c in r["review_comments"]],
                         ["[Minor] nil deref"])

    def test_appendix_findings_are_not_reported(self):
        self.write([{"severity": "Minor", "claim": "kept", "verdict": "fix", "list": "main"},
                    {"severity": "Minor", "claim": "dropped", "verdict": "fix", "list": "appendix"}])
        reviews = ingest(data(), PRS, self.dir, tool="variant")[URL]["reviews"]
        self.assertEqual([c["body"] for r in reviews if r["tool"] == "variant" for c in r["review_comments"]],
                         ["[Minor] kept"])

    def test_refuses_partial_run(self):
        with self.assertRaises(SystemExit):
            ingest(data(), PRS, self.dir)

    def test_refuses_pr_missing_from_manifest(self):
        self.write([])
        d = data()
        d["https://github.com/grafana/grafana/pull/2"] = {"golden_comments": [], "reviews": []}
        with self.assertRaises(SystemExit):
            ingest(d, PRS, self.dir)

    def test_rejects_bad_severity(self):
        self.write([{"severity": "High", "claim": "x", "verdict": "fix"}])
        with self.assertRaises(ValueError):
            ingest(data(), PRS, self.dir)


if __name__ == "__main__":
    unittest.main()


FAKE_ACP = r'''#!/usr/bin/env python3
import json, os, sys
log = open(os.environ["FAKE_ACP_LOG"], "a", buffering=1)
def send(m):
    print(json.dumps({"jsonrpc": "2.0", **m}), flush=True)
for line in sys.stdin:
    m = json.loads(line)
    log.write(line)
    if "method" not in m:
        continue
    if m["method"] == "session/new":
        send({"id": m["id"], "result": {"sessionId": "s1", "cwd": m["params"]["cwd"]}})
    elif m["method"] == "session/prompt":
        opts = [{"optionId": "yes", "kind": "allow_once"}, {"optionId": "no", "kind": "reject_once"}]
        for n, kind in ((901, "read"), (902, "edit")):
            send({"id": n, "method": "session/request_permission", "params": {"toolCall": {"kind": kind}, "options": opts}})
            log.write(sys.stdin.readline())
        send({"method": "session/update", "params": {"update": {"sessionUpdate": "agent_message_chunk",
              "content": {"type": "text", "text": '{"verdict": "confirmed",'}}}})
        send({"method": "session/update", "params": {"update": {"sessionUpdate": "agent_message_chunk",
              "content": {"type": "text", "text": ' "impact": "trivial"}'}}}})
        send({"id": m["id"], "result": {"stopReason": "end_turn", "usage": {"totalTokens": 7}}})
    else:
        send({"id": m["id"], "result": {}})
'''


class GeminiBackendTest(unittest.TestCase):
    def test_reads_reply_allows_reads_and_rejects_edits(self):
        import os
        import types
        from unittest import mock

        import verify
        d = Path(tempfile.mkdtemp())
        (d / "agy_acp_server").write_text(FAKE_ACP)
        (d / "agy_acp_server").chmod(0o755)
        env = {"PATH": f"{d}:{os.environ['PATH']}", "FAKE_ACP_LOG": str(d / "log")}
        args = types.SimpleNamespace(model="gemini-4-neon", effort="high", timeout=1)
        with mock.patch.dict(os.environ, env):
            text, meta = verify.ask_gemini("task", d, d / "change.patch", args)
        self.assertEqual(json.loads(text), {"verdict": "confirmed", "impact": "trivial"})
        self.assertEqual(meta["usage"], {"totalTokens": 7})
        self.assertEqual(meta["permission_requests"], [{"kind": "read", "allowed": True}, {"kind": "edit", "allowed": False}])
        sent = [json.loads(ln) for ln in (d / "log").read_text().splitlines()]
        answers = {m["id"]: m["result"]["outcome"]["optionId"] for m in sent if m.get("id") in (901, 902)}
        self.assertEqual(answers, {901: "yes", 902: "no"})
        config = {m["params"]["configId"]: m["params"]["value"] for m in sent if m.get("method") == "session/set_config_option"}
        self.assertEqual(config, {"model": "gemini-4-neon", "thinking_level": "high"})
