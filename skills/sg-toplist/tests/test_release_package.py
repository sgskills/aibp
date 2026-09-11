"""AIBP 迁入资产、合成样例和发布边界的本地可复跑契约。"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_rankings import analyze_paths


class ReleasePackageTests(unittest.TestCase):
    def test_required_runtime_assets_exist_without_standalone_release_docs(self) -> None:
        for relative in (
            "references/intent-contract.json",
            "tests/samples/sample-week-1.csv",
            "tests/samples/sample-week-2.csv",
            "scripts/run_analysis.py",
            "scripts/maintenance_check.py",
        ):
            with self.subTest(relative=relative):
                self.assertTrue((ROOT / relative).is_file())
        for forbidden in ("README.md", "README.rst", "LICENSE", "MAINTENANCE.md", "RELEASE-CHECKLIST.md", "examples"):
            with self.subTest(forbidden=forbidden):
                self.assertFalse((ROOT / forbidden).exists())

    def test_aibp_root_license_is_the_release_source(self) -> None:
        repository_license = ROOT.parents[1] / "LICENSE"
        self.assertTrue(repository_license.is_file())
        self.assertIn("SGSkills Internal Use License 1.0", repository_license.read_text(encoding="utf-8"))

    def test_documented_examples_run_in_quick_and_deep_modes(self) -> None:
        paths = [str(ROOT / "tests/samples/sample-week-1.csv"), str(ROOT / "tests/samples/sample-week-2.csv")]
        quick = analyze_paths(paths[:1], mode="quick")
        deep = analyze_paths(paths, mode="deep")
        self.assertEqual((quick["status"], quick["mode"]), ("analyzed", "quick"))
        self.assertEqual((deep["status"], deep["mode"]), ("analyzed", "deep"))
        self.assertEqual(deep["trajectories"]["summary"]["matched_count"], 4)
        self.assertEqual(sum(deep["severe_error_guards"].values()), 0)

    def test_release_text_has_no_private_absolute_paths_or_real_workbook_names(self) -> None:
        # 拆开测试常量，避免扫描器把测试自身误报为候选泄露。
        forbidden = (
            "C:" + "\\Users\\",
            "E:" + "\\+Skills",
            "E:" + "\\+AI",
            "市场排行_" + "商品_餐具_碗_2025",
        )
        offenders = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".rst", ".json", ".yaml", ".py", ".csv", ""}:
                continue
            text = path.read_text(encoding="utf-8")
            if any(term in text for term in forbidden):
                offenders.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
