from __future__ import annotations

import copy
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path, PurePosixPath


SKILL_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = SKILL_ROOT / "scripts" / "run_eval.py"
SPEC = importlib.util.spec_from_file_location("sg_shiwu_run_eval", RUNNER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load contract runner: {RUNNER_PATH}")
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)

GUARD_PATH = SKILL_ROOT / "scripts" / "output_guard.py"
GUARD_SPEC = importlib.util.spec_from_file_location("sg_shiwu_output_guard", GUARD_PATH)
if GUARD_SPEC is None or GUARD_SPEC.loader is None:
    raise RuntimeError(f"Unable to load output guard: {GUARD_PATH}")
GUARD = importlib.util.module_from_spec(GUARD_SPEC)
GUARD_SPEC.loader.exec_module(GUARD)


EXPECTED_REFERENCES = {
    "input-contract.md",
    "feature-method.md",
    "evidence-policy.md",
    "output-contract.md",
    "uncertainty-and-correction.md",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _frontmatter(text: str) -> tuple[set[str], dict[str, str]]:
    match = re.match(r"\A---\r?\n(?P<body>.*?)\r?\n---(?:\r?\n|\Z)", text, re.DOTALL)
    if not match:
        raise AssertionError("SKILL.md must begin with YAML frontmatter")
    body = match.group("body")
    keys = set(re.findall(r"^([a-z][a-z0-9-]*):(?:\s.*)?$", body, re.MULTILINE))
    values: dict[str, str] = {}
    lines = body.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        key_match = re.match(r"^([a-z][a-z0-9-]*):(?:\s*(.*))?$", line)
        if not key_match:
            index += 1
            continue
        key, raw_value = key_match.group(1), key_match.group(2) or ""
        if raw_value in {"|", ">"}:
            block: list[str] = []
            index += 1
            while index < len(lines) and (lines[index].startswith(" ") or not lines[index]):
                block.append(lines[index].strip())
                index += 1
            values[key] = "\n".join(block).strip()
            continue
        values[key] = raw_value.strip().strip('"')
        index += 1
    return keys, values


def _feature(
    *,
    feature_id: str = "F-01",
    value: str = "圆柱形杯身",
    source_id: str = "IMG-01",
    evidence_type: str = "清晰观察",
    stability: str = "身份不变量",
    priority: str = "P0",
    confidence: str = "高",
) -> dict[str, object]:
    return {
        "id": feature_id,
        "name": "主体轮廓",
        "value": value,
        "evidence": [{"source_id": source_id, "location": "主体中央轮廓"}],
        "evidence_type": evidence_type,
        "stability": stability,
        "priority": priority,
        "confidence": {"level": confidence, "reason": "主体边界清晰且位置可定位"},
    }


def _valid_output() -> dict[str, object]:
    return {
        "route": "analyze",
        "handoff_target": None,
        "section_order": list(RUNNER.REQUIRED_SECTIONS),
        "groups": [
            {
                "id": "P01",
                "kind": "product",
                "image_ids": ["IMG-01"],
                "relation": "same_sku",
            }
        ],
        "features": [_feature()],
        "identity_anchors": [
            {"group_id": "P01", "text": "圆柱形杯身", "feature_ids": ["F-01"]}
        ],
        "correction": None,
    }


class PublishedStructureTests(unittest.TestCase):
    def test_root_structure_is_minimal(self) -> None:
        self.assertEqual(
            {path.name for path in SKILL_ROOT.iterdir()},
            {"SKILL.md", "agents", "references", "scripts", "tests"},
        )
        self.assertEqual(
            {path.name for path in (SKILL_ROOT / "agents").iterdir()},
            {"openai.yaml"},
        )
        self.assertEqual(
            {path.name for path in (SKILL_ROOT / "references").iterdir()},
            EXPECTED_REFERENCES,
        )
        self.assertEqual(
            {path.name for path in (SKILL_ROOT / "scripts").iterdir()},
            {
                "run_eval.py",
                "output_guard.py",
                "check-update.ps1",
                "check-update.sh",
                "update-version.txt",
            },
        )
        self.assertEqual(
            {path.name for path in (SKILL_ROOT / "tests").iterdir()},
            {"test_contract.py", "fixtures"},
        )
        for case_dir in (SKILL_ROOT / "tests" / "fixtures").iterdir():
            if case_dir.is_dir():
                self.assertEqual({path.name for path in case_dir.iterdir()}, {"case.json"})

    def test_frontmatter_has_exact_required_keys_and_values(self) -> None:
        keys, values = _frontmatter(_read(SKILL_ROOT / "SKILL.md"))
        self.assertEqual(keys, {"name", "description", "license"})
        self.assertEqual(values["name"], "sg-shiwu")
        self.assertEqual(values["license"], "SGSkills Internal Use License 1.0")
        description = values["description"]
        self.assertTrue(description)
        self.assertLessEqual(len(description), 1024)
        self.assertNotIn("<", description)
        self.assertNotIn(">", description)
        self.assertIn("视觉指纹", description)
        self.assertLess(description.index("当用户"), description.index("不用于"))

    def test_openai_yaml_preserves_quoted_chinese_and_literal_skill_name(self) -> None:
        raw = _read(SKILL_ROOT / "agents" / "openai.yaml")
        lines = raw.splitlines()
        self.assertEqual(lines[0], "interface:")
        self.assertEqual(len(lines), 4)
        parsed: dict[str, str] = {}
        for line in lines[1:]:
            match = re.fullmatch(r'  ([a-z_]+): ("(?:[^"\\]|\\.)*")', line)
            self.assertIsNotNone(match, f"interface string must be double quoted: {line}")
            assert match is not None
            parsed[match.group(1)] = json.loads(match.group(2))
        self.assertEqual(
            set(parsed), {"display_name", "short_description", "default_prompt"}
        )
        self.assertEqual(parsed["display_name"], "识物｜产品特征提取专家")
        self.assertEqual(
            parsed["short_description"],
            "把产品图片转化为可追溯的视觉指纹、身份锚点与防漂移约束",
        )
        self.assertGreaterEqual(len(parsed["short_description"]), 25)
        self.assertLessEqual(len(parsed["short_description"]), 64)
        self.assertIn("$sg-shiwu", parsed["default_prompt"])

    def test_all_local_references_exist_and_never_escape(self) -> None:
        skill_text = _read(SKILL_ROOT / "SKILL.md")
        for name in EXPECTED_REFERENCES:
            self.assertIn(f"references/{name}", skill_text)

        markdown_files = [SKILL_ROOT / "SKILL.md", *(SKILL_ROOT / "references").glob("*.md")]
        link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
        root_resolved = SKILL_ROOT.resolve()
        for document in markdown_files:
            for raw_target in link_pattern.findall(_read(document)):
                target = raw_target.strip().strip("<>").split("#", 1)[0]
                if not target or re.match(r"^[a-z][a-z0-9+.-]*://", target, re.IGNORECASE):
                    continue
                self.assertNotIn("..", PurePosixPath(target.replace("\\", "/")).parts)
                resolved = (document.parent / target).resolve()
                try:
                    resolved.relative_to(root_resolved)
                except ValueError as exc:
                    self.fail(f"local reference escapes skill root: {document} -> {target}: {exc}")
                self.assertTrue(resolved.is_file(), f"missing local reference: {document} -> {target}")

    def test_output_sections_are_exact_and_ordered(self) -> None:
        text = _read(SKILL_ROOT / "references" / "output-contract.md")
        headings = re.findall(r"^### [1-7]\. (.+)$", text, re.MULTILINE)
        self.assertEqual(tuple(headings), RUNNER.REQUIRED_SECTIONS)
        self.assertEqual(
            RUNNER.DEGRADED_SECTIONS,
            ("无法分析的原因", "未做出的结论", "最小上传清单"),
        )

    def test_feature_enums_match_published_evidence_policy(self) -> None:
        self.assertEqual(
            RUNNER.EVIDENCE_TYPES,
            {"清晰观察", "用户确认", "外观推断", "冲突", "不可判断"},
        )
        self.assertEqual(
            RUNNER.STABILITY_VALUES,
            {"身份不变量", "变体特征", "状态变量", "拍摄伪影", "未知"},
        )
        self.assertEqual(RUNNER.PRIORITIES, {"P0", "P1", "P2"})
        self.assertEqual(RUNNER.CONFIDENCE_LEVELS, {"高", "中", "低"})
        policy = _read(SKILL_ROOT / "references" / "evidence-policy.md")
        for value in (
            *RUNNER.EVIDENCE_TYPES,
            *RUNNER.STABILITY_VALUES,
            *RUNNER.PRIORITIES,
            *RUNNER.CONFIDENCE_LEVELS,
        ):
            self.assertIn(value, policy)


class GoldenSetTests(unittest.TestCase):
    def test_all_fixtures_satisfy_schema_routes_and_coverage(self) -> None:
        summary = RUNNER.evaluate_all(SKILL_ROOT)
        failures = [
            f"{result['case_id']}: {'; '.join(result['errors'])}"
            for result in summary["case_results"]
            if result["errors"]
        ]
        failures.extend(summary["errors"])
        self.assertGreaterEqual(summary["total"], 20)
        self.assertEqual(failures, [])
        self.assertEqual(summary["passed"], summary["total"])

    def test_fixture_schema_rejects_bad_route_sections_and_tokens(self) -> None:
        source = SKILL_ROOT / "tests" / "fixtures" / "mixed-sku" / "case.json"
        case = json.loads(_read(source))
        broken = copy.deepcopy(case)
        broken["expected"]["route"] = "request_upload"
        broken["expected"]["must_assert"].append("Not-Snake")
        errors = RUNNER.validate_case(broken, "mixed-sku")
        self.assertTrue(any("required_sections" in error for error in errors))
        self.assertTrue(any("snake_case" in error for error in errors))
        self.assertTrue(any("mixed_sku" in error and "analyze" in error for error in errors))

    def test_fixture_schema_rejects_unknown_feature_enums(self) -> None:
        feature = _feature(evidence_type="确定无疑")
        errors = RUNNER.validate_feature_record(feature, {"IMG-01"})
        self.assertTrue(any("evidence_type" in error for error in errors))


class OutputContractTests(unittest.TestCase):
    def test_output_guard_rejects_single_image_photometric_colour_anchor(self) -> None:
        sources = {"IMG-01": {"id": "IMG-01", "kind": "image", "readable": True,
                              "active": True, "group_ids": ["P01"]}}
        feature = _feature()
        feature.update(name="手柄底端色区", value="底端呈琥珀橙色", group_id="P01")
        feature["confidence"]["reason"] = "两处亮色可见，但受到直射光与亮斑影响"
        self.assertTrue(GUARD._photometric_anchor_risk(feature, sources))

    def test_output_guard_rejects_composite_geometry_field(self) -> None:
        groups = {"P01": {"id": "P01", "kind": "product", "image_ids": ["IMG-01"],
                          "relation": "same_sku", "parent_id": None,
                          "basis": "主体边界清晰", "confidence": "高"}}
        sources = {"IMG-01": {"id": "IMG-01", "kind": "image", "readable": True,
                              "active": True, "group_ids": ["P01"]}}
        feature = _feature()
        feature["group_id"] = "P01"
        feature["name"] = "主体几何"
        errors = GUARD._feature_errors(feature, groups, sources, "features[0]")
        self.assertTrue(any("composite field" in error for error in errors))

    def test_valid_evidenced_output_passes(self) -> None:
        self.assertEqual(RUNNER.validate_output_contract(_valid_output(), {"IMG-01"}), [])

    def test_feature_requires_registered_localized_evidence(self) -> None:
        feature = _feature(source_id="IMG-99")
        feature["evidence"][0]["location"] = ""
        errors = RUNNER.validate_feature_record(feature, {"IMG-01"})
        self.assertTrue(any("not registered" in error for error in errors))
        self.assertTrue(any("location" in error for error in errors))

    def test_inference_and_unknown_cannot_claim_high_confidence(self) -> None:
        inference = _feature(
            value="疑似磨砂表面",
            evidence_type="外观推断",
            confidence="高",
        )
        unknown = _feature(
            value="不可判断",
            evidence_type="不可判断",
            stability="未知",
            confidence="高",
        )
        self.assertTrue(
            any("cannot have high confidence" in error for error in RUNNER.validate_feature_record(inference, {"IMG-01"}))
        )
        self.assertTrue(
            any("cannot have high confidence" in error for error in RUNNER.validate_feature_record(unknown, {"IMG-01"}))
        )

    def test_conflict_requires_two_registered_sources(self) -> None:
        conflict = _feature(
            value="冲突未决",
            evidence_type="冲突",
            stability="未知",
            confidence="中",
        )
        errors = RUNNER.validate_feature_record(conflict, {"IMG-01", "IMG-02"})
        self.assertTrue(any("two distinct sources" in error for error in errors))
        conflict["evidence"].append({"source_id": "IMG-02", "location": "侧面标签"})
        self.assertEqual(
            RUNNER.validate_feature_record(conflict, {"IMG-01", "IMG-02"}),
            [],
        )

    def test_identity_anchor_rejects_state_artifact_and_unresolved_features(self) -> None:
        output = _valid_output()
        output["features"] = [
            _feature(stability="状态变量"),
            _feature(
                feature_id="F-02",
                value="不可判断",
                evidence_type="不可判断",
                stability="未知",
                priority="P1",
                confidence="低",
            ),
        ]
        output["identity_anchors"][0]["feature_ids"] = ["F-01", "F-02"]
        errors = RUNNER.validate_output_contract(output, {"IMG-01"})
        self.assertTrue(any("non-identity stability" in error for error in errors))
        self.assertTrue(any("unresolved evidence" in error for error in errors))

    def test_degraded_and_handoff_routes_cannot_fabricate_analysis(self) -> None:
        for route, target, sections in (
            ("request_upload", None, RUNNER.DEGRADED_SECTIONS),
            ("handoff", None, ()),
        ):
            with self.subTest(route=route):
                output = _valid_output()
                output["route"] = route
                output["handoff_target"] = target
                output["section_order"] = list(sections)
                errors = RUNNER.validate_output_contract(output, {"IMG-01"})
                self.assertTrue(any("must not fabricate" in error for error in errors))

    def test_correction_is_field_local_and_preserves_user_source(self) -> None:
        previous = _valid_output()
        previous["features"].append(
            _feature(
                feature_id="F-02",
                value="用户确认蓝色",
                source_id="USER-01",
                evidence_type="用户确认",
                stability="变体特征",
                priority="P1",
                confidence="高",
            )
        )
        corrected = copy.deepcopy(previous)
        corrected["route"] = "correct"
        corrected["features"][1]["value"] = "用户确认深蓝色"
        corrected["correction"] = {
            "changed_feature_ids": ["F-02"],
            "change_summary": [
                {
                    "feature_id": "F-02",
                    "from": "用户确认蓝色",
                    "to": "用户确认深蓝色",
                    "source": "USER-01",
                    "reason": "用户在可信对话中校正颜色变体",
                }
            ],
        }
        known_sources = {"IMG-01", "USER-01"}
        self.assertEqual(RUNNER.validate_output_contract(corrected, known_sources), [])
        self.assertEqual(RUNNER.validate_correction(previous, corrected), [])

        broken = copy.deepcopy(corrected)
        broken["features"][0]["value"] = "无关轮廓被改写"
        errors = RUNNER.validate_correction(previous, broken)
        self.assertTrue(any("changed_feature_ids" in error for error in errors))

        provenance_lost = copy.deepcopy(corrected)
        provenance_lost["features"][1]["evidence"] = [
            {"source_id": "IMG-01", "location": "主体表面"}
        ]
        errors = RUNNER.validate_correction(previous, provenance_lost)
        self.assertTrue(any("user-confirmed provenance" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
