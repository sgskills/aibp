from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Mapping, Sequence
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
FIXTURES = SKILL_ROOT / "tests" / "fixtures"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from analyze_rankings import analyze_payload  # noqa: E402
from run_eval import REQUIRED_TAGS, run_evaluations  # noqa: E402


ALLOWED_CASE_KEYS = {"id", "tags", "mode", "operation", "input", "assertions"}
STABLE_RESULT_ROOTS = {
    "mode",
    "status",
    "data_quality",
    "audit",
    "comparability",
    "temporality",
    "structure",
    "trajectories",
    "sensitivity",
    "capability_gaps",
    "routes",
    "facts",
    "opportunities",
    "actions",
    "max_limitation",
    "severe_error_guards",
    "rendered_sections",
    "issues",
}
SEVERE_ERROR_KEYS = {
    "cross_island_merge",
    "single_period_as_trend",
    "out_of_window_as_delisted",
    "product_mismatch",
    "fabricated_sales_share_gmv",
    "hypothesis_as_decision",
}


def _read_case(directory_name: str) -> dict[str, object]:
    return json.loads((FIXTURES / directory_name / "case.json").read_text(encoding="utf-8"))


def _contains_key(value: object, forbidden: str) -> bool:
    if isinstance(value, Mapping):
        return any(
            str(key).lower() == forbidden or _contains_key(child, forbidden)
            for key, child in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_key(child, forbidden) for child in value)
    return False


class EvalRunnerTests(unittest.TestCase):
    def test_all_golden_cases_are_recomputed_and_pass(self) -> None:
        summary = run_evaluations(FIXTURES)
        self.assertGreaterEqual(summary["total"], 40)
        self.assertLessEqual(summary["total"], 48)
        self.assertEqual(summary["passed"], summary["total"], summary["failures"])
        self.assertEqual(summary["failed"], 0, summary["failures"])
        self.assertGreaterEqual(summary["assertions"], 100)
        self.assertEqual(summary["missing_tags"], [])
        self.assertTrue(REQUIRED_TAGS.issubset(set(summary["coverage_tags"])))

    def test_cli_json_reports_the_same_green_suite(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-B", str(SCRIPTS / "run_eval.py"), "--format", "json"],
            cwd=SKILL_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        summary = json.loads(completed.stdout)
        self.assertEqual(summary["total"], 48)
        self.assertEqual(summary["passed"], 48)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(summary["failures"], [])

    def test_fixture_contract_uses_only_machine_assertions(self) -> None:
        paths = sorted(FIXTURES.glob("*/case.json"))
        self.assertEqual(len(paths), 48)
        for path in paths:
            case = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(set(case), ALLOWED_CASE_KEYS, path)
            self.assertFalse(_contains_key(case, "expected"), path)
            self.assertIn(case["operation"], {"analyze", "corrupted_file"}, path)
            for assertion in case["assertions"]:
                root = str(assertion["path"]).split(".", maxsplit=1)[0]
                self.assertIn(root, STABLE_RESULT_ROOTS, (path, assertion))
            periods = case["input"].get("periods", [])
            row_count = sum(len(period.get("rows", [])) for period in periods)
            self.assertLessEqual(row_count, 16, path)

    def test_quick_and_deep_modes_share_deterministic_evidence(self) -> None:
        quick_case = _read_case("04-two-explicit-quick")
        deep_case = _read_case("05-two-explicit-deep")
        self.assertEqual(quick_case["input"], deep_case["input"])
        quick = analyze_payload(quick_case["input"], mode="quick")
        deep = analyze_payload(deep_case["input"], mode="deep")
        self.assertEqual(quick["mode"], "quick")
        self.assertEqual(deep["mode"], "deep")
        for key in (
            "status",
            "data_quality",
            "audit",
            "comparability",
            "temporality",
            "structure",
            "trajectories",
            "sensitivity",
            "capability_gaps",
            "routes",
            "actions",
            "max_limitation",
            "severe_error_guards",
        ):
            self.assertEqual(quick[key], deep[key], key)

    def test_every_analyze_case_keeps_six_severe_errors_at_zero(self) -> None:
        for path in sorted(FIXTURES.glob("*/case.json")):
            case = json.loads(path.read_text(encoding="utf-8"))
            if case["operation"] != "analyze":
                continue
            result = analyze_payload(case["input"], mode=case["mode"])
            guards = result["severe_error_guards"]
            self.assertEqual(set(guards), SEVERE_ERROR_KEYS, path)
            self.assertTrue(all(value == 0 for value in guards.values()), (path, guards))

    def test_runner_rejects_a_forbidden_ground_truth_key(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sg-toplist-runner-contract-") as temp_dir:
            case_dir = Path(temp_dir) / "forbidden-ground-truth"
            case_dir.mkdir()
            case = {
                "id": "forbidden-ground-truth",
                "tags": ["single_period"],
                "mode": "quick",
                "operation": "analyze",
                "input": {"periods": [], "expected": {"status": "PASS"}},
                "assertions": [{"path": "mode", "op": "eq", "value": "quick"}],
            }
            (case_dir / "case.json").write_text(
                json.dumps(case, ensure_ascii=False), encoding="utf-8"
            )
            summary = run_evaluations(Path(temp_dir))
            self.assertTrue(
                any("fixture must not contain an expected field" in item for item in summary["failures"]),
                summary["failures"],
            )


if __name__ == "__main__":
    unittest.main()
