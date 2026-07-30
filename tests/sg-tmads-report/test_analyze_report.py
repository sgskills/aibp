from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "sg-tmads-report"
    / "scripts"
    / "analyze_report.py"
)
SPEC = importlib.util.spec_from_file_location("sg_tmads_analyze_report", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"无法加载脚本：{SCRIPT_PATH}")
ANALYZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYZER)


def valid_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "日期": "2026-07-01",
        "计划ID": "p-1",
        "计划名称": "测试计划",
        "展现量": 1000,
        "点击量": 100,
        "花费": 200,
        "总成交笔数": 10,
        "成交人数": 8,
        "总成交金额": 800,
    }
    row.update(overrides)
    return row


def payload(
    row: dict[str, object],
    assumptions: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "request": {"goal": "审计投产"},
        "assumptions": assumptions or {},
        "datasets": [
            {
                "name": "直通车明细",
                "report_type": "直通车",
                "attribution_window": "30d",
                "rows": [row],
            }
        ],
    }


class CsvSafetyTests(unittest.TestCase):
    def test_duplicate_headers_fail_before_dictionary_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "duplicate.csv"
            csv_path.write_text("日期,花费,花费\n2026-07-01,10,20\n", encoding="utf-8")

            with self.assertRaisesRegex(ANALYZER.InputFormatError, "列 2, 3"):
                ANALYZER._load_input(csv_path, "", "unknown", "unknown")

    def test_normalized_duplicate_headers_also_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "normalized-duplicate.csv"
            csv_path.write_text(
                "日期,花费,花 费\n2026-07-01,10,20\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ANALYZER.InputFormatError, "重复表头"):
                ANALYZER._load_input(csv_path, "", "unknown", "unknown")


class FieldValidationTests(unittest.TestCase):
    def assert_invalid_field(self, field_name: str, value: object) -> None:
        result = ANALYZER.analyze_payload(payload(valid_row(**{field_name: value})))
        detail = result["islands"][0]["details"][0]
        self.assertEqual("invalid_value", detail["excluded_reason"])
        self.assertTrue(result["audit"]["dataset_inventory"][0]["invalid_rows"])

    def test_negative_core_value_is_excluded(self) -> None:
        self.assert_invalid_field("花费", -1)

    def test_percentage_core_value_is_not_misread_as_decimal(self) -> None:
        self.assert_invalid_field("花费", "40%")

    def test_fractional_count_is_excluded(self) -> None:
        self.assert_invalid_field("点击量", 1.5)

    def test_non_numeric_core_value_is_excluded(self) -> None:
        self.assert_invalid_field("总成交金额", "八百")


class PrivacyAndScopeTests(unittest.TestCase):
    def test_unknown_raw_values_are_absent_by_default(self) -> None:
        row = valid_row(手机号="13800138000", 内部备注="secret-note")
        result = ANALYZER.analyze_payload(payload(row))
        serialized = json.dumps(result, ensure_ascii=False)

        self.assertNotIn("13800138000", serialized)
        self.assertNotIn("secret-note", serialized)
        self.assertNotIn("source_values", serialized)

    def test_include_raw_uses_mapped_field_allowlist(self) -> None:
        row = valid_row(手机号="13800138000", 内部备注="secret-note")
        result = ANALYZER.analyze_payload(payload(row), include_raw=True)
        source_values = result["islands"][0]["details"][0]["source_values"]

        self.assertIn("花费", source_values)
        self.assertNotIn("手机号", source_values)
        self.assertNotIn("内部备注", source_values)
        self.assertNotIn("secret-note", json.dumps(source_values, ensure_ascii=False))

    def test_financial_metrics_require_explicit_scope(self) -> None:
        result = ANALYZER.analyze_payload(
            payload(
                valid_row(),
                {"gross_margin_rate": "40%", "refund_amount_rate": "10%"},
            )
        )

        self.assertEqual("unconfirmed", result["assumptions"]["scope"])
        self.assertFalse(result["assumptions"]["financial_calculation_enabled"])
        self.assertNotIn(
            "promotion_contribution_profit",
            result["islands"][0]["metrics"],
        )

    def test_store_wide_scope_enables_auditable_financial_metrics(self) -> None:
        result = ANALYZER.analyze_payload(
            payload(
                valid_row(),
                {
                    "gross_margin_rate": "40%",
                    "refund_amount_rate": "10%",
                    "scope": "store-wide",
                },
            )
        )

        self.assertEqual("store-wide", result["assumptions"]["scope"])
        self.assertTrue(result["assumptions"]["financial_calculation_enabled"])
        self.assertAlmostEqual(
            88.0,
            result["islands"][0]["metrics"]["promotion_contribution_profit"],
        )


class OutputSafetyTests(unittest.TestCase):
    def test_atomic_writer_refuses_silent_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "report.json"
            ANALYZER._write_text(output_path, "first")
            self.assertEqual("first", output_path.read_text(encoding="utf-8"))

            with self.assertRaisesRegex(ANALYZER.InputFormatError, "默认拒绝覆盖"):
                ANALYZER._write_text(output_path, "second")

            ANALYZER._write_text(output_path, "second", force=True)
            self.assertEqual("second", output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
