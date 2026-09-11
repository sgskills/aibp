from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from entity_matcher import match_periods


def _period(label: str, rows: list[dict[str, Any]], top_n: int = 2) -> dict[str, Any]:
    return {
        "period": label,
        "platform": "天猫",
        "scope": "全网",
        "category": "耳机",
        "ranking_metric": "交易总量",
        "top_n": top_n,
        "rows": rows,
    }


class EntityMatcherTests(unittest.TestCase):
    def test_rank_delta_entries_exits_reentry_and_platform_new_are_distinct(self) -> None:
        periods = [
            _period(
                "2026-07-01~2026-07-07",
                [
                    {"rank": 1, "product_id": "A", "title": "商品A", "shop": "甲店"},
                    {"rank": 2, "product_id": "B", "title": "商品B", "shop": "乙店"},
                ],
            ),
            _period(
                "2026-07-08~2026-07-14",
                [
                    {"rank": 1, "product_id": "B", "title": "商品B", "shop": "乙店"},
                    {"rank": 2, "product_id": "C", "title": "商品C", "shop": "丙店", "trend": "新上榜"},
                ],
            ),
            _period(
                "2026-07-15~2026-07-21",
                [
                    {"rank": 1, "product_id": "A", "title": "商品A", "shop": "甲店"},
                    {"rank": 2, "product_id": "B", "title": "商品B", "shop": "乙店"},
                ],
            ),
        ]

        result = match_periods(periods)
        first_b = next(
            item
            for item in result["matched"]
            if item["product_id"] == "B" and item["before_period"] == "2026-07-01 ~ 2026-07-07"
        )

        self.assertEqual(first_b["rank_delta"], 1)
        self.assertEqual(first_b["direction"], "up")
        self.assertTrue(first_b["rank_is_ordinal"])
        self.assertEqual(result["summary"]["entry_count"], 2)
        self.assertEqual(result["summary"]["exit_count"], 2)
        self.assertEqual(result["summary"]["reentry_count"], 1)
        self.assertEqual(result["summary"]["platform_new_listed_count"], 1)
        self.assertEqual(result["reentries"][0]["product_id"], "A")
        self.assertEqual(result["platform_new_listed"][0]["product_id"], "C")
        self.assertTrue(all(item["not_delisted_or_zero_sales"] for item in result["exits"]))
        self.assertEqual(result["exits"][0]["classification"], "退出所给 Top-2 窗口")

    def test_different_top_n_excludes_rows_outside_common_k(self) -> None:
        result = match_periods(
            [
                _period(
                    "2026-07-01~2026-07-07",
                    [
                        {"rank": 1, "product_id": "A"},
                        {"rank": 2, "product_id": "B"},
                        {"rank": 3, "product_id": "C"},
                    ],
                    top_n=3,
                ),
                _period(
                    "2026-07-08~2026-07-14",
                    [{"rank": 1, "product_id": "B"}, {"rank": 2, "product_id": "D"}],
                    top_n=2,
                ),
            ]
        )

        comparison = result["per_comparison"][0]

        self.assertEqual(comparison["common_k"], 2)
        self.assertEqual(comparison["matched_count"], 1)
        self.assertEqual({entry["product_id"] for entry in result["entries"]}, {"D"})
        self.assertEqual({exit_item["product_id"] for exit_item in result["exits"]}, {"A"})
        self.assertNotIn("C", {item["product_id"] for item in result["exits"]})

    def test_same_id_large_identity_change_is_link_reuse_not_safe_trajectory(self) -> None:
        result = match_periods(
            [
                _period(
                    "2026-07-01~2026-07-07",
                    [{"rank": 1, "product_id": "LINK-1", "title": "无线蓝牙耳机", "shop": "甲店"}],
                    top_n=1,
                ),
                _period(
                    "2026-07-08~2026-07-14",
                    [{"rank": 1, "product_id": "LINK-1", "title": "家用扫地机器人", "shop": "乙店"}],
                    top_n=1,
                ),
            ]
        )

        self.assertEqual(result["summary"]["reuse_suspect_count"], 1)
        self.assertEqual(result["summary"]["safe_matched_count"], 0)
        self.assertFalse(result["matched"][0]["safe_for_trajectory"])
        self.assertTrue({"shop_changed", "title_changed_substantially"}.issubset(result["reuse_suspects"][0]["reasons"]))
        self.assertIn("疑似链接复用", result["reuse_suspects"][0]["classification"])

    def test_same_title_different_ids_are_candidates_and_never_auto_merged(self) -> None:
        result = match_periods(
            [
                _period(
                    "2026-07-01~2026-07-07",
                    [{"rank": 1, "product_id": "OLD-ID", "title": "同款降噪耳机", "shop": "甲店"}],
                    top_n=1,
                ),
                _period(
                    "2026-07-08~2026-07-14",
                    [{"rank": 1, "product_id": "NEW-ID", "title": "同款降噪耳机", "shop": "甲店"}],
                    top_n=1,
                ),
            ]
        )

        self.assertEqual(result["summary"]["matched_count"], 0)
        self.assertEqual(result["summary"]["title_alias_candidate_count"], 1)
        candidate = result["title_alias_candidates"][0]
        self.assertEqual((candidate["before_product_id"], candidate["after_product_id"]), ("OLD-ID", "NEW-ID"))
        self.assertIn("禁止自动合并", candidate["classification"])

    def test_product_id_is_matched_as_an_exact_string_not_a_number(self) -> None:
        result = match_periods(
            [
                _period(
                    "2026-07-01~2026-07-07",
                    [
                        {"rank": 1, "product_id": "000123", "title": "甲"},
                        {"rank": 2, "product_id": "123", "title": "乙"},
                    ],
                ),
                _period(
                    "2026-07-08~2026-07-14",
                    [
                        {"rank": 1, "product_id": "123", "title": "乙"},
                        {"rank": 2, "product_id": "000123", "title": "甲"},
                    ],
                ),
            ]
        )

        self.assertEqual({item["product_id"] for item in result["matched"]}, {"000123", "123"})
        deltas = {item["product_id"]: item["rank_delta"] for item in result["matched"]}
        self.assertEqual(deltas, {"000123": -1, "123": 1})

    def test_interval_changes_use_bounds_and_report_overlap_as_uncertain(self) -> None:
        result = match_periods(
            [
                _period(
                    "2026-07-01~2026-07-07",
                    [{"rank": 1, "product_id": "A", "buyers": "1万~2万"}],
                    top_n=1,
                ),
                _period(
                    "2026-07-08~2026-07-14",
                    [{"rank": 1, "product_id": "A", "buyers": "1.5万~3万"}],
                    top_n=1,
                ),
            ]
        )

        change = result["matched"][0]["interval_changes"]["buyers"]

        self.assertEqual(change["lower_delta"], -5_000.0)
        self.assertEqual(change["upper_delta"], 20_000.0)
        self.assertEqual(change["direction"], "overlap_or_uncertain")
        self.assertTrue(change["ordinal_or_interval_only"])

    def test_duplicate_id_outside_common_k_excludes_every_copy_and_every_event_type(self) -> None:
        result = match_periods(
            [
                _period(
                    "2026-07-01~2026-07-07",
                    [
                        {"rank": 1, "product_id": "A", "title": "重复链接第一条"},
                        {"rank": 2, "product_id": "B", "title": "稳定商品"},
                        {"rank": 3, "product_id": "A", "title": "重复链接第二条"},
                    ],
                    top_n=3,
                ),
                _period(
                    "2026-07-08~2026-07-14",
                    [
                        {"rank": 1, "product_id": "A", "title": "后期唯一A"},
                        {"rank": 2, "product_id": "B", "title": "稳定商品"},
                    ],
                    top_n=2,
                ),
            ]
        )

        event_lists = (
            result["matched"],
            result["entries"],
            result["exits"],
            result["reentries"],
            result["platform_new_listed"],
        )
        self.assertTrue(all("A" not in {str(item.get("product_id")) for item in events} for events in event_lists))
        self.assertEqual({item["product_id"] for item in result["matched"]}, {"B"})
        self.assertEqual(result["entries"], [])
        self.assertEqual(result["exits"], [])
        self.assertEqual(result["reentries"], [])
        self.assertTrue(
            any(
                item.get("product_id") == "A" and item.get("reason") == "duplicate_product_id_excluded_not_first_wins"
                for item in result["excluded_ambiguous_ids"]
            )
        )


if __name__ == "__main__":
    unittest.main()
