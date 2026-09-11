from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path
from types import ModuleType


SKILL_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = SKILL_ROOT / "scripts" / "run_eval.py"
FIXTURES_ROOT = SKILL_ROOT / "tests" / "fixtures"
FIXED_DESCRIPTION = "把概念、人物、事件、作品、产品、技术、圈层或小众主题转化为既能快速入门、又能继续深挖的认知地图。 触发方式：用户想系统了解一个陌生主题、追溯它的来路、看清同类坐标、理解内部语言与争议，或获得跨历史和现实的洞察时使用；纯翻译、润色、摘要和整篇代写不适用，尽调、预测、个性化专业决策及要求穷尽证据的研究报告让位 sg-research。"
REFERENCE_NAMES = {
    "scope-and-routing.md",
    "concept-workflow.md",
    "evidence-and-source-policy.md",
    "output-contract.md",
    "uncertainty-and-correction.md",
}


def load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sg_blackcat_run_eval", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("runner import spec unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if len(lines) < 5 or lines[0] != "---":
        raise ValueError("frontmatter opening delimiter missing")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError("frontmatter closing delimiter missing") from error
    values: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line:
            raise ValueError("frontmatter entry malformed")
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


class TestBlackcatContract(unittest.TestCase):
    def test_required_layout_is_minimal(self) -> None:
        self.assertEqual(
            {path.name for path in SKILL_ROOT.iterdir()},
            {"SKILL.md", "agents", "references", "scripts", "tests"},
        )
        required_files = {
            "SKILL.md",
            "agents/openai.yaml",
            "scripts/run_eval.py",
            "tests/test_contract.py",
        }
        for relative_path in required_files:
            self.assertTrue((SKILL_ROOT / relative_path).is_file(), relative_path)
        self.assertFalse((SKILL_ROOT / "assets").exists())
        self.assertFalse((SKILL_ROOT / "README.md").exists())
        self.assertFalse((SKILL_ROOT / "CHANGELOG.md").exists())
        self.assertFalse((SKILL_ROOT / "PROGRESS.md").exists())
        self.assertEqual(
            {path.name for path in (SKILL_ROOT / "references").iterdir() if path.is_file()},
            REFERENCE_NAMES,
        )

    def test_frontmatter_is_exact(self) -> None:
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        metadata = parse_frontmatter(text)
        self.assertEqual(set(metadata), {"name", "description", "license"})
        self.assertEqual(metadata["name"], "sg-blackcat")
        self.assertEqual(metadata["description"], FIXED_DESCRIPTION)
        self.assertEqual(metadata["license"], "SGSkills Internal Use License 1.0")

    def test_openai_yaml_has_only_quoted_strings(self) -> None:
        text = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertRegex(text, r'(?m)^  display_name: "黑猫"$')
        short_match = re.search(r'(?m)^  short_description: "([^"]+)"$', text)
        self.assertIsNotNone(short_match)
        short_description = short_match.group(1) if short_match else ""
        self.assertGreaterEqual(len(short_description), 25)
        self.assertLessEqual(len(short_description), 64)
        prompt_match = re.search(r'(?m)^  default_prompt: "([^"]+)"$', text)
        self.assertIsNotNone(prompt_match)
        self.assertIn("$sg-blackcat", prompt_match.group(1) if prompt_match else "")
        for line in text.splitlines():
            if line.startswith("  ") and ":" in line:
                self.assertRegex(line, r'^  [a-z_]+: ".*"$')

    def test_runtime_preserves_blackcat_identity_without_clio_persona_copy(self) -> None:
        banned_words = ("希" + "腊", "缪" + "斯", "委" + "托人")
        banned_identity = re.compile("|".join(banned_words), re.IGNORECASE)
        banned_extensions = {
            ".bmp",
            ".csv",
            ".doc",
            ".docx",
            ".gif",
            ".jpeg",
            ".jpg",
            ".pdf",
            ".png",
            ".ppt",
            ".pptx",
            ".rtf",
            ".tif",
            ".tiff",
            ".tsv",
            ".txt",
            ".webp",
            ".xls",
            ".xlsx",
        }
        for path in SKILL_ROOT.rglob("*"):
            if not path.is_file():
                continue
            if path.relative_to(SKILL_ROOT).as_posix() == "scripts/update-version.txt":
                continue
            self.assertNotIn(path.suffix.lower(), banned_extensions, str(path))
            if path.suffix.lower() in {".md", ".yaml", ".py", ".json"}:
                text = path.read_text(encoding="utf-8")
                self.assertIsNone(banned_identity.search(text), str(path))
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("南宫黑猫", skill_text)
        self.assertIn("纵向追来路、横向看位置、交叉找洞察", skill_text)

    def test_no_disabled_checks_or_placeholders(self) -> None:
        blocked_words = ("to" + "do", "sk" + "ip", "mo" + "ck")
        blocked_tokens = re.compile(r"\b(?:" + "|".join(blocked_words) + r")\b", re.IGNORECASE)
        for path in [SKILL_ROOT / "SKILL.md", RUNNER_PATH, Path(__file__)]:
            self.assertIsNone(blocked_tokens.search(path.read_text(encoding="utf-8")), str(path))

    def test_reference_contracts_are_present(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((SKILL_ROOT / "references").glob("*.md"))
        )
        required_markers = {
            "[ROUTE-CONCEPT]",
            "[ROUTE-OFFLINE]",
            "[ROUTE-CLARIFY-ONCE]",
            "[ROUTE-SPLIT]",
            "[ROUTE-SG-RESEARCH]",
            "[ROUTE-NOT-APPLICABLE]",
            "[WORD-CONCEPT-HISTORY]",
            "[CITATION-INTEGRITY]",
            "[EVIDENCE-LABELS]",
            "[PROMPT-INJECTION]",
            "[HIGH-RISK-EDUCATION]",
            "[OFFLINE-DEGRADED]",
            "[CAUSALITY-GATE]",
            "[AMBIGUITY-CANDIDATES]",
            "[SPELLING-TRANSPARENCY]",
            "[ACRONYM-DOMAIN]",
            "[NEIGHBOR-DISTINCTION]",
            "[ROUTE-TOPIC-MAP]",
            "[ROUTE-DEEP-MAP]",
            "[VERTICAL-AXIS]",
            "[HORIZONTAL-AXIS]",
            "[CROSS-INSIGHT]",
            "[FIRST-PRINCIPLES]",
            "[INSIDER-GUIDE]",
            "[TOPIC-MAP-OUTPUT]",
            "[DEEP-MAP-OUTPUT]",
        }
        for marker in required_markers:
            self.assertIn(marker, combined)

    def test_fixture_suite_is_large_and_unique(self) -> None:
        case_paths = sorted(FIXTURES_ROOT.glob("*/case.json"))
        self.assertGreaterEqual(len(case_paths), 28)
        cases = [json.loads(path.read_text(encoding="utf-8")) for path in case_paths]
        self.assertEqual(len({case["id"] for case in cases}), len(cases))
        self.assertEqual(len({case["category"] for case in cases}), len(cases))
        for path, case in zip(case_paths, cases, strict=True):
            self.assertEqual(case["id"], path.parent.name)
            self.assertNotIn("expected", case["prompt"].lower())

    def test_route_decision_does_not_read_prompt(self) -> None:
        runner = load_runner()
        scenario = {
            "request_kind": "concept_explanation",
            "object_kind": "bounded_concept",
            "concept_count": 1,
            "ambiguity": "none",
            "evidence_state": "online_fulltext",
            "risk": "ordinary",
            "flags": [],
        }
        self.assertEqual(runner.decide_route(scenario), "concept_card")
        self.assertEqual(runner.decide_route(dict(scenario)), "concept_card")

    def test_complex_objects_can_receive_topic_maps(self) -> None:
        runner = load_runner()
        base = {
            "request_kind": "concept_explanation",
            "concept_count": 1,
            "ambiguity": "none",
            "evidence_state": "online_fulltext",
            "risk": "ordinary",
            "flags": [],
        }
        for object_kind in ("complex_event", "complex_policy"):
            scenario = dict(base, object_kind=object_kind)
            self.assertEqual(runner.decide_route(scenario), "topic_map")

    def test_deep_exploration_uses_signature_framework(self) -> None:
        runner = load_runner()
        scenario = {
            "request_kind": "deep_exploration",
            "object_kind": "subculture",
            "concept_count": 1,
            "ambiguity": "none",
            "evidence_state": "online_fulltext",
            "risk": "ordinary",
            "flags": ["history", "insider_culture", "cross_insight", "first_principles"],
        }
        route = runner.decide_route(scenario)
        self.assertEqual(route, "deep_map")
        contracts = runner.decide_contracts(scenario, route)
        self.assertTrue(
            {"[VERTICAL-AXIS]", "[HORIZONTAL-AXIS]", "[CROSS-INSIGHT]", "[INSIDER-GUIDE]"}
            .issubset(contracts)
        )

    def test_specialized_contract_signals_are_enforced(self) -> None:
        runner = load_runner()
        base = {
            "request_kind": "concept_explanation",
            "object_kind": "bounded_concept",
            "concept_count": 1,
            "ambiguity": "none",
            "evidence_state": "online_fulltext",
            "risk": "ordinary",
            "flags": [],
        }
        scenarios = [
            (dict(base, ambiguity="manageable"), "[AMBIGUITY-CANDIDATES]"),
            (dict(base, object_kind="acronym"), "[ACRONYM-DOMAIN]"),
            (dict(base, flags=["spelling_candidate"]), "[SPELLING-TRANSPARENCY]"),
            (dict(base, flags=["needs_distinction"]), "[NEIGHBOR-DISTINCTION]"),
        ]
        for scenario, marker in scenarios:
            route = runner.decide_route(scenario)
            self.assertIn(marker, runner.decide_contracts(scenario, route))

    def test_runner_reports_all_cases_green(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-B", str(RUNNER_PATH), "--format", "json"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertGreaterEqual(payload["total"], 28)
        self.assertEqual(payload["total"], payload["passed"])
        self.assertEqual(payload["failed"], 0)
        self.assertEqual(payload["suiteErrors"], [])
        self.assertEqual(payload["scope"], "structure_and_normalized_routing_contracts_only")


if __name__ == "__main__":
    unittest.main()
