from __future__ import annotations

import hashlib
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


class PerformanceContractTests(unittest.TestCase):
    def test_fast_path_is_default_and_safety_is_not_skipped(self) -> None:
        content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("快速路径（默认）", content)
        self.assertIn("不主动联网核验", content)
        self.assertIn("最多 1 个备选", content)
        for required in ("真实性", "硬规则", "必留/禁用", "来源映射", "profile 隔离", "title_guard.py"):
            self.assertIn(required, content)

    def test_fast_output_hides_internal_validation_details(self) -> None:
        content = (SKILL_ROOT / "references" / "output-contract.md").read_text(encoding="utf-8")
        self.assertIn("快速交付（默认）", content)
        self.assertIn("最多 3 个短要点", content)
        self.assertIn("不输出 profile 版本、除上述精确字节数外的逐项长度测量、完整校验 JSON", content)
        self.assertIn("深度交付（按需）", content)

    def test_migrated_golden_cases_are_unchanged(self) -> None:
        fixture = SKILL_ROOT / "tests" / "fixtures" / "golden_cases.json"
        canonical = fixture.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest().upper()
        self.assertEqual("FC6587DB195581D5EA11BED3CA8B0CC5CCB3E41EB45674628C8C338D71EF92CA", digest)


if __name__ == "__main__":
    unittest.main()
