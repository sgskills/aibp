import json
import os
import sys
import unittest
from pathlib import Path


ROOT = Path(os.environ.get("SG_REVIEW_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT / "scripts"))
import review_stats as runtime


class Round2UnicodeIdentifierTests(unittest.TestCase):
    def test_mixed_script_identifier_is_removed_from_all_output_fields(self):
        raw_id = "订单甲12345"
        data = {
            "source_url": f"https://example.invalid/orders/{raw_id}?token=synthetic",
            "reviews": [{
                "review_id": raw_id,
                "review_text": f"合成评价：订单 {raw_id} 包装完整",
                "follow_up": f"合成追评：仍在核对 {raw_id}",
                "sku": f"礼盒-{raw_id}",
                "product": f"商品-{raw_id}",
                "platform": f"平台-{raw_id}",
                "version": f"版本-{raw_id}",
                "fulfillment": f"履约-{raw_id}",
                "inclusion_rule": f"规则-{raw_id}",
            }],
        }
        initial = runtime.analyze_payload(data)
        internal_id = initial["normalized_reviews"][0]["review_id"]
        annotations = {
            "basis_sha256": initial["audit"]["annotation_basis_sha256"],
            "reviewed_review_ids": [internal_id],
            "annotations": [{
                "review_id": internal_id,
                "theme_mentions": [{
                    "theme": f"包装-{raw_id}",
                    "quote": "包装完整",
                }],
                "scene_clues": [{
                    "label": f"送礼-{raw_id}",
                    "quote": "包装完整",
                }],
            }],
        }
        serialized = json.dumps(runtime.analyze_payload(data, annotations), ensure_ascii=False)
        self.assertNotIn(raw_id, serialized)
        self.assertIn("[外部编号X000001]", serialized)

    def test_delimiter_identifier_uses_longest_exact_match_without_unrelated_redaction(self):
        shorter = "订单/甲-12345"
        longer = "订单/甲-12345-扩展"
        data = {"reviews": [
            {"review_id": shorter, "review_text": f"合成评价：{shorter} 与普通订单甲12345均可查"},
            {"review_id": longer, "review_text": f"合成评价：{longer} 已完成"},
        ]}
        result = runtime.analyze_payload(data)
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(shorter, serialized)
        self.assertNotIn(longer, serialized)
        self.assertIn("普通订单甲12345均可查", serialized)
        self.assertIn("[外部编号X000001]", serialized)
        self.assertIn("[外部编号X000002]", serialized)

    def test_external_id_prefix_does_not_redact_longer_unrelated_identifier(self):
        raw_id = "客户甲-AB_12/中文.77"
        similar = raw_id + "0"
        data = {
            "source_url": f"https://example.test/item/{similar}/detail?campaign=drop-me",
            "reviews": [{
                "review_id": raw_id,
                "review_text": f"实际业务号 {raw_id} 已登记；无关型号 {similar} 正常在售",
                "sku": f"实际批次 {raw_id}；相似批次 {similar}",
            }],
        }
        initial = runtime.analyze_payload(data)
        row = initial["normalized_reviews"][0]
        self.assertIn("[外部编号X000001]", row["analysis_text"])
        self.assertIn(similar, row["analysis_text"])
        self.assertIn(similar, row["sku"])
        self.assertEqual(
            initial["source"]["source_url"],
            f"https://example.test/item/{similar}/detail",
        )

        annotations = {
            "basis_sha256": initial["audit"]["annotation_basis_sha256"],
            "reviewed_review_ids": [row["review_id"]],
            "annotations": [{
                "review_id": row["review_id"],
                "theme_mentions": [{
                    "theme": f"实际号 {raw_id}；相似词 {similar}",
                    "quote": "已登记",
                }],
            }],
        }
        theme = runtime.analyze_payload(data, annotations)["themes"]["items"][0]["theme"]
        self.assertIn("[外部编号X000001]", theme)
        self.assertIn(similar, theme)

    def test_exact_mixed_identifier_is_redacted_inside_unspaced_chinese_sentence(self):
        raw_id = "订单甲12345"
        data = {
            "source_url": f"https://example.test/orders/{raw_id}/detail",
            "reviews": [{
                "review_id": raw_id,
                "review_text": f"合成评价：订单{raw_id}包装完整",
                "sku": f"礼盒-{raw_id}",
            }],
        }
        serialized = json.dumps(runtime.analyze_payload(data), ensure_ascii=False)
        self.assertNotIn(raw_id, serialized)
        self.assertIn("订单[外部编号X000001]包装完整", serialized)

    def test_ascii_prefixed_or_suffixed_similar_tokens_are_preserved(self):
        raw_id = "客户甲-AB_12/中文.77"
        similarities = ["X" + raw_id, raw_id + "A", raw_id + "_0"]
        data = {"reviews": [{
            "review_id": raw_id,
            "review_text": "；".join(similarities),
        }]}
        text = runtime.analyze_payload(data)["normalized_reviews"][0]["analysis_text"]
        for similar in similarities:
            self.assertIn(similar, text)


if __name__ == "__main__":
    unittest.main()
