"""周期重复与更正必须显式保留内容指纹和来源。"""
from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_rankings import analyze_payload

def payload() -> dict:
    return json.loads((ROOT / "tests/fixtures/03-two-auto-deep/case.json").read_text(encoding="utf-8"))["input"]

class HistoryTests(unittest.TestCase):
    def test_identical_period_copy_is_one_observation_with_duplicate_evidence(self) -> None:
        source = payload()
        reference = analyze_payload(source)
        copied = deepcopy(source["periods"][0])
        copied["source_file"] = "duplicate-copy.csv"
        source["periods"].append(copied)
        result = analyze_payload(source)
        self.assertEqual(result["trajectories"]["summary"], reference["trajectories"]["summary"])
        self.assertEqual(len(result["audit"]["islands"]), 2)
        self.assertEqual(len(result["input_history"]["deduplicated"]), 1)

    def test_conflicting_revision_needs_explicit_hash_choice_then_recomputes(self) -> None:
        source = payload()
        revised = deepcopy(source["periods"][1])
        revised["source_file"] = "correction.csv"
        revised["rows"][0]["buyers"] = "500 ~ 750"
        source["periods"].append(revised)
        conflict = analyze_payload(source)
        self.assertTrue(conflict["input_history"]["conflicts"])
        self.assertEqual(conflict["trajectories"]["summary"]["matched_count"], 0)
        variants = conflict["input_history"]["conflicts"][0]["variants"]
        selected = next(x["content_sha256"] for x in variants if any(s["file"] == "correction.csv" for s in x["sources"]))
        source["selected_revision_hashes"] = [selected]
        corrected = analyze_payload(source)
        fresh = analyze_payload({"periods": [source["periods"][0], revised]})
        self.assertEqual(corrected["trajectories"]["summary"], fresh["trajectories"]["summary"])
        self.assertEqual(len(corrected["input_history"]["resolved"]), 1)
        self.assertEqual(corrected["input_history"]["resolved"][0]["selected_sha256"], selected)

    def test_unavailable_revision_selection_is_rejected(self) -> None:
        source = payload()
        source["selected_revision_hashes"] = ["0" * 64]
        result = analyze_payload(source)
        self.assertEqual(result["status"], "rejected")

if __name__ == "__main__":
    unittest.main()
