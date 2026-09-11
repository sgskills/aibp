from __future__ import annotations

import copy
import json
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from ranking_engine import analyze_periods, validate_result_guards


def _period(
    label: str,
    rows: list[dict[str, Any]],
    *,
    top_n: int | None = None,
    platform: str = "天猫",
    scope: str = "全网",
    category: str = "耳机",
    metric: str = "交易总量",
) -> dict[str, Any]:
    return {
        "period": label,
        "platform": platform,
        "scope": scope,
        "category": category,
        "ranking_metric": metric,
        "top_n": top_n or max((int(row["rank"]) for row in rows), default=0),
        "rows": rows,
    }


def _weekly_periods(count: int, *, with_visitors: bool = False) -> list[dict[str, Any]]:
    periods: list[dict[str, Any]] = []
    start = date(2026, 7, 1)
    for index in range(count):
        period_start = start + timedelta(days=7 * index)
        period_end = period_start + timedelta(days=6)
        target_rank = count - index
        target_row: dict[str, Any] = {
            "rank": target_rank,
            "product_id": "A",
            "title": "降噪耳机",
            "shop": "甲店",
            "buyers": 10 * (index + 1),
        }
        if with_visitors:
            target_row["visitors"] = 100 * (index + 1)
        filler_ids = iter(f"FILL-{number}" for number in range(1, count))
        rows = [
            target_row if rank == target_rank else {"rank": rank, "product_id": next(filler_ids)}
            for rank in range(1, count + 1)
        ]
        periods.append(
            _period(
                f"{period_start.isoformat()}~{period_end.isoformat()}",
                rows,
                top_n=count,
            )
        )
    return periods


class RankingEngineTests(unittest.TestCase):
    def test_one_two_and_three_periods_use_only_allowed_temporal_labels(self) -> None:
        expected = {
            1: ("snapshot", "单期快照/线索"),
            2: ("short_signal", "短期变化信号"),
            3: ("trend_candidate", "趋势候选（未满足较强趋势门槛）"),
        }

        for count, (level, label) in expected.items():
            with self.subTest(period_count=count):
                result = analyze_periods(_weekly_periods(count), mode="deep")
                self.assertEqual(result["temporality"]["level"], level)
                self.assertEqual(result["temporality"]["label"], label)
                self.assertFalse(result["temporality"]["strong_trend"])
                self.assertFalse(result["temporality"]["causality_proven"])

    def test_four_periods_need_two_observed_metrics_in_the_same_direction_for_strong_trend(self) -> None:
        one_metric = analyze_periods(_weekly_periods(4, with_visitors=False), mode="deep")
        two_metrics = analyze_periods(_weekly_periods(4, with_visitors=True), mode="deep")

        self.assertEqual(one_metric["temporality"]["level"], "trend_candidate")
        self.assertFalse(one_metric["temporality"]["strong_trend"])
        self.assertEqual(two_metrics["temporality"]["level"], "strong_trend")
        self.assertTrue(two_metrics["temporality"]["strong_trend"])
        candidate = two_metrics["temporality"]["strong_trend_candidates"][0]
        self.assertEqual(candidate["period_count"], 4)
        self.assertEqual(set(candidate["supporting_observed_metrics"]), {"buyers", "visitors"})
        self.assertIn("仍非因果证据", candidate["classification"])

    def test_multi_period_incomparable_islands_are_not_merged_into_a_signal(self) -> None:
        periods = [
            _period(
                "2026-07-01~2026-07-07",
                [{"rank": 1, "product_id": "A"}],
                platform="天猫",
            ),
            _period(
                "2026-07-08~2026-07-14",
                [{"rank": 1, "product_id": "A"}],
                platform="淘宝",
            ),
        ]

        result = analyze_periods(periods, mode="deep")

        self.assertEqual(result["temporality"]["level"], "incomparable_multi_period")
        self.assertEqual(result["comparability"]["comparable_count"], 0)
        self.assertFalse(result["comparability"]["cross_island_merge_performed"])
        self.assertEqual(result["trajectories"]["summary"]["matched_count"], 0)

    def test_pollution_is_listed_before_cleaned_sensitivity_and_never_silently_removed(self) -> None:
        periods = [
            _period(
                "2026-07-01~2026-07-07",
                [
                    {"rank": 1, "product_id": "A", "title": "无线降噪耳机"},
                    {"rank": 2, "product_id": "B", "title": "福利专拍链接"},
                    {"rank": 3, "product_id": "C", "title": "平板电脑学习机"},
                ],
                top_n=3,
            )
        ]

        result = analyze_periods(periods, mode="deep")
        sensitivity = result["sensitivity"]

        self.assertEqual(len(sensitivity["evidence_first"]), 2)
        self.assertEqual(
            {item["reason"] for item in sensitivity["evidence_first"]},
            {"transaction_only_link", "likely_wrong_category"},
        )
        self.assertFalse(sensitivity["removed_silently"])
        self.assertTrue(sensitivity["cleaning_used_for_sensitivity_only"])
        self.assertEqual(sensitivity["all_data"]["row_count"], 3)
        self.assertEqual(sensitivity["cleaned_view"]["row_count"], 1)
        self.assertEqual(sensitivity["difference"]["row_count"], -2)

    def test_missing_price_amount_and_cost_create_explicit_capability_gaps(self) -> None:
        result = analyze_periods(
            [
                _period(
                    "2026-07-01~2026-07-07",
                    [{"rank": 1, "product_id": "A", "title": "降噪耳机", "keywords": "降噪,长续航"}],
                    top_n=1,
                )
            ],
            mode="deep",
        )

        gap_codes = {gap["code"] for gap in result["capability_gaps"]}

        self.assertTrue({"NO_PRICE", "NO_PAYMENT_AMOUNT", "NO_COST"}.issubset(gap_codes))
        self.assertIn("不能推算GMV", {gap["message"] for gap in result["capability_gaps"] if gap["code"] == "NO_PAYMENT_AMOUNT"}.pop())
        self.assertTrue(any("不能推算GMV" in gap["message"] for gap in result["capability_gaps"]))
        self.assertFalse(result["structure"]["own_product_positioning"]["provided"])

    def test_every_opportunity_and_action_keeps_the_full_evidence_validation_chain(self) -> None:
        result = analyze_periods(
            [
                _period(
                    "2026-07-01~2026-07-07",
                    [
                        {"rank": 1, "product_id": "B", "title": "耳机"},
                        {"rank": 2, "product_id": "A", "title": "耳机", "keywords": "降噪"},
                    ],
                    top_n=2,
                ),
                _period(
                    "2026-07-08~2026-07-14",
                    [
                        {"rank": 1, "product_id": "A", "title": "耳机", "keywords": "降噪"},
                        {"rank": 2, "product_id": "B", "title": "耳机"},
                    ],
                    top_n=2,
                ),
            ],
            mode="deep",
        )
        required = {
            "observation_fact",
            "data_position_and_definition",
            "change_pattern",
            "possible_explanation",
            "alternative_explanation_or_limitation",
            "opportunity_hypothesis",
            "action",
            "validation",
            "is_hypothesis_not_decision",
        }

        recommendations = [*result["opportunities"], *result["actions"].values()]
        self.assertEqual(set(result["actions"]), {"product_selection", "product_development", "main_promotion"})
        for recommendation in recommendations:
            with self.subTest(code=recommendation["code"], domain=recommendation.get("domain")):
                self.assertTrue(required.issubset(recommendation))
                self.assertTrue(recommendation["is_hypothesis_not_decision"])
                self.assertTrue(recommendation["validation"]["metrics"])
                self.assertTrue(recommendation["validation"]["cycle"])
                self.assertTrue(recommendation["validation"]["stop_condition"])
                self.assertTrue(recommendation["alternative_explanation_or_limitation"])
        self.assertIn("不扩库存", result["actions"]["product_selection"]["action"])
        self.assertIn("小样/概念验证", result["actions"]["product_development"]["action"])
        self.assertIn("小流量验证", result["actions"]["main_promotion"]["action"])

    def test_own_store_and_product_ids_are_positioned_without_guessing(self) -> None:
        result = analyze_periods(
            [
                _period(
                    "2026-07-01~2026-07-07",
                    [
                        {"rank": 1, "product_id": "A", "shop": "竞品旗舰店"},
                        {"rank": 2, "product_id": "OWN-2", "shop": "我的官方旗舰店"},
                    ],
                    top_n=2,
                )
            ],
            own_store="我的官方旗舰店",
            own_product_ids=["A"],
            mode="deep",
        )
        positioning = result["structure"]["own_product_positioning"]

        self.assertTrue(positioning["provided"])
        self.assertEqual(positioning["match_count"], 2)
        self.assertEqual({item["product_id"] for item in positioning["matches"]}, {"A", "OWN-2"})

    def test_quick_and_deep_share_deterministic_core_evidence(self) -> None:
        periods = [
            _period(
                "2026-07-01~2026-07-07",
                [{"rank": 1, "product_id": "B"}, {"rank": 2, "product_id": "A", "title": "耳机"}],
                top_n=2,
            ),
            _period(
                "2026-07-08~2026-07-14",
                [{"rank": 1, "product_id": "A", "title": "耳机"}, {"rank": 2, "product_id": "B"}],
                top_n=2,
            ),
        ]

        quick = analyze_periods(periods, mode="quick")
        deep = analyze_periods(periods, mode="deep")

        for key in ("audit", "comparability", "temporality", "structure", "trajectories", "sensitivity", "capability_gaps", "actions"):
            with self.subTest(key=key):
                self.assertEqual(quick[key], deep[key])
        self.assertLessEqual(len(quick["facts"]), 3)
        self.assertLessEqual(len(quick["opportunities"]), 3)
        self.assertEqual(quick["opportunities"], deep["opportunities"])

    def test_all_network_tmall_and_taobao_mix_is_explicitly_limited(self) -> None:
        result = analyze_periods(
            [
                _period(
                    "2026-07-01~2026-07-07",
                    [
                        {"rank": 1, "product_id": "TM", "shop_type": "天猫"},
                        {"rank": 2, "product_id": "TB", "shop_type": "淘宝"},
                    ],
                    top_n=2,
                    platform="全网",
                    scope="全网",
                )
            ],
            mode="deep",
        )

        self.assertIn("同时含天猫/淘宝", result["max_limitation"])
        self.assertIn("不能冒充纯天猫样本", result["max_limitation"])

    def test_title_attribute_counts_are_explicit_mentions_not_demand(self) -> None:
        result = analyze_periods(
            [
                _period(
                    "2026-07-01~2026-07-07",
                    [
                        {"rank": 1, "product_id": "A", "title": "家用高颜值耳机"},
                        {"rank": 2, "product_id": "B", "title": "家用耳机"},
                    ],
                    top_n=2,
                )
            ],
            mode="deep",
        )
        attributes = result["structure"]["periods"][0]["title_explicit_attributes"]

        self.assertEqual(attributes[0]["attribute"], "家用")
        self.assertEqual(attributes[0]["count"], 2)
        self.assertIn("标题显式提及", attributes[0]["evidence_label"])
        self.assertTrue(attributes[0]["not_consumer_demand"])

    def test_four_contiguous_periods_with_different_lengths_cannot_be_a_strong_trend(self) -> None:
        labels = (
            "2026-07-01~2026-07-07",
            "2026-07-08~2026-07-14",
            "2026-07-15~2026-07-19",
            "2026-07-20~2026-07-26",
        )
        periods = []
        for index, label in enumerate(labels):
            target_rank = 4 - index
            filler_ids = iter(("B", "C", "D"))
            rows = [
                {
                    "rank": rank,
                    "product_id": "A",
                    "buyers": 10 * (index + 1),
                    "visitors": 100 * (index + 1),
                }
                if rank == target_rank
                else {"rank": rank, "product_id": next(filler_ids)}
                for rank in range(1, 5)
            ]
            periods.append(_period(label, rows, top_n=4))

        result = analyze_periods(periods, mode="deep")

        self.assertEqual(result["temporality"]["level"], "trend_candidate")
        self.assertFalse(result["temporality"]["strong_trend"])
        self.assertEqual(result["temporality"]["strong_trend_candidates"], [])

    def test_polluted_ids_stay_in_sensitivity_but_never_drive_facts_opportunities_or_action_bases(self) -> None:
        periods = [
            _period(
                "2026-07-01~2026-07-07",
                [
                    {"rank": 1, "product_id": "CLEAN", "title": "家用耳机"},
                    {"rank": 2, "product_id": "POLLUTED", "title": "福利专拍链接"},
                ],
                top_n=2,
            ),
            _period(
                "2026-07-08~2026-07-14",
                [
                    {"rank": 1, "product_id": "POLLUTED", "title": "福利专拍链接"},
                    {"rank": 2, "product_id": "CLEAN", "title": "家用耳机"},
                ],
                top_n=2,
            ),
        ]

        result = analyze_periods(periods, mode="deep")
        recommendation_surface = json.dumps(
            {"facts": result["facts"], "opportunities": result["opportunities"], "actions": result["actions"]},
            ensure_ascii=False,
        )

        self.assertTrue(result["sensitivity"]["evidence_first"])
        self.assertEqual(result["sensitivity"]["all_data"]["matched_count"], 2)
        self.assertEqual(result["sensitivity"]["cleaned_view"]["matched_count"], 1)
        self.assertIn("POLLUTED", json.dumps(result["sensitivity"], ensure_ascii=False))
        self.assertNotIn("POLLUTED", recommendation_surface)
        rank_fact = next(fact for fact in result["facts"] if fact["code"] == "RANK_MOVES")
        self.assertEqual({item["product_id"] for item in rank_fact["observation"]}, {"CLEAN"})

    def test_own_id_reuse_and_missing_periods_are_explicit_positioning_limits(self) -> None:
        periods = [
            _period(
                "2026-07-01~2026-07-07",
                [
                    {"rank": 1, "product_id": "OWN", "title": "降噪耳机", "shop": "自有店"},
                    {"rank": 2, "product_id": "B", "title": "商品B", "shop": "乙店"},
                ],
                top_n=2,
            ),
            _period(
                "2026-07-08~2026-07-14",
                [
                    {"rank": 1, "product_id": "OWN", "title": "家用扫地机器人", "shop": "其他店"},
                    {"rank": 2, "product_id": "B", "title": "商品B", "shop": "乙店"},
                ],
                top_n=2,
            ),
            _period(
                "2026-07-15~2026-07-21",
                [
                    {"rank": 1, "product_id": "B", "title": "商品B", "shop": "乙店"},
                    {"rank": 2, "product_id": "C", "title": "商品C", "shop": "丙店"},
                ],
                top_n=2,
            ),
        ]

        result = analyze_periods(periods, own_product_ids=["OWN"], mode="deep")
        positioning_text = json.dumps(result["structure"]["own_product_positioning"], ensure_ascii=False)

        self.assertEqual(result["trajectories"]["summary"]["reuse_suspect_count"], 1)
        self.assertIn("链接复用", positioning_text)
        self.assertRegex(positioning_text, r"缺榜|未出现")
        self.assertIn("2026-07-15 ~ 2026-07-21", positioning_text)

    def test_guard_recomputes_forged_cross_island_match_and_dangerous_action_language(self) -> None:
        result = analyze_periods(
            [
                _period("2026-07-01~2026-07-07", [{"rank": 1, "product_id": "A"}], platform="天猫"),
                _period("2026-07-08~2026-07-14", [{"rank": 1, "product_id": "A"}], platform="淘宝"),
            ],
            mode="deep",
        )
        forged_cross_island = copy.deepcopy(result)
        forged_cross_island["trajectories"]["matched"].append(
            {
                "product_id": "FORGED",
                "before_period": "2026-07-01 ~ 2026-07-07",
                "after_period": "2026-07-08 ~ 2026-07-14",
                "before_island": result["audit"]["islands"][0]["island_id"],
                "after_island": result["audit"]["islands"][1]["island_id"],
                "safe_for_trajectory": True,
            }
        )
        cross_guards = validate_result_guards(forged_cross_island)

        forged_action = copy.deepcopy(result)
        forged_action["actions"]["product_selection"] = {
            "action": "立即正式立项、重投资源、扩库存，并承诺GMV份额增长",
            "is_hypothesis_not_decision": True,
            "validation": {"metrics": ["排名"], "cycle": "立即", "stop_condition": "无"},
        }
        action_guards = validate_result_guards(forged_action)

        self.assertGreater(cross_guards["cross_island_merge"], 0)
        self.assertGreater(action_guards["fabricated_sales_share_gmv"], 0)
        self.assertGreater(action_guards["hypothesis_as_decision"], 0)

    def test_guard_detects_a_forged_match_for_an_id_excluded_as_duplicate(self) -> None:
        result = analyze_periods(
            [
                _period(
                    "2026-07-01~2026-07-07",
                    [
                        {"rank": 1, "product_id": "A"},
                        {"rank": 2, "product_id": "B"},
                        {"rank": 3, "product_id": "A"},
                    ],
                    top_n=3,
                ),
                _period(
                    "2026-07-08~2026-07-14",
                    [{"rank": 1, "product_id": "A"}, {"rank": 2, "product_id": "B"}],
                    top_n=2,
                ),
            ],
            mode="deep",
        )
        self.assertNotIn("A", {item["product_id"] for item in result["trajectories"]["matched"]})
        self.assertEqual(validate_result_guards(result)["product_mismatch"], 0)

        forged = copy.deepcopy(result)
        forged["trajectories"]["matched"].append(
            {"product_id": "A", "safe_for_trajectory": True, "before_period": "x", "after_period": "y"}
        )

        self.assertGreater(validate_result_guards(forged)["product_mismatch"], 0)


if __name__ == "__main__":
    unittest.main()
