from __future__ import annotations

import ast
import json
import os
import re
import unittest
from pathlib import Path


ROOT = Path(os.environ.get("SG_REVIEW_ROOT", Path(__file__).resolve().parents[1])).resolve()


class SkillContractTests(unittest.TestCase):
    def test_required_runtime_files_exist(self) -> None:
        required = [
            "SKILL.md",
            "agents/openai.yaml",
            "references/data-intake.md",
            "references/review-method.md",
            "references/output-contract.md",
            "references/business-report.md",
            "references/v11-alignment.md",
            "assets/report-template.md",
            "scripts/review_stats.py",
            "scripts/report_contract.py",
            "scripts/run_eval.py",
            "tests/golden/cases.json",
        ]
        missing = [path for path in required if not (ROOT / path).is_file()]
        self.assertEqual(missing, [])

    def test_skill_frontmatter_has_aibp_required_fields(self) -> None:
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        end = text.find("\n---\n", 4)
        self.assertGreater(end, 4)
        frontmatter = text[4:end]
        keys = re.findall(r"^([A-Za-z_][A-Za-z0-9_-]*):", frontmatter, re.M)
        self.assertEqual(keys, ["name", "description", "license"])
        self.assertRegex(frontmatter, r"(?m)^name: sg-review$")
        self.assertRegex(frontmatter, r"(?m)^license: SGSkills Internal Use License 1\.0$")
        for phrase in (
            "把用户提供或合法导出的电商评价转化为",
            "触发方式",
            "不用于抓取商品链接",
            "推广报表",
            "完整市场研究",
        ):
            self.assertIn(phrase, frontmatter)

    def test_openai_interface_contract(self) -> None:
        text = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        display = re.search(r'^\s*display_name:\s*"([^"]+)"\s*$', text, re.M)
        short = re.search(r'^\s*short_description:\s*"([^"]+)"\s*$', text, re.M)
        prompt = re.search(r'^\s*default_prompt:\s*"([^"]+)"\s*$', text, re.M)
        self.assertIsNotNone(display)
        self.assertEqual(display.group(1), "电商评价分析")
        self.assertIsNotNone(short)
        self.assertGreaterEqual(len(short.group(1)), 25)
        self.assertLessEqual(len(short.group(1)), 64)
        self.assertIsNotNone(prompt)
        self.assertIn("$sg-review", prompt.group(1))

    def test_references_cover_hard_boundaries(self) -> None:
        combined = "\n".join(
            (ROOT / "references" / name).read_text(encoding="utf-8")
            for name in ("data-intake.md", "review-method.md", "output-contract.md")
        )
        for phrase in (
            "评价覆盖率 = 提及该主题的不同评价数 ÷ 全部有效评价数",
            "提及份额 = 该主题提及次数 ÷ 当前模块全部主题提及次数",
            "单点信号",
            "疑似重复",
            "产品、Listing、渠道或服务",
            "证据索引",
            "只有链接",
            "comparison_basis_sha256",
            "--force",
            "内部编号",
            "【数据不足，以下为推断性分析】",
            "隐藏商业机会",
            "为什么不只是整改",
            "停止条件",
        ):
            self.assertIn(phrase, combined)

    def test_golden_set_has_required_categories(self) -> None:
        payload = json.loads((ROOT / "tests" / "golden" / "cases.json").read_text(encoding="utf-8"))
        cases = payload["cases"]
        ids = [case["id"] for case in cases]
        categories = {case["category"] for case in cases}
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(categories), 12)
        expected = {
            "完整数据", "缺星级日期SKU", "少样本", "重复模板", "星级与文本冲突",
            "跨品类泛化", "SKU样本失衡", "不可比竞品", "链接不可访问",
            "提示注入与隐私", "只有汇总无原文", "非评价任务",
        }
        self.assertTrue(expected.issubset(categories))

    def test_fixtures_are_explicitly_synthetic_and_have_no_obvious_pii(self) -> None:
        phone = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
        email = re.compile(r"[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
        for path in (ROOT / "tests" / "fixtures").iterdir():
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            self.assertIn("合成", text, path.name)
            self.assertIsNone(phone.search(text), path.name)
            self.assertIsNone(email.search(text), path.name)

    def test_scripts_do_not_import_disallowed_runtime_dependencies(self) -> None:
        disallowed = {"pandas", "openpyxl", "yaml", "requests", "numpy"}
        imported: set[str] = set()
        for path in (ROOT / "scripts").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
        self.assertEqual(imported & disallowed, set())

    def test_no_extraneous_docs_or_archives(self) -> None:
        # Approved task-0 contract migration: minimal root release documents only.
        allowed_release_docs = {"README.md", "CHANGELOG.md", "SKILL.patch.md"}
        forbidden_names = {"INSTALLATION_GUIDE.md", "QUICK_REFERENCE.md"}
        found = [
            str(path.relative_to(ROOT)) for path in ROOT.rglob("*")
            if path.is_file() and (
                path.name in forbidden_names
                or (path.name in allowed_release_docs and path.parent != ROOT
                    and ".work" not in path.relative_to(ROOT).parts)
                or (path.parent == ROOT and path.suffix.lower() == ".md"
                    and path.name not in allowed_release_docs | {"SKILL.md"})
                or (path.parent == ROOT and path.name.upper().startswith(("LICENSE", "COPYING", "VERSION")))
            )
        ]
        archives = [str(path.relative_to(ROOT)) for path in ROOT.rglob("*") if path.suffix.lower() in {".zip", ".7z", ".rar"}]
        self.assertEqual(found, [])
        self.assertEqual(archives, [])


if __name__ == "__main__":
    unittest.main()
