from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from title_guard import load_profiles, measure_title, scope_matches, validate_title  # noqa: E402


def eval_profiles() -> dict[str, object]:
    base = load_profiles()
    override = json.loads(
        (SKILL_ROOT / "tests" / "fixtures" / "platform-overrides.json").read_text(
            encoding="utf-8"
        )
    )
    base["platforms"].update(override["platforms"])
    return base


class TitleGuardTests(unittest.TestCase):
    def test_length_metrics_are_deterministic(self) -> None:
        self.assertEqual(6, measure_title("水杯A1", "legacy_weighted_bytes"))
        self.assertEqual(4, measure_title("水杯A1", "codepoints"))
        self.assertEqual(8, measure_title("水杯A1", "utf8_bytes"))

    def test_hard_rules_block_length_space_and_symbol(self) -> None:
        request = {
            "platform": "fixture-marketplace",
            "title": "超长 陶瓷杯★马克杯测试标题",
            "title_core_terms": ["马克杯"],
            "keyword_sources": [
                {"term": "马克杯", "status": "confirmed", "source": "product_name"}
            ],
        }
        result = validate_title(request, eval_profiles())
        codes = {item["code"] for item in result["errors"]}
        self.assertFalse(result["allowed"])
        self.assertIn("space_forbidden", codes)
        self.assertIn("symbol_forbidden", codes)
        self.assertIn("length_above_max", codes)

    def test_owner_tmall_operating_length_blocks_short_title(self) -> None:
        request = {
            "platform": "tmall",
            "title": "陶瓷马克杯",
            "title_core_terms": ["马克杯"],
            "keyword_sources": [
                {"term": "马克杯", "status": "confirmed", "source": "product_name"}
            ],
        }
        result = validate_title(request, eval_profiles())
        self.assertFalse(result["allowed"])
        self.assertIn(
            "length_below_min",
            {item["code"] for item in result["errors"]},
        )
        self.assertEqual("owner_operating_default", result["measurements"]["length_policy_source"])

    def test_unverified_and_unsourced_terms_are_blocked(self) -> None:
        request = {
            "platform": "jd",
            "title": "陶瓷碗景德镇",
            "title_core_terms": ["陶瓷碗", "景德镇"],
            "keyword_sources": [
                {"term": "陶瓷碗", "status": "confirmed", "source": "product_name"},
                {"term": "景德镇", "status": "pending", "source": "hotword"},
            ],
            "unverified_attributes": ["景德镇"],
        }
        result = validate_title(request, eval_profiles())
        codes = {item["code"] for item in result["errors"]}
        self.assertEqual(
            {"unsupported_core_term", "unverified_attribute_hit"},
            codes,
        )

    def test_profile_requires_exact_scope(self) -> None:
        self.assertTrue(
            scope_matches(
                {"platform": "tmall", "store": "a", "category": "服饰"},
                {"platform": "天猫", "store": "a", "category": "服饰"},
            )
        )
        self.assertFalse(
            scope_matches(
                {"platform": "tmall", "store": "a", "category": "服饰"},
                {"platform": "天猫", "store": "b", "category": "服饰"},
            )
        )
        self.assertFalse(
            scope_matches(
                {"platform": "tmall", "store": "a"},
                {"platform": "天猫", "store": "a", "category": "服饰"},
            )
        )

    def test_cli_reads_stdin_and_returns_json(self) -> None:
        request = {
            "platform": "fixture-marketplace",
            "title": "陶瓷马克杯",
            "title_core_terms": ["马克杯"],
            "keyword_sources": [
                {"term": "马克杯", "status": "confirmed", "source": "product_name"}
            ],
        }
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "title_guard.py"),
                "--profiles",
                str(SKILL_ROOT / "tests" / "fixtures" / "platform-overrides.json"),
                "--format",
                "json",
            ],
            input=json.dumps(request, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr or completed.stdout)
        self.assertTrue(json.loads(completed.stdout)["allowed"])


if __name__ == "__main__":
    unittest.main()
