"""Round-3 public delivery regressions using new synthetic inputs only."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from analyze_rankings import analyze_payload, render_markdown


def _row(rank: int, product_id: str, shop: str, buyers: Any = None) -> dict[str, Any]:
    return {
        "rank": rank,
        "product_id": product_id,
        "title": f"商品{product_id}",
        "shop": shop,
        "buyers": buyers,
    }


def _period(index: int, rows: list[dict[str, Any]], source_file: str) -> dict[str, Any]:
    start = 1 + index * 7
    return {
        "period": f"2026-07-{start:02d}~2026-07-{start + 6:02d}",
        "platform": "天猫",
        "scope": "全网",
        "category": "餐具",
        "ranking_metric": "交易总量",
        "top_n": len(rows),
        "source_file": source_file,
        "sheet": "榜单",
        "rows": rows,
    }


def _entrant_payload() -> dict[str, Any]:
    return {
        "periods": [
            _period(
                0,
                [
                    _row(1, "Exact-ID-A", "mornenjoy旗舰店", 120),
                    _row(2, "Stable-ID-B", "yomerto旗舰店", "220-260"),
                    _row(3, "Stable-ID-C", "其他店铺"),
                ],
                "source-week-1.csv",
            ),
            _period(
                1,
                [
                    _row(1, "New-ID-D", "yomerto旗舰店", 430),
                    _row(2, "Stable-ID-B", "yomerto旗舰店", "400-440"),
                    _row(3, "Stable-ID-C", "其他店铺"),
                ],
                "source-week-2.csv",
            ),
        ]
    }


class ReleaseDeliveryGuardrailTests(unittest.TestCase):
    def test_source_shop_names_are_verbatim_and_prominent_in_json_and_markdown(self) -> None:
        result = analyze_payload(_entrant_payload(), mode="quick")
        guardrails = result["delivery_guardrails"]
        markdown = render_markdown(result)

        self.assertTrue(guardrails["identity_verbatim_required"])
        shops = {item["value"] for item in guardrails["source_shop_names"]}
        self.assertTrue({"mornenjoy旗舰店", "yomerto旗舰店"}.issubset(shops))
        self.assertIn("## 交付硬规则（压缩也不得省略）", markdown)
        self.assertIn("mornenjoy旗舰店", markdown)
        self.assertIn("yomerto旗舰店", markdown)
        self.assertIn("New-ID-D", markdown)

    def test_quick_and_deep_keep_scope_and_action_validation_basis(self) -> None:
        for mode in ("quick", "deep"):
            with self.subTest(mode=mode):
                result = analyze_payload(_entrant_payload(), mode=mode)
                markdown = render_markdown(result)
                guardrails = result["delivery_guardrails"]

                self.assertEqual(
                    guardrails["compression_must_keep"],
                    ["来源", "周期", "范围", "排名口径", "验证指标", "周期设置依据", "停止/回退条件"],
                )
                for action in result["actions"].values():
                    self.assertTrue(action)
                    validation = action["validation"]
                    self.assertTrue(validation["metrics"])
                    self.assertTrue(validation["cycle"])
                    self.assertTrue(validation["cycle_basis"])
                    self.assertTrue(validation["threshold_source"])
                    self.assertTrue(validation["stop_condition"])
                for fragment in (
                    "2026-07-01 ~ 2026-07-07",
                    "2026-07-08 ~ 2026-07-14",
                    "范围=全网",
                    "排名指标=交易总量",
                    "周期设置依据=",
                    "仅证据窗口，不等于测试周期",
                    "停止条件=",
                ):
                    self.assertIn(fragment, markdown)

    def test_skill_and_output_contract_state_the_nonnegotiable_delivery_rules(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        contract = (SKILL_ROOT / "references" / "output-contract.md").read_text(encoding="utf-8")
        required = (
            "身份值必须逐字来自结构化结果或源表",
            "不得翻译、扩写、品牌化、大小写改写或无证别名替换",
            "压缩不得省略关键口径",
            "不能把源表统计周期直接当作测试周期",
            "不得把部分缺失、部分区间或单个字段的能力缺口普遍化为全列事实",
            "最终回答前逐项核对所有店名、商品ID和数字是否可定位到源值",
        )
        for document in (skill, contract):
            for phrase in required:
                with self.subTest(document="SKILL" if document is skill else "output-contract", phrase=phrase):
                    self.assertIn(phrase, document)

    def test_mixed_exact_interval_and_missing_values_are_counted_not_generalized(self) -> None:
        payload = {
            "periods": [
                _period(
                    0,
                    [
                        _row(1, "Exact", "mornenjoy旗舰店", 120),
                        _row(2, "Interval", "yomerto旗舰店", "220-260"),
                        _row(3, "Missing", "其他店铺"),
                    ],
                    "mixed-values.csv",
                )
            ]
        }
        result = analyze_payload(payload, mode="quick")
        composition = result["delivery_guardrails"]["metric_value_composition"][0]["metrics"]["buyers"]
        markdown = render_markdown(result)

        self.assertEqual(composition, {"exact": 1, "interval_or_bound": 1, "missing": 1})
        self.assertIn("买家数：精确值=1，区间/边界值=1，缺失=1", markdown)
        self.assertIn("不得概括为全列区间或全列缺失", markdown)


if __name__ == "__main__":
    unittest.main()
