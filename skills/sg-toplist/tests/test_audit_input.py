from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from audit_input import audit_dataset, audit_paths, build_comparisons, load_input, normalize_payload, parse_interval


class AuditInputTests(unittest.TestCase):
    def _write_delimited(self, suffix: str, rows: list[list[object]]) -> Path:
        path = Path(self.temp_dir.name) / f"ranking{suffix}"
        delimiter = "\t" if suffix == ".tsv" else ","
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            csv.writer(handle, delimiter=delimiter).writerows(rows)
        return path

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_csv_alias_mapping_preserves_long_id_and_interval_bounds(self) -> None:
        long_id = "000123456789012345678901234567890"
        path = self._write_delimited(
            ".csv",
            [
                [
                    "统计周期",
                    "行业排名",
                    "宝贝ID",
                    "商品标题",
                    "店铺名称",
                    "支付买家数",
                    "访客数",
                    "榜单平台",
                    "榜单范围",
                    "类目名称",
                    "排名指标",
                    "TopN",
                ],
                [
                    "2026-07-01~2026-07-07",
                    "1",
                    long_id,
                    "标题显式提及：便携",
                    "甲店",
                    "1万~2万",
                    "3万~4万",
                    "天猫",
                    "全网",
                    "耳机",
                    "交易总量",
                    "300",
                ],
            ],
        )

        payload = load_input(path)
        period = payload["periods"][0]
        row = period["rows"][0]

        self.assertEqual(period["period"], "2026-07-01 ~ 2026-07-07")
        self.assertEqual(period["top_n"], 300)
        self.assertEqual(row["product_id"], long_id)
        self.assertEqual(row["rank"], 1)
        self.assertEqual(
            row["buyers_interval"],
            {
                "lower": 10_000.0,
                "upper": 20_000.0,
                "estimated_midpoint": 15_000.0,
                "midpoint_is_estimate": True,
                "raw": "1万~2万",
            },
        )

    def test_tsv_is_read_with_the_same_canonical_contract(self) -> None:
        path = self._write_delimited(
            ".tsv",
            [
                ["周期", "排名", "商品ID", "标题", "平台", "范围", "类目", "指标"],
                ["2026-07-08~2026-07-14", "2", "90071992547409931234", "商品甲", "天猫", "全网", "耳机", "交易总量"],
            ],
        )

        payload = load_input(path)
        row = payload["periods"][0]["rows"][0]

        self.assertEqual(row["product_id"], "90071992547409931234")
        self.assertEqual(row["rank"], 2)
        self.assertEqual(row["title"], "商品甲")

    def test_xlsx_is_read_as_values_without_following_hyperlinks(self) -> None:
        from openpyxl import Workbook

        path = Path(self.temp_dir.name) / "ranking.xlsx"
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "全网-交易总量"
        worksheet.append(["周期", "排名", "商品ID", "标题", "平台", "范围", "类目", "指标"])
        worksheet.append(["2026-07-01~2026-07-07", 1, "001234567890123456", "商品甲", "天猫", "全网", "耳机", "交易总量"])
        worksheet["D2"].hyperlink = "https://example.invalid/item/001234567890123456"
        workbook.save(path)
        workbook.close()

        payload = load_input(path)

        self.assertEqual(payload["periods"][0]["rows"][0]["product_id"], "001234567890123456")
        self.assertEqual(payload["input_controls"]["ordinary_hyperlinks_ignored"], 1)

    def test_interval_parser_does_not_hide_estimation_or_overlap(self) -> None:
        before = parse_interval("1万~2万")
        after = parse_interval("1.5万~3万")

        self.assertTrue(before["midpoint_is_estimate"])
        self.assertEqual(before["estimated_midpoint"], 15_000.0)
        self.assertEqual(after["lower"], 15_000.0)
        self.assertEqual(after["upper"], 30_000.0)

    def test_missing_and_duplicate_keys_are_blocking_with_traceable_codes(self) -> None:
        payload = {
            "periods": [
                {
                    "period": "2026-07-01~2026-07-07",
                    "platform": "天猫",
                    "scope": "全网",
                    "category": "耳机",
                    "ranking_metric": "交易总量",
                    "top_n": 4,
                    "rows": [
                        {"rank": 1, "product_id": "A"},
                        {"rank": 1, "product_id": "A"},
                        {"rank": "", "product_id": "B"},
                        {"rank": 4, "product_id": ""},
                    ],
                }
            ]
        }

        result = audit_dataset(payload)
        issue_codes = {issue["code"] for issue in result["issues"]}

        self.assertFalse(result["valid"])
        self.assertEqual(result["status"], "blocking")
        self.assertTrue(
            {
                "MISSING_PRODUCT_ID",
                "MISSING_OR_INVALID_RANK",
                "DUPLICATE_PRODUCT_ID",
                "DUPLICATE_RANK",
            }.issubset(issue_codes)
        )

    def test_comparability_islands_never_cross_platform_scope_category_or_metric(self) -> None:
        periods = normalize_payload(
            {
                "periods": [
                    {
                        "period": period,
                        "platform": platform,
                        "scope": scope,
                        "category": category,
                        "ranking_metric": metric,
                        "top_n": 3,
                        "rows": [{"rank": 1, "product_id": f"{platform}-{period}"}],
                    }
                    for platform, scope, category, metric, period in (
                        ("天猫", "全网", "耳机", "交易总量", "2026-07-01~2026-07-07"),
                        ("天猫", "全网", "耳机", "交易总量", "2026-07-08~2026-07-14"),
                        ("淘宝", "全网", "耳机", "交易总量", "2026-07-08~2026-07-14"),
                        ("天猫", "仅天猫", "耳机", "交易总量", "2026-07-08~2026-07-14"),
                        ("天猫", "全网", "音箱", "交易总量", "2026-07-08~2026-07-14"),
                        ("天猫", "全网", "耳机", "访客数", "2026-07-08~2026-07-14"),
                    )
                ]
            }
        )["periods"]

        comparisons = build_comparisons(periods)

        self.assertEqual(len(comparisons), 1)
        self.assertEqual(comparisons[0]["series_id"], "天猫 | 全网 | 耳机 | 交易总量")
        self.assertTrue(comparisons[0]["comparable"])

    def test_different_top_n_compares_only_common_k(self) -> None:
        payload = normalize_payload(
            {
                "periods": [
                    {
                        "period": "2026-07-01~2026-07-07",
                        "platform": "天猫",
                        "scope": "全网",
                        "category": "耳机",
                        "ranking_metric": "交易总量",
                        "top_n": 300,
                        "rows": [{"rank": 1, "product_id": "A"}],
                    },
                    {
                        "period": "2026-07-08~2026-07-14",
                        "platform": "天猫",
                        "scope": "全网",
                        "category": "耳机",
                        "ranking_metric": "交易总量",
                        "top_n": 100,
                        "rows": [{"rank": 1, "product_id": "A"}],
                    },
                ]
            }
        )

        comparison = build_comparisons(payload["periods"])[0]

        self.assertEqual(comparison["common_k"], 100)
        self.assertIn("different_top_n_compare_common_k_only", comparison["reasons"])

    def test_all_network_mixed_platform_rows_are_not_relabelled_as_tmall_only(self) -> None:
        payload = normalize_payload(
            {
                "periods": [
                    {
                        "period": "2026-07-01~2026-07-07",
                        "scope": "全网",
                        "category": "耳机",
                        "ranking_metric": "交易总量",
                        "rows": [
                            {"rank": 1, "product_id": "TM-1", "platform": "天猫"},
                            {"rank": 2, "product_id": "TB-1", "platform": "淘宝"},
                        ],
                    }
                ]
            }
        )

        dimensions = {(period["platform"], period["scope"]) for period in payload["periods"]}

        self.assertEqual(dimensions, {("天猫", "全网"), ("淘宝", "全网")})
        self.assertNotIn(("天猫", "仅天猫"), dimensions)

    def test_rank_text_must_be_an_entire_positive_integer_not_a_substring(self) -> None:
        payload = {
            "periods": [
                {
                    "period": "2026-07-01~2026-07-07",
                    "platform": "天猫",
                    "scope": "全网",
                    "category": "耳机",
                    "ranking_metric": "交易总量",
                    "top_n": 3,
                    "rows": [
                        {"rank": "-1", "product_id": "NEGATIVE"},
                        {"rank": "3.5", "product_id": "DECIMAL"},
                        {"rank": "abc2", "product_id": "EMBEDDED"},
                    ],
                }
            ]
        }

        normalised = normalize_payload(payload)
        result = audit_dataset(payload)
        invalid_issue = next(issue for issue in result["issues"] if issue["code"] == "MISSING_OR_INVALID_RANK")

        self.assertEqual([row["rank"] for row in normalised["periods"][0]["rows"]], [None, None, None])
        self.assertEqual(invalid_issue["evidence"]["count"], 3)
        self.assertEqual(result["status"], "blocking")
        self.assertFalse(result["valid"])

    def test_declared_top_300_with_only_contiguous_top_100_is_not_treated_as_complete_top_300(self) -> None:
        periods = []
        for label in ("2026-07-01~2026-07-07", "2026-07-08~2026-07-14"):
            periods.append(
                {
                    "period": label,
                    "platform": "天猫",
                    "scope": "全网",
                    "category": "耳机",
                    "ranking_metric": "交易总量",
                    "top_n": 300,
                    "rows": [{"rank": rank, "product_id": f"{label}-{rank}"} for rank in range(1, 101)],
                }
            )

        result = audit_dataset({"periods": periods})

        self.assertNotEqual(result["status"], "usable")
        self.assertFalse(
            any(comparison["comparable"] and comparison["common_k"] == 300 for comparison in result["comparisons"])
        )
        for comparison in result["comparisons"]:
            if comparison["comparable"]:
                self.assertLessEqual(comparison["common_k"], 100)

    def test_reversed_or_unparsed_periods_never_become_longitudinal_comparisons(self) -> None:
        cases = {
            "reversed": ("2026-07-07~2026-07-01", "2026-07-08~2026-07-14"),
            "unparsed": ("第一周", "第二周"),
        }
        for case_name, labels in cases.items():
            with self.subTest(case=case_name):
                payload = {
                    "periods": [
                        {
                            "period": label,
                            "platform": "天猫",
                            "scope": "全网",
                            "category": "耳机",
                            "ranking_metric": "交易总量",
                            "top_n": 1,
                            "rows": [{"rank": 1, "product_id": "A"}],
                        }
                        for label in labels
                    ]
                }

                result = audit_dataset(payload)

                self.assertFalse(any(comparison["comparable"] for comparison in result["comparisons"]))

    def test_audit_paths_preserves_good_file_evidence_when_another_file_is_damaged(self) -> None:
        good_path = self._write_delimited(
            ".csv",
            [
                ["周期", "排名", "商品ID", "标题", "平台", "范围", "类目", "指标"],
                ["2026-07-01~2026-07-07", 1, "GOOD", "安全商品", "天猫", "全网", "耳机", "交易总量"],
            ],
        )
        damaged_path = Path(self.temp_dir.name) / "damaged.xlsx"
        damaged_path.write_bytes(b"PK\x03\x04not-a-workbook")

        result = audit_paths([damaged_path, good_path])
        serialized = json.dumps(result, ensure_ascii=False)

        self.assertTrue(any(island.get("source_file") == good_path.name for island in result["islands"]))
        rejection_evidence = [*result["issues"], *result.get("file_rejections", [])]
        self.assertTrue(any(issue.get("code") == "DAMAGED_FILE" for issue in rejection_evidence))
        self.assertEqual(result["period_count"], 1)
        self.assertIn(good_path.name, serialized)
        self.assertNotEqual(result["status"], "usable")


if __name__ == "__main__":
    unittest.main()
