from __future__ import annotations

import re
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
FIXED_DESCRIPTION = (
    "把一份或多份天猫市场商品排名表转化为可追溯的数据审计、榜单结构与跨期变化、市场机会假设，"
    "以及打品、研发和主推方向的运营建议。 触发方式：用户提供单期或连续周期商品排名并要求极速分析或深度"
    "分析时；不用于抓取平台数据、广告投放、利润诊断、评价洞察，也不把单期榜单、名次变化或标题"
    "词频当作市场趋势、销量份额或因果证据。"
)
REQUIRED_FILES = {
    "SKILL.md",
    "agents/openai.yaml",
    "references/data-contract.md",
    "references/comparability-and-matching.md",
    "references/ranking-metrics.md",
    "references/opportunity-and-action.md",
    "references/output-contract.md",
    "references/routing-and-risk.md",
    "scripts/audit_input.py",
    "scripts/entity_matcher.py",
    "scripts/ranking_engine.py",
    "scripts/analyze_rankings.py",
    "scripts/run_eval.py",
}


def _frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n", text, re.DOTALL)
    if match is None:
        raise AssertionError("SKILL.md must begin with YAML frontmatter")
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            raise AssertionError(f"invalid frontmatter line: {line}")
        fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


class SkillContractTests(unittest.TestCase):
    def test_required_files_exist(self) -> None:
        actual = {
            path.relative_to(SKILL_ROOT).as_posix()
            for path in SKILL_ROOT.rglob("*")
            if path.is_file()
        }
        self.assertTrue(REQUIRED_FILES.issubset(actual), sorted(REQUIRED_FILES - actual))

    def test_frontmatter_is_future_aibp_compatible(self) -> None:
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        fields = _frontmatter(text)
        self.assertEqual(set(fields), {"name", "description", "license"})
        self.assertEqual(fields["name"], "sg-toplist")
        self.assertEqual(fields["description"], FIXED_DESCRIPTION)
        self.assertEqual(fields["license"], "SGSkills Internal Use License 1.0")
        self.assertLessEqual(len(text.splitlines()), 500)
        self.assertNotIn("TODO", text)

    def test_openai_yaml_strings_and_identity(self) -> None:
        text = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn('display_name: "竞品排名分析师"', text)
        description_match = re.search(r'^\s*short_description:\s*"([^"]+)"\s*$', text, re.MULTILINE)
        self.assertIsNotNone(description_match)
        short_description = description_match.group(1)
        self.assertGreaterEqual(len(short_description), 25)
        self.assertLessEqual(len(short_description), 64)
        prompt_match = re.search(r'^\s*default_prompt:\s*"([^"]+)"\s*$', text, re.MULTILINE)
        self.assertIsNotNone(prompt_match)
        self.assertIn("$sg-toplist", prompt_match.group(1))
        for line in text.splitlines():
            if ":" not in line or not line.strip() or line.rstrip().endswith(":"):
                continue
            self.assertRegex(line, r':\s*".*"\s*$', line)

    def test_skill_root_has_no_forbidden_artifacts(self) -> None:
        forbidden_names = {"README.md", "CHANGELOG.md", "assets"}
        actual_names = {path.name for path in SKILL_ROOT.iterdir()}
        self.assertTrue(forbidden_names.isdisjoint(actual_names))
        forbidden_extensions = {".xlsx", ".xls", ".xlsm", ".html", ".htm"}
        offenders = [
            path.relative_to(SKILL_ROOT).as_posix()
            for path in SKILL_ROOT.rglob("*")
            if path.is_file() and path.suffix.lower() in forbidden_extensions
        ]
        self.assertEqual(offenders, [])

    def test_all_references_are_routed_from_skill(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        for name in (
            "data-contract.md",
            "comparability-and-matching.md",
            "ranking-metrics.md",
            "opportunity-and-action.md",
            "output-contract.md",
            "routing-and-risk.md",
        ):
            self.assertIn(f"references/{name}", skill_text)


if __name__ == "__main__":
    unittest.main()
