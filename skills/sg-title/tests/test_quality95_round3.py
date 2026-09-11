from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from title_guard import load_profiles, route_request, validate_title


def base_request() -> dict:
    return {
        "platform": "jd",
        "title": "M1蓝牙音箱",
        "title_core_terms": ["M1", "蓝牙音箱"],
        "keyword_sources": [
            {"term": "M1", "status": "confirmed", "source": "用户明确型号"},
            {"term": "蓝牙音箱", "status": "confirmed", "source": "用户明确商品名"},
        ],
    }


class Round3SafetyTests(unittest.TestCase):
    def test_undeclared_import_and_child_risks_fail_closed(self) -> None:
        request = base_request()
        request["title"] = "德国进口儿童M1蓝牙音箱"
        result = validate_title(request)
        self.assertFalse(result["allowed"])
        self.assertIn("high_risk_evidence_missing", {item["code"] for item in result["errors"]})

    def test_phantom_core_term_cannot_stand_in_for_title_coverage(self) -> None:
        request = base_request()
        request["title_core_terms"].append("德国进口")
        request["keyword_sources"].append(
            {"term": "德国进口", "status": "confirmed", "source": "不存在于标题的幽灵映射"}
        )
        result = validate_title(request)
        self.assertFalse(result["allowed"])
        self.assertIn("core_term_not_in_title", {item["code"] for item in result["errors"]})

    def test_non_test_profile_without_freshness_is_rejected(self) -> None:
        profiles = copy.deepcopy(load_profiles())
        profiles["platforms"]["custom-live"] = {
            "display_name": "custom-live",
            "version": "1",
            "scope": "真实运行档案",
            "status": "verified",
            "sources": [],
            "length": {"metric": "codepoints", "min": None, "max": None, "enforcement": "unknown"},
            "space_policy": {"value": "forbid", "enforcement": "hard"},
            "symbol_policy": {"forbidden": [], "enforcement": "unknown"},
            "max_term_repetitions": {"value": 1, "enforcement": "advisory"},
        }
        request = base_request()
        request["platform"] = "custom-live"
        result = validate_title(request, profiles)
        self.assertFalse(result["allowed"])
        self.assertIn("platform_schema_invalid", {item["code"] for item in result["errors"]})

    def test_platform_specific_title_phrase_survives_mixed_route(self) -> None:
        result = route_request("优化京东标题，同时诊断广告投放ROI")
        self.assertTrue(result["title_task"])
        self.assertIn("sg-tmads-report", result["adjacent_routes"])


if __name__ == "__main__":
    unittest.main()
