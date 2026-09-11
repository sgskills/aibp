from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
ROUTER = ROOT / "skills" / "sg-aibp"
CASES = json.loads((Path(__file__).with_name("cases.json")).read_text(encoding="utf-8"))
SPECIALISTS = {
    "sg-ceo-vision",
    "sg-research",
    "sg-blackcat",
    "sg-mece",
    "sg-review",
    "sg-shiwu",
    "sg-toplist",
    "sg-title",
    "sg-tmads-report",
    "sg-skill-optimizer",
}


class RouterContractTests(unittest.TestCase):
    def test_every_specialist_has_a_route_case_and_live_skill(self) -> None:
        expected = {case["expected"] for case in CASES if case["expected"] != "OUT_OF_SCOPE"}
        self.assertEqual(expected, SPECIALISTS)
        for slug in SPECIALISTS:
            with self.subTest(slug=slug):
                self.assertTrue((ROOT / "skills" / slug / "SKILL.md").is_file())

    def test_route_case_ids_are_unique_and_inputs_are_nonempty(self) -> None:
        ids = [case["id"] for case in CASES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(case["request"].strip() for case in CASES))

    def test_router_matrix_names_every_specialist(self) -> None:
        text = (ROUTER / "references" / "routing-matrix.md").read_text(encoding="utf-8")
        for slug in SPECIALISTS:
            with self.subTest(slug=slug):
                self.assertIn(f"`{slug}`", text)

    def test_router_does_not_claim_specialist_execution(self) -> None:
        text = (ROUTER / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("不用于替代专业 Skill", text)
        self.assertIn("不自动安装、更新、提交、推送、发布", text)
        self.assertIn("最多追问一个关键问题", text)

    def test_openai_prompt_explicitly_invokes_router(self) -> None:
        text = (ROUTER / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("$sg-aibp", text)


if __name__ == "__main__":
    unittest.main()
