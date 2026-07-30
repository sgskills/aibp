from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from common import detect_trigger_overlaps, find_skill_files, parse_frontmatter, read_text


FIXTURES = Path(__file__).parent / "fixtures"


class DbskillPatternRegressionTests(unittest.TestCase):
    def test_skill_narrative_standard_is_required_for_creation_and_revision(self) -> None:
        skill_text = read_text(SKILL_ROOT / "SKILL.md")
        standard = read_text(SKILL_ROOT / "references" / "skill_narrative_standard.md")

        self.assertIn("叙事与路由规范", skill_text)
        self.assertIn("references/skill_narrative_standard.md", skill_text)
        self.assertIn("一句话定位", standard)
        self.assertIn("角色、任务、交付、边界、前提", standard)
        self.assertIn("下一步不确定", standard)
        self.assertIn("不得假定安装其他 Skill", standard)

    def test_rule_applicability_review_is_required_before_final_scoring(self) -> None:
        skill_text = read_text(SKILL_ROOT / "SKILL.md")
        standard = read_text(SKILL_ROOT / "references" / "rule_applicability_review.md")

        self.assertIn("规则适用性复核", skill_text)
        self.assertIn("references/rule_applicability_review.md", skill_text)
        self.assertIn("业务 Skill", standard)
        self.assertIn("不适用", standard)

    def test_fixed_request_modes_make_p1_p2_p3_observable(self) -> None:
        skill_text = read_text(SKILL_ROOT / "SKILL.md")

        self.assertIn("## 固定请求模式", skill_text)
        self.assertIn("PLAN_ONLY", skill_text)
        self.assertIn("READ_ONLY", skill_text)
        self.assertIn("CONFIRMED_EXECUTION", skill_text)
        self.assertIn("不创建备份、不写入日志、不修改文件", skill_text)
        self.assertIn("确认计划不可追溯", skill_text)
        self.assertIn("写入清单", skill_text)

    def test_block_scalar_description_uses_content_not_indicator(self) -> None:
        content = read_text(FIXTURES / "07-block-scalar" / "skill" / "SKILL.md")
        parsed = parse_frontmatter(content)

        self.assertTrue(parsed["valid"], parsed["frontmatterErrors"])
        self.assertEqual(
            "当用户要优化 Skill 时使用。 Trigger: optimize a Skill.",
            parsed["description"],
        )

    def test_folded_scalar_description_is_joined_as_one_sentence(self) -> None:
        content = (
            "---\n"
            "name: folded-scalar\n"
            "description: >\n"
            "  Use when auditing a Skill.\n"
            "  Not for business delivery.\n"
            "---\n"
        )

        parsed = parse_frontmatter(content)

        self.assertTrue(parsed["valid"], parsed["frontmatterErrors"])
        self.assertEqual(
            "Use when auditing a Skill. Not for business delivery.",
            parsed["description"],
        )

    def test_hard_linked_skill_is_discovered_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            primary = root / "primary"
            mirror = root / "mirror"
            primary.mkdir()
            mirror.mkdir()
            source = primary / "SKILL.md"
            source.write_text(
                "---\nname: primary\ndescription: Use when auditing a Skill. Not for business delivery.\n---\n",
                encoding="utf-8",
            )
            os.link(source, mirror / "SKILL.md")

            discovered = find_skill_files(root)

            self.assertEqual(1, len(discovered))
            self.assertTrue(discovered[0].samefile(source))

    def test_distinct_files_with_same_content_remain_conflict_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            description = "Use when optimizing an existing Skill safely. Not for business delivery."
            for name in ("c", "d"):
                skill_dir = root / name
                skill_dir.mkdir()
                (skill_dir / "SKILL.md").write_text(
                    f"---\nname: {name}\ndescription: {description}\n---\n",
                    encoding="utf-8",
                )

            discovered = find_skill_files(root)
            overlaps = detect_trigger_overlaps(root / "c", "c", description, root)

            self.assertEqual(2, len(discovered))
            self.assertEqual("d", overlaps[0]["skill"])

    def test_same_name_exact_description_is_treated_as_a_mirror(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            description = "Use when optimizing an existing Skill safely. Not for business delivery."
            for name in ("canonical", "mirror"):
                skill_dir = root / name
                skill_dir.mkdir()
                (skill_dir / "SKILL.md").write_text(
                    f"---\nname: optimizer\ndescription: {description}\n---\n",
                    encoding="utf-8",
                )

            overlaps = detect_trigger_overlaps(
                root / "canonical", "optimizer", description, root
            )

            self.assertEqual([], overlaps)


if __name__ == "__main__":
    unittest.main()
