from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from platform_guard import inspect_platform
from title_guard import load_profiles, measure_title, validate_title


ORIGINAL_58 = "碗碟套装中式高颜值景德镇家用新款陶瓷碗餐具套装碗盘乔迁新居"
ORIGINAL_60 = "摩登世家釉下彩窑变2026新款餐具乔迁新居礼物碗盘碟套装家用碗具"
SHORT_REWRITE_46 = "景德镇陶瓷碗碟套装家用2026新款中式乔迁新居餐具"
SHORT_REWRITE_50 = "摩登世家釉下彩窑变碗碟套装家用2026新款乔迁新居餐具"
MICRO_TUNED_60 = "碗碟套装中式高颜值景德镇家用新款陶瓷碗餐具套装碗盘碟乔迁新居"


def request_for(title: str, *, original: str | None = None, mode: str | None = None,
                required: list[str] | None = None) -> dict:
    # 每个候选使用完整标题作为单个可追溯片段，避免本测试依赖中文分词。
    request = {
        "platform": "tmall",
        "title": title,
        "title_core_terms": [title],
        "keyword_sources": [
            {"term": title, "status": "confirmed", "source": "用户提供的原标题及已确认词池"}
        ],
        "required_terms": list(required or []),
    }
    if original is not None:
        request["original_title"] = original
        request["revision"] = {"mode": mode, "removals": []}
    return request


class TmallOperatingLengthTests(unittest.TestCase):
    def test_user_examples_have_frozen_legacy_byte_counts(self) -> None:
        self.assertEqual(58, measure_title(ORIGINAL_58, "legacy_weighted_bytes"))
        self.assertEqual(60, measure_title(ORIGINAL_60, "legacy_weighted_bytes"))
        self.assertEqual(46, measure_title(SHORT_REWRITE_46, "legacy_weighted_bytes"))
        self.assertEqual(50, measure_title(SHORT_REWRITE_50, "legacy_weighted_bytes"))
        self.assertEqual(60, measure_title(MICRO_TUNED_60, "legacy_weighted_bytes"))

    def test_tmall_short_title_is_blocked_without_user_prompt(self) -> None:
        result = validate_title(request_for(SHORT_REWRITE_46))
        self.assertFalse(result["allowed"])
        self.assertIn("length_below_min", {item["code"] for item in result["errors"]})
        self.assertEqual("owner_operating_default", result["measurements"]["length_policy_source"])

    def test_non_tmall_platform_does_not_inherit_tmall_operating_target(self) -> None:
        request = request_for("M1蓝牙音箱")
        request["platform"] = "jd"
        self.assertTrue(validate_title(request)["allowed"])

    def test_owner_operating_target_survives_official_profile_review_due(self) -> None:
        result = inspect_platform(load_profiles(), "tmall", "2026-09-09")
        self.assertTrue(result["schema_valid"])
        self.assertTrue(result["review_due"])
        self.assertEqual(
            "hard",
            result["profile"]["operating_defaults"]["length"]["enforcement"],
        )

    def test_malformed_owner_operating_target_fails_profile_schema(self) -> None:
        profiles = load_profiles()
        profiles["platforms"]["tmall"]["operating_defaults"]["length"]["min"] = "59"
        result = inspect_platform(profiles, "tmall", "2026-09-09")
        self.assertFalse(result["schema_valid"])
        self.assertIn(
            "platform_schema_invalid",
            {item["code"] for item in result["errors"]},
        )


class OriginalFirstRevisionTests(unittest.TestCase):
    def test_qualified_original_is_kept_exactly(self) -> None:
        result = validate_title(request_for(ORIGINAL_60, original=ORIGINAL_60, mode="keep"))
        self.assertTrue(result["allowed"])
        self.assertEqual("keep", result["checks"]["revision_mode"])
        self.assertTrue(result["checks"]["original_title_qualified"])

    def test_qualified_original_cannot_be_rewritten_for_optimization(self) -> None:
        result = validate_title(request_for(SHORT_REWRITE_50, original=ORIGINAL_60, mode="micro_edit"))
        self.assertFalse(result["allowed"])
        codes = {item["code"] for item in result["errors"]}
        self.assertIn("qualified_original_changed", codes)
        self.assertIn("length_below_min", codes)

    def test_short_original_can_be_micro_tuned_by_insertion_only(self) -> None:
        result = validate_title(request_for(MICRO_TUNED_60, original=ORIGINAL_58, mode="micro_edit"))
        self.assertTrue(result["allowed"])
        self.assertEqual("micro_edit", result["checks"]["revision_mode"])
        self.assertTrue(result["checks"]["original_order_preserved"])

    def test_large_shortening_and_reordering_is_not_a_micro_edit(self) -> None:
        result = validate_title(request_for(SHORT_REWRITE_46, original=ORIGINAL_58, mode="micro_edit"))
        self.assertFalse(result["allowed"])
        codes = {item["code"] for item in result["errors"]}
        self.assertIn("original_order_not_preserved", codes)
        self.assertIn("length_below_min", codes)

    def test_missing_required_term_is_added_without_reordering_the_original(self) -> None:
        original_without_ceramic = ORIGINAL_58.replace("陶瓷", "")
        result = validate_title(
            request_for(
                MICRO_TUNED_60,
                original=original_without_ceramic,
                mode="micro_edit",
                required=["陶瓷"],
            )
        )
        self.assertTrue(result["allowed"])
        self.assertTrue(result["checks"]["original_order_preserved"])
        self.assertEqual(1, result["checks"]["required_terms_met"])

    def test_revision_contract_is_visible_to_the_agent(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        output = (ROOT / "references" / "output-contract.md").read_text(encoding="utf-8")
        keywords = (ROOT / "references" / "keyword-method.md").read_text(encoding="utf-8")
        self.assertIn("保留原标题 → 微调原标题 → 重构标题", skill)
        self.assertIn("不得为了优化而改标题", skill)
        self.assertIn("59–60 旧字节", skill)
        self.assertIn("精确字节数", output)
        self.assertIn("相对顺序", keywords)


if __name__ == "__main__":
    unittest.main()
