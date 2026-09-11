"""发布审查：路由意图、实际渲染和运行失败的行为测试。"""
from __future__ import annotations
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_rankings import analyze_payload, render_markdown, route_request

class ReleaseCliTests(unittest.TestCase):
    def test_negated_historical_and_quoted_tasks_do_not_route(self) -> None:
        for request in (
            "不要做利润分析，只看排名", "无需分析评价和利润，比较榜单", "利润分析不用做，只看排名",
            "上次做过利润分析，这次只比较榜单", "标题写着“利润翻倍”，请看榜单",
        ):
            with self.subTest(request=request):
                self.assertEqual(route_request(request)["handoffs"], [])

    def test_positive_later_clause_and_double_negation_are_not_lost(self) -> None:
        self.assertEqual([x["target"] for x in route_request("不要利润分析，但请分析评价")['handoffs']], ["sg-review"])
        self.assertIn("sg-profit", [x["target"] for x in route_request("不要遗漏利润分析")['handoffs']])
        self.assertIn("sg-tmads-report", [x["target"] for x in route_request("比较榜单，还要判断ROI")['handoffs']])

    def test_quick_discloses_platform_counts_missing_values_and_cleaning_basis(self) -> None:
        path = ROOT / "tests/fixtures/34-all-network-mixed/case.json"
        payload = json.loads(path.read_text(encoding="utf-8"))["input"]
        text = render_markdown(analyze_payload(payload, mode="quick"))
        for required in ("分析口径", "模式选择", "平台构成", "有效排名行", "缺失ID", "重复排名", "清洗规则", "全量", "清洗后", "不可算"):
            self.assertIn(required, text)
        self.assertIn("天猫", text)
        self.assertIn("淘宝", text)

    def test_all_blocked_rendering_exposes_repair_without_business_actions(self) -> None:
        path = ROOT / "tests/fixtures/19-duplicate-rank/case.json"
        payload = json.loads(path.read_text(encoding="utf-8"))["input"]
        result = analyze_payload(payload, mode="quick")
        text = render_markdown(result)
        self.assertEqual(result["facts"], [])
        self.assertTrue(all(action is None for action in result["actions"].values()))
        self.assertIn("修复", text)
        self.assertNotIn("小流量验证", text)

if __name__ == "__main__":
    unittest.main()
