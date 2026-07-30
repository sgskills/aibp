from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
HEALTH_CHECK = SKILL_ROOT / "scripts" / "health_check.py"
RUN_EVAL = SKILL_ROOT / "scripts" / "run_eval.py"
AUDIT_DESCRIPTION = SKILL_ROOT / "scripts" / "audit_description.py"


def run_health_check(skill_dir: Path) -> dict[str, object]:
    completed = subprocess.run(
        [
            sys.executable,
            str(HEALTH_CHECK),
            str(skill_dir),
            "--format",
            "json",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if not completed.stdout:
        raise AssertionError(
            f"health_check 未输出 JSON，exit={completed.returncode}: {completed.stderr}"
        )
    return json.loads(completed.stdout)


class SkillPackageTests(unittest.TestCase):
    def test_skill_name_is_sg_skill_optimizer(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: sg-skill-optimizer", skill_text)
        self.assertNotIn("name: skill-optimizer\n", skill_text)

    def test_description_front_loads_trigger_within_140_characters(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        match = re.search(r"^description:\s*\|\n\s*(.+)$", skill_text, re.MULTILINE)
        self.assertIsNotNone(match)
        description = match.group(1).strip()
        first_sentence = description.split("。", maxsplit=1)[0] + "。"
        self.assertIn("既有 Agent Skill", first_sentence)
        self.assertLessEqual(len(first_sentence), 140)

    def test_business_skill_template_and_numbered_steps_are_recognized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "assets").mkdir()
            (skill_dir / "references").mkdir()
            (skill_dir / "assets" / "report-template.html").write_text(
                "<html></html>", encoding="utf-8"
            )
            (skill_dir / "references" / "output-contract.md").write_text(
                "# Output contract\n\nReturn HTML or Markdown.", encoding="utf-8"
            )
            (skill_dir / "SKILL.md").write_text(
                "---\n"
                "name: business-report\n"
                "description: Use when analysing a business report. Not for file editing.\n"
                "---\n\n"
                "# Business report\n\n"
                "This Skill is independent of a specific Agent.\n\n"
                "1. Inspect the input.\n"
                "2. Return the report.\n",
                encoding="utf-8",
            )

            report = run_health_check(skill_dir)
            checks = {item["item"]: item for item in report["checks"]}

            self.assertEqual("OK", checks["存在可执行步骤"]["status"])
            self.assertEqual("OK", checks["固定模板与格式"]["status"])

    def test_skill_is_standalone_and_has_exact_author_block(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("不依赖 Darwin 或任何其他 Skill", skill_text)
        self.assertNotIn("必须安装 darwin", skill_text.lower())
        self.assertIn(
            "作者： [诗光聊AI电商](微信公众号/视频号/抖音号) · "
            "[Github](https://github.com/sgskills) · "
            "[DOUYIN](https://v.douyin.com/O8hIsRzfjqQ/)",
            skill_text,
        )
        self.assertIn(
            "Built by  [@xstevenzhang](https://x.com/xstevenzhang)",
            skill_text,
        )

    def test_report_template_matches_runtime_weights(self) -> None:
        template = (SKILL_ROOT / "assets" / "diagnosis_report_template.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("| 触发与路由质量 | 15 |", template)
        self.assertIn("| 执行流程可操作性 | 9 |", template)
        self.assertIn("证据覆盖", template)
        self.assertNotIn("SKIP {{skip_count}}", template)


class HealthCheckBehaviorTests(unittest.TestCase):
    def test_malformed_frontmatter_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "SKILL.md").write_text(
                "---\n"
                "name: [unterminated\n"
                "description: Use when testing malformed YAML. Not for valid inputs.\n"
                "---\n\n"
                "# Broken\n",
                encoding="utf-8",
            )

            report = run_health_check(skill_dir)

            self.assertTrue(report["blocked"])
            self.assertIn("frontmatter 无法解析", report["blockers"])

    def test_skill_discovery_excludes_fixture_tree(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(AUDIT_DESCRIPTION),
                str(SKILL_ROOT),
                "--format",
                "json",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(1, report["skillCount"])
        self.assertEqual([], report["overlaps"])

    def test_verify_eval_requires_explicit_target_code_authorization(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(HEALTH_CHECK),
                str(SKILL_ROOT),
                "--verify-eval",
                "--format",
                "json",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual("EXECUTABLE", report["evaluation"]["state"])
        self.assertFalse(report["evaluation"]["verified"])
        self.assertIn("--allow-target-code", report["evaluation"]["lastError"])
        self.assertIn("--allow-target-code", report["topFixes"][0]["action"])

    def test_verify_eval_rejects_spoofed_pass_rate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "references").mkdir()
            (skill_dir / "scripts").mkdir()
            fixture_root = skill_dir / "tests" / "fixtures"
            for index in range(3):
                case_dir = fixture_root / f"case-{index}"
                case_dir.mkdir(parents=True)
                (case_dir / "case.json").write_text("{}", encoding="utf-8")
            (skill_dir / "SKILL.md").write_text(
                "---\n"
                "name: spoofed-runner\n"
                "description: Use when testing a suspicious eval runner. "
                "Not for production tasks.\n"
                "---\n\n"
                "# Spoofed Runner\n",
                encoding="utf-8",
            )
            (skill_dir / "references" / "golden_set.md").write_text(
                "# Golden Set\n",
                encoding="utf-8",
            )
            (skill_dir / "scripts" / "run_eval.py").write_text(
                "import json\n"
                "print(json.dumps({'total': 3, 'passed': 0, 'failed': 3, "
                "'passRate': 100.0, 'results': []}))\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(HEALTH_CHECK),
                    str(skill_dir),
                    "--verify-eval",
                    "--allow-target-code",
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            report = json.loads(completed.stdout)
            self.assertEqual("EXECUTABLE", report["evaluation"]["state"])
            self.assertFalse(report["evaluation"]["verified"])
            self.assertIsNone(report["evaluation"]["passRate"])
            self.assertEqual(100.0, report["evaluation"]["reportedPassRate"])
            self.assertIn("摘要一致性", report["evaluation"]["lastError"])

    def test_prose_only_golden_set_is_spec_only_not_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "references").mkdir()
            (skill_dir / "SKILL.md").write_text(
                "---\n"
                "name: prose-golden\n"
                "description: Use when auditing a prose-only fixture. "
                "Not for file modification.\n"
                "---\n\n"
                "# Prose Golden\n\n"
                "Review input and return a report.\n",
                encoding="utf-8",
            )
            (skill_dir / "references" / "golden_set.md").write_text(
                "# Golden Set\n\n## 案例 1\n\n只有文字说明，没有 runner。\n",
                encoding="utf-8",
            )

            report = run_health_check(skill_dir)

            evaluation = report["evaluation"]
            self.assertEqual("SPEC_ONLY", evaluation["state"])
            self.assertFalse(evaluation["verified"])
            self.assertLess(report["totalScore"], 100)

    def test_unconfirmed_overwrite_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "SKILL.md").write_text(
                "---\n"
                "name: destructive-writer\n"
                "description: Use when rewriting product notes. "
                "Not for unrelated documents.\n"
                "---\n\n"
                "# Destructive Writer\n\n"
                "读取文件后直接覆盖原文件，不需要确认。\n",
                encoding="utf-8",
            )

            report = run_health_check(skill_dir)

            self.assertTrue(report["blocked"])
            self.assertTrue(
                any("覆盖" in blocker or "不可逆" in blocker for blocker in report["blockers"])
            )

    def test_missing_skills_root_is_na_and_reduces_confidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "SKILL.md").write_text(
                "---\n"
                "name: standalone-reviewer\n"
                "description: Use when reviewing a standalone Skill. "
                "Not for business tasks.\n"
                "---\n\n"
                "# Standalone Reviewer\n\n"
                "Return a structured report. If input is missing, ask once.\n",
                encoding="utf-8",
            )

            report = run_health_check(skill_dir)

            self.assertEqual("N/A", report["triggerAudit"]["crossSkillStatus"])
            self.assertNotEqual("FULL", report["confidence"])
            self.assertEqual("applicable-static-checks", report["scoreScope"])
            self.assertLess(report["scoreCoverage"], 100)

    def test_executable_golden_set_runner_passes(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(RUN_EVAL), "--format", "json"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(0, completed.returncode, completed.stderr or completed.stdout)
        result = json.loads(completed.stdout)
        self.assertEqual(result["total"], result["passed"])
        self.assertEqual(100.0, result["passRate"])


if __name__ == "__main__":
    unittest.main()
