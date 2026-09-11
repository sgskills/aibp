from __future__ import annotations

import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from run_eval import run_all  # noqa: E402


class GoldenEvalTests(unittest.TestCase):
    def test_golden_suite_is_frozen_broad_and_green(self) -> None:
        result = run_all()
        self.assertGreaterEqual(result["total"], 24)
        self.assertEqual(0, result["failed"])
        self.assertEqual(0, result["skipped"])
        self.assertEqual(result["total"], result["passed"])

    def test_required_coverage_tags_exist(self) -> None:
        result = run_all()
        required = {
            "资料齐全",
            "资料极少",
            "错类榜单",
            "虚假属性热词",
            "竞品品牌IP",
            "单品",
            "套装",
            "不可比7天30天",
            "四平台档案",
            "有无空格两用户隔离",
            "必留词",
            "禁用词",
            "英文数字型号",
            "词组与通顺冲突",
            "候选不足",
            "撤销偏好",
            "提示注入",
            "相邻Skill路由",
        }
        self.assertTrue(required.issubset(set(result["coverage_tags"])))

    def test_acceptance_metrics_are_exact(self) -> None:
        result = run_all()
        self.assertEqual(
            {
                "无来源核心词": 0,
                "未证实属性": 0,
                "必留覆盖率": 100.0,
                "禁用命中": 0,
                "激活规则合规率": 100.0,
                "跨profile泄漏": 0,
            },
            result["acceptance"],
        )


if __name__ == "__main__":
    unittest.main()
