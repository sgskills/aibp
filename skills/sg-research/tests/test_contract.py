from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import run_eval  # noqa: E402


class SkillStructureTests(unittest.TestCase):
    def test_structure_is_self_contained_and_exact(self) -> None:
        self.assertEqual([], run_eval.validate_structure())

    def test_manifest_freezes_twenty_seven_unique_categories(self) -> None:
        self.assertEqual(27, len(run_eval.CASE_MANIFEST))
        categories = [spec["category"] for spec in run_eval.CASE_MANIFEST.values()]
        self.assertEqual(27, len(set(categories)))

    def test_all_contract_markers_have_a_declared_reference(self) -> None:
        for contract, filename in run_eval.CONTRACT_FILES.items():
            text = (SKILL_ROOT / "references" / filename).read_text(encoding="utf-8")
            self.assertIn(f"[{contract}]", text)


class GoldenSetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = run_eval.load_cases()
        cls.by_id = {case["id"]: case for case in cls.cases}

    def test_case_ids_match_frozen_manifest(self) -> None:
        self.assertEqual(set(run_eval.CASE_MANIFEST), set(self.by_id))

    def test_every_case_matches_route_and_contract_manifest(self) -> None:
        results = [run_eval.evaluate_case(case) for case in self.cases]
        failures = {
            result["id"]: result["failures"] for result in results if not result["passed"]
        }
        self.assertEqual({}, failures)

    def test_router_priority_is_calculated_not_read_from_expectation(self) -> None:
        expected_routes = {
            "GS-001-explicit-pack-wins": "research_task_pack",
            "GS-002-offline-switch": "research_task_pack",
            "GS-003-online-report": "research_execution",
            "GS-004-both-online": "research_execution_plus_task_pack",
            "GS-006-execution-interrupted": "research_degraded_bundle",
            "GS-007-simple-fact": "non_trigger",
        }
        for case_id, expected_route in expected_routes.items():
            with self.subTest(case_id=case_id):
                self.assertEqual(expected_route, run_eval.calculate_route(self.by_id[case_id]))

    def test_non_trigger_cases_have_no_report_or_task_pack_contracts(self) -> None:
        forbidden = {"REPORT-SECTIONS", "TASK-PACK-SECTIONS", "PARTIAL-DELIVERY"}
        non_trigger_ids = {
            "GS-007-simple-fact",
            "GS-008-pure-summary",
            "GS-009-translation",
            "GS-010-ordinary-writing",
        }
        for case_id in non_trigger_ids:
            with self.subTest(case_id=case_id):
                contracts = set(self.by_id[case_id]["expected"]["contracts"])
                self.assertTrue(contracts.isdisjoint(forbidden))

    def test_offline_and_degraded_routes_keep_distinct_contracts(self) -> None:
        offline = set(self.by_id["GS-002-offline-switch"]["expected"]["contracts"])
        degraded = set(
            self.by_id["GS-006-execution-interrupted"]["expected"]["contracts"]
        )
        self.assertIn("OFFLINE-DISCLOSURE", offline)
        self.assertNotIn("PARTIAL-DELIVERY", offline)
        self.assertIn("PARTIAL-DELIVERY", degraded)
        self.assertIn("TASK-PACK-SECTIONS", degraded)

    def test_final_authority_and_same_lineage_cases_are_paired(self) -> None:
        final_authority = self.by_id["GS-014-final-authority"]
        same_lineage = self.by_id["GS-013-same-lineage"]
        self.assertEqual("research_execution", run_eval.calculate_route(final_authority))
        self.assertEqual("research_degraded_bundle", run_eval.calculate_route(same_lineage))
        self.assertIn("FINAL-AUTHORITY", final_authority["expected"]["contracts"])
        self.assertIn("SOURCE-INDEPENDENCE", same_lineage["expected"]["contracts"])

    def test_neighboring_aibp_tasks_have_explicit_handoffs(self) -> None:
        handoff_ids = {
            "GS-025-ceo-vision-handoff",
            "GS-026-mece-handoff",
            "GS-027-specialist-handoff",
        }
        for case_id in handoff_ids:
            with self.subTest(case_id=case_id):
                case = self.by_id[case_id]
                self.assertEqual("non_trigger", run_eval.calculate_route(case))
                self.assertIn(
                    "ROUTE-SPECIALIST-HANDOFF", case["expected"]["contracts"]
                )


class RunnerInterfaceTests(unittest.TestCase):
    def test_json_interface_reports_exact_recomputed_totals(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-B", str(SCRIPTS_DIR / "run_eval.py"), "--format", "json"],
            cwd=SKILL_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(0, completed.returncode, completed.stderr or completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(27, payload["total"])
        self.assertEqual(payload["total"], payload["passed"])
        self.assertEqual(0, payload["failed"])
        self.assertEqual(100.0, payload["passRate"])
        self.assertEqual(payload["total"], len(payload["results"]))
        self.assertTrue(all(result["passed"] is True for result in payload["results"]))
        self.assertIn("no live research", payload["scope"])


if __name__ == "__main__":
    unittest.main()
