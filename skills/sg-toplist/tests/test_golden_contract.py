from __future__ import annotations

import json
import unittest
from collections.abc import Mapping, Sequence
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = SKILL_ROOT / "tests" / "fixtures"
REQUIRED_TAGS = {
    "single_period",
    "two_periods",
    "multi_period",
    "incomparable_island",
    "different_top_n",
    "missing_id",
    "duplicate_id",
    "missing_rank",
    "duplicate_rank",
    "link_reuse",
    "same_title_different_id",
    "entry",
    "platform_new_listed",
    "reentry",
    "exit_window",
    "interval_overlap",
    "missing_price",
    "missing_amount",
    "pollution",
    "all_network",
    "tmall_only",
    "own_product",
    "mode_consistency",
    "routing",
    "cell_injection",
    "corrupted_file",
}


def _contains_key(value: object, forbidden: str) -> bool:
    if isinstance(value, Mapping):
        return any(
            str(key).lower() == forbidden or _contains_key(child, forbidden)
            for key, child in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_key(child, forbidden) for child in value)
    return False


class GoldenContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case_paths = sorted(FIXTURES.glob("*/case.json"))
        self.cases = [json.loads(path.read_text(encoding="utf-8")) for path in self.case_paths]

    def test_at_least_36_directory_scoped_cases(self) -> None:
        self.assertGreaterEqual(len(self.case_paths), 36)
        for path in self.case_paths:
            self.assertEqual(path.name, "case.json")
            self.assertEqual(path.parent.parent, FIXTURES)

    def test_cases_are_unique_and_have_assertions(self) -> None:
        ids = [case.get("id") for case in self.cases]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(isinstance(case.get("assertions"), list) for case in self.cases))
        self.assertTrue(all(case["assertions"] for case in self.cases))

    def test_required_coverage_tags_are_present(self) -> None:
        tags = {
            tag
            for case in self.cases
            for tag in case.get("tags", [])
            if isinstance(tag, str)
        }
        self.assertEqual(REQUIRED_TAGS - tags, set())

    def test_fixtures_cannot_embed_expected_output(self) -> None:
        offenders = [case.get("id") for case in self.cases if _contains_key(case, "expected")]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
