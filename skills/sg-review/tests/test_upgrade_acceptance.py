"""Independent task-0 red-to-green contracts; synthetic data only.

Frozen by reviewer A before implementation. Existing tests stay unchanged.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(os.environ.get("SG_REVIEW_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT / "scripts"))
import review_stats as runtime


def payload() -> dict:
    return {"reviews": [
        {"review_id": "SYNTHETIC-ORDER-A", "review_text": "合成评价：包装完整，适合送礼", "sku": "红色"},
        {"review_id": "SYNTHETIC-ORDER-B", "review_text": "合成评价：握持舒适", "sku": "蓝色"},
        {"review_id": "SYNTHETIC-ORDER-C", "review_text": "合成评价：表面划痕", "sku": "蓝色"},
    ]}


def envelope(data: dict, *, all_reviewed: bool = True) -> dict:
    first = runtime.analyze_payload(data)
    ids = [row["review_id"] for row in first["normalized_reviews"]]
    return {
        "basis_sha256": first["audit"]["annotation_basis_sha256"],
        "reviewed_review_ids": ids if all_reviewed else ids[:1],
        "annotations": [{"review_id": ids[0], "theme_mentions": [
            {"theme": "包装", "quote": "包装完整", "sentiment": "positive"}
        ]}],
    }


class BindingAndDenominatorTests(unittest.TestCase):
    def test_bound_complete_keeps_distinct_review_and_mention_denominators(self):
        data = payload()
        result = runtime.analyze_payload(data, envelope(data))
        audit = result["annotation_audit"]
        self.assertEqual(audit["binding_status"], "bound")
        self.assertTrue(audit["complete"])
        self.assertEqual(audit["reviewed_review_count"], 3)
        self.assertEqual(audit["unreviewed_review_count"], 0)
        theme = result["themes"]["items"][0]
        self.assertEqual((theme["review_count"], theme["coverage_denominator"]), (1, 3))
        self.assertEqual((theme["mention_count"], theme["mention_denominator"]), (1, 1))
        self.assertFalse(theme["coverage_is_lower_bound"])
        self.assertTrue(theme["coverage_scope"])
        self.assertTrue(result["capabilities"]["evidence_backed_themes"])
        self.assertIn("包装完整", result["evidence_index"][0]["quotes"])

    def test_partial_annotation_is_not_complete_and_coverage_is_lower_bound(self):
        data = payload()
        result = runtime.analyze_payload(data, envelope(data, all_reviewed=False))
        self.assertFalse(result["annotation_audit"]["complete"])
        self.assertEqual(result["annotation_audit"]["reviewed_review_count"], 1)
        self.assertEqual(result["annotation_audit"]["unreviewed_review_count"], 2)
        theme = result["themes"]["items"][0]
        self.assertEqual(theme["coverage_denominator"], 3)
        self.assertAlmostEqual(theme["review_coverage"], 1 / 3, places=6)
        self.assertTrue(theme["coverage_is_lower_bound"])
        self.assertTrue(theme["coverage_scope"])

    def test_no_annotations_do_not_mean_zero_themes_in_fully_reviewed_population(self):
        result = runtime.analyze_payload(payload())
        self.assertFalse(result["annotation_audit"]["complete"])
        self.assertEqual(result["annotation_audit"]["reviewed_review_count"], 0)
        self.assertEqual(result["annotation_audit"]["unreviewed_review_count"], 3)

    def test_empty_but_reviewed_bound_annotations_are_distinct_from_unreviewed(self):
        data = payload()
        ann = envelope(data)
        ann["annotations"] = []
        result = runtime.analyze_payload(data, ann)
        self.assertTrue(result["annotation_audit"]["complete"])
        self.assertEqual(result["themes"]["mention_denominator"], 0)
        self.assertFalse(result["themes"]["available"])

    def test_binding_changes_on_raw_identity_even_when_sanitized_text_is_equal(self):
        data = payload()
        old = runtime.analyze_payload(data)["audit"]["annotation_basis_sha256"]
        data["reviews"][0]["review_id"] = "SYNTHETIC-ORDER-REPLACED"
        new = runtime.analyze_payload(data)["audit"]["annotation_basis_sha256"]
        self.assertNotEqual(old, new)
        self.assertEqual(len(new), 64)

    def test_binding_changes_on_order_and_config(self):
        data = payload()
        old = runtime.analyze_payload(data)["audit"]["annotation_basis_sha256"]
        reversed_data = {"reviews": list(reversed(data["reviews"]))}
        self.assertNotEqual(old, runtime.analyze_payload(reversed_data)["audit"]["annotation_basis_sha256"])
        changed = runtime.analyze_payload(data, config=runtime.AnalysisConfig(positive_min=5))
        self.assertNotEqual(old, changed["audit"]["annotation_basis_sha256"])

    def test_old_envelope_is_rejected_after_reorder_even_with_shared_quote(self):
        data = {"reviews": [
            {"review_id": "SYN-A", "review_text": "合成评价：包装完整", "sku": "甲"},
            {"review_id": "SYN-B", "review_text": "合成评价：包装完整", "sku": "乙"},
        ]}
        old = envelope(data)
        data["reviews"].reverse()
        try:
            result = runtime.analyze_payload(data, old)
        except runtime.ReviewInputError:
            return
        self.assertFalse(result["capabilities"]["evidence_backed_themes"])
        self.assertFalse(result["themes"]["available"])
        self.assertEqual(result["evidence_index"], [])
        self.assertNotEqual(result["annotation_audit"]["binding_status"], "bound")

    def test_wrong_binding_is_not_bypassed_by_empty_annotation_array(self):
        data = payload()
        ann = envelope(data)
        ann.update(basis_sha256="0" * 64, annotations=[])
        try:
            result = runtime.analyze_payload(data, ann)
        except runtime.ReviewInputError:
            return
        self.assertFalse(result["annotation_audit"]["complete"])
        self.assertNotEqual(result["annotation_audit"]["binding_status"], "bound")

    def test_duplicate_or_unknown_reviewed_ids_cannot_certify_complete(self):
        data = payload()
        for ids in (["R000001", "R000001", "R000003"], ["R000001", "R000002", "NOT-AN-ID"]):
            ann = envelope(data)
            ann["reviewed_review_ids"] = ids
            with self.subTest(ids=ids):
                try:
                    result = runtime.analyze_payload(data, ann)
                except runtime.ReviewInputError:
                    continue
                self.assertFalse(result["annotation_audit"]["complete"])

    def test_legacy_shared_quote_cannot_be_authoritative_sku_evidence(self):
        data = {"reviews": [
            {"review_text": "合成评价：共享短语", "sku": "甲"},
            {"review_text": "合成评价：共享短语", "sku": "乙"},
        ]}
        ann = [{"review_id": "R000001", "theme_mentions": [{"theme": "共享", "quote": "共享短语"}]}]
        result = runtime.analyze_payload(data, ann)
        self.assertEqual(result["annotation_audit"]["binding_status"], "legacy_unbound")
        self.assertFalse(result["annotation_audit"]["complete"])
        self.assertFalse(result["capabilities"]["evidence_backed_themes"])
        for item in result["evidence_index"]:
            self.assertNotIn("共享短语", item.get("quotes", []))

    def test_naked_normalized_output_is_explicitly_rejected(self):
        rows = runtime.analyze_payload(payload())["normalized_reviews"]
        with self.assertRaises(runtime.ReviewInputError):
            runtime.analyze_payload({"reviews": rows})

    def test_invalid_long_quote_tail_cannot_be_truncated_into_valid_evidence(self):
        text = "合成有效正文" * 40
        data = {"reviews": [{"review_text": text}]}
        first = runtime.analyze_payload(data)
        ann = {"basis_sha256": first["audit"]["annotation_basis_sha256"],
               "reviewed_review_ids": ["R000001"],
               "annotations": [{"review_id": "R000001", "theme_mentions": [
                   {"theme": "伪造尾部", "quote": text[:180] + "根本不存在的结论"}
               ]}]}
        result = runtime.analyze_payload(data, ann)
        self.assertFalse(result["themes"]["available"])
        self.assertGreater(result["themes"]["rejected_annotation_count"], 0)

    def test_source_url_path_and_external_id_in_text_do_not_leak(self):
        data = {"source_url": "https://example.invalid/users/13812345678/view?token=never-output",
                "reviews": [{"review_id": "SYNTHETIC-ORDER-4477", "review_text": "合成评价：订单 SYNTHETIC-ORDER-4477 包装完整"}]}
        serialized = json.dumps(runtime.analyze_payload(data), ensure_ascii=False)
        self.assertNotIn("13812345678", serialized)
        self.assertNotIn("never-output", serialized)
        self.assertNotIn("SYNTHETIC-ORDER-4477", serialized)

    def test_non_ecommerce_code_review_is_not_review_analysis(self):
        self.assertEqual(runtime.assess_task_scope("请 review 这段 Python 代码，找 bug"), "out_of_scope")


if __name__ == "__main__":
    unittest.main()
