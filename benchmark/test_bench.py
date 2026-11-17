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
