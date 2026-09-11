#!/usr/bin/env python3
"""验证 sg-research 的目录结构与规范化路由合同，不评估真实研究质量。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_ROOT = SKILL_ROOT / "tests" / "fixtures"
SCHEMA_VERSION = "1.0.0"
SCOPE_NOTICE = (
    "Deterministic structure and normalized routing contracts only; "
    "no live research, source verification, or research-quality claim."
)

ROUTES = {
    "research_execution",
    "research_task_pack",
    "research_execution_plus_task_pack",
    "research_degraded_bundle",
    "non_trigger",
}
TOOL_STATES = {
    "ONLINE_FULL",
    "OFFLINE",
    "FAIL_AFTER_LEDGER_1",
    "SEARCH_ONLY",
    "ONLINE_SAME_LINEAGE",
    "ONLINE_ONE_FINAL_AUTHORITY",
    "ONLINE_CONFLICT",
    "ONLINE_CORRELATION_ONLY",
    "ONLINE_NO_FORECAST_METHOD",
    "ONLINE_WITH_INJECTION",
    "ONLINE_MULTILINGUAL",
    "ONLINE_STABLE_TWO_ROUNDS",
}
EXECUTION_STATES = {"not_started", "ready", "interrupted", "evidence_insufficient"}
INTENT_KEYS = {
    "research",
    "wants_report",
    "wants_task_pack",
    "explicit_task_pack_only",
}

REQUIRED_REFERENCE_FILES = {
    "mode-routing.md",
    "research-design.md",
    "source-policy.md",
    "uncertainty.md",
    "report-contract.md",
    "task-pack-contract.md",
    "golden-set.md",
}
CONTRACT_FILES = {
    "ROUTE-EXECUTION": "mode-routing.md",
    "ROUTE-TASK-PACK": "mode-routing.md",
    "ROUTE-DUAL": "mode-routing.md",
    "ROUTE-PARTIAL": "mode-routing.md",
    "ROUTE-NOT-APPLICABLE": "mode-routing.md",
    "ROUTE-SPECIALIST-HANDOFF": "mode-routing.md",
    "TOOL-PREFLIGHT": "mode-routing.md",
    "LXS-OPTIONAL": "research-design.md",
    "NO-HISTORY-ADAPT": "research-design.md",
    "MULTILINGUAL-SEARCH": "research-design.md",
    "PERIODIC-SNAPSHOT": "research-design.md",
    "STOP-RULE": "research-design.md",
    "EVIDENCE-LEDGER": "research-design.md",
    "FULLTEXT-EVIDENCE": "source-policy.md",
    "SOURCE-INDEPENDENCE": "source-policy.md",
    "FINAL-AUTHORITY": "source-policy.md",
    "CONFLICT-LINEAGE": "source-policy.md",
    "PROMPT-INJECTION": "source-policy.md",
    "HIGH-RISK-SOURCES": "source-policy.md",
    "FACT-INFERENCE-ASSUMPTION": "uncertainty.md",
    "CONFIDENCE-HML": "uncertainty.md",
    "CAUSALITY-GATE": "uncertainty.md",
    "FORECAST-GATE": "uncertainty.md",
    "REPORT-SECTIONS": "report-contract.md",
    "NEARBY-CITATIONS": "report-contract.md",
    "PARTIAL-DELIVERY": "report-contract.md",
    "TASK-PACK-SECTIONS": "task-pack-contract.md",
    "OFFLINE-DISCLOSURE": "task-pack-contract.md",
    "ACCEPTANCE-CRITERIA": "task-pack-contract.md",
}


def _spec(category: str, route: str, *contracts: str) -> dict[str, Any]:
    return {"category": category, "route": route, "contracts": frozenset(contracts)}


CASE_MANIFEST = {
    "GS-001-explicit-pack-wins": _spec(
        "explicit-task-pack",
        "research_task_pack",
        "ROUTE-TASK-PACK",
        "TASK-PACK-SECTIONS",
        "ACCEPTANCE-CRITERIA",
    ),
    "GS-002-offline-switch": _spec(
        "offline-fallback",
        "research_task_pack",
        "TOOL-PREFLIGHT",
        "ROUTE-TASK-PACK",
        "OFFLINE-DISCLOSURE",
        "TASK-PACK-SECTIONS",
    ),
    "GS-003-online-report": _spec(
        "online-report",
        "research_execution",
        "TOOL-PREFLIGHT",
        "ROUTE-EXECUTION",
        "EVIDENCE-LEDGER",
        "REPORT-SECTIONS",
        "NEARBY-CITATIONS",
        "STOP-RULE",
    ),
    "GS-004-both-online": _spec(
        "dual-delivery-online",
        "research_execution_plus_task_pack",
        "ROUTE-DUAL",
        "REPORT-SECTIONS",
        "TASK-PACK-SECTIONS",
        "STOP-RULE",
    ),
    "GS-005-both-offline": _spec(
        "dual-delivery-offline",
        "research_task_pack",
        "TOOL-PREFLIGHT",
        "ROUTE-TASK-PACK",
        "OFFLINE-DISCLOSURE",
        "TASK-PACK-SECTIONS",
    ),
    "GS-006-execution-interrupted": _spec(
        "execution-interrupted",
        "research_degraded_bundle",
        "ROUTE-PARTIAL",
        "PARTIAL-DELIVERY",
        "TASK-PACK-SECTIONS",
    ),
    "GS-007-simple-fact": _spec(
        "simple-fact",
        "non_trigger",
        "ROUTE-NOT-APPLICABLE",
    ),
    "GS-008-pure-summary": _spec(
        "pure-summary",
        "non_trigger",
        "ROUTE-NOT-APPLICABLE",
    ),
    "GS-009-translation": _spec(
        "translation",
        "non_trigger",
        "ROUTE-NOT-APPLICABLE",
    ),
    "GS-010-ordinary-writing": _spec(
        "ordinary-writing",
        "non_trigger",
        "ROUTE-NOT-APPLICABLE",
    ),
    "GS-011-no-history": _spec(
        "no-history-data",
        "research_execution",
        "ROUTE-EXECUTION",
        "NO-HISTORY-ADAPT",
        "LXS-OPTIONAL",
        "REPORT-SECTIONS",
    ),
    "GS-012-breaking-news": _spec(
        "time-sensitive-news",
        "research_execution",
        "ROUTE-EXECUTION",
        "FULLTEXT-EVIDENCE",
        "EVIDENCE-LEDGER",
        "REPORT-SECTIONS",
        "STOP-RULE",
    ),
    "GS-013-same-lineage": _spec(
        "syndicated-same-lineage",
        "research_degraded_bundle",
        "ROUTE-PARTIAL",
        "SOURCE-INDEPENDENCE",
        "PARTIAL-DELIVERY",
        "TASK-PACK-SECTIONS",
    ),
    "GS-014-final-authority": _spec(
        "single-final-authority",
        "research_execution",
        "ROUTE-EXECUTION",
        "FINAL-AUTHORITY",
        "CONFIDENCE-HML",
        "REPORT-SECTIONS",
    ),
    "GS-015-unreadable-body": _spec(
        "unreadable-fulltext",
        "research_task_pack",
        "TOOL-PREFLIGHT",
        "ROUTE-TASK-PACK",
        "FULLTEXT-EVIDENCE",
        "OFFLINE-DISCLOSURE",
        "TASK-PACK-SECTIONS",
    ),
    "GS-016-source-conflict": _spec(
        "source-conflict",
        "research_execution",
        "ROUTE-EXECUTION",
        "CONFLICT-LINEAGE",
        "CONFIDENCE-HML",
        "REPORT-SECTIONS",
    ),
    "GS-017-correlation-causality": _spec(
        "correlation-causation",
        "research_execution",
        "ROUTE-EXECUTION",
        "CAUSALITY-GATE",
        "FACT-INFERENCE-ASSUMPTION",
        "REPORT-SECTIONS",
    ),
    "GS-018-high-risk-medical": _spec(
        "high-risk-medical",
        "research_execution",
        "ROUTE-EXECUTION",
        "HIGH-RISK-SOURCES",
        "CONFIDENCE-HML",
        "REPORT-SECTIONS",
    ),
    "GS-019-unsupported-forecast": _spec(
        "forecast-without-method",
        "research_degraded_bundle",
        "ROUTE-PARTIAL",
        "FORECAST-GATE",
        "PARTIAL-DELIVERY",
        "TASK-PACK-SECTIONS",
    ),
    "GS-020-prompt-injection": _spec(
        "prompt-injection",
        "research_execution",
        "ROUTE-EXECUTION",
        "PROMPT-INJECTION",
        "FULLTEXT-EVIDENCE",
        "REPORT-SECTIONS",
    ),
    "GS-021-multilingual": _spec(
        "multilingual-search",
        "research_execution",
        "ROUTE-EXECUTION",
        "MULTILINGUAL-SEARCH",
        "SOURCE-INDEPENDENCE",
        "REPORT-SECTIONS",
    ),
    "GS-022-periodic-tracking": _spec(
        "periodic-tracking",
        "research_execution_plus_task_pack",
        "ROUTE-DUAL",
        "PERIODIC-SNAPSHOT",
        "REPORT-SECTIONS",
        "TASK-PACK-SECTIONS",
        "STOP-RULE",
    ),
    "GS-023-assume-and-continue": _spec(
        "nonblocking-assumptions",
        "research_execution",
        "ROUTE-EXECUTION",
        "FACT-INFERENCE-ASSUMPTION",
        "REPORT-SECTIONS",
    ),
    "GS-024-normal-stop": _spec(
        "normal-stop",
        "research_execution",
        "ROUTE-EXECUTION",
        "STOP-RULE",
        "REPORT-SECTIONS",
    ),
    "GS-025-ceo-vision-handoff": _spec(
        "ceo-direction-resource-handoff",
        "non_trigger",
        "ROUTE-NOT-APPLICABLE",
        "ROUTE-SPECIALIST-HANDOFF",
    ),
    "GS-026-mece-handoff": _spec(
        "ambiguous-ecommerce-handoff",
        "non_trigger",
        "ROUTE-NOT-APPLICABLE",
        "ROUTE-SPECIALIST-HANDOFF",
    ),
    "GS-027-specialist-handoff": _spec(
        "known-specialist-handoff",
        "non_trigger",
        "ROUTE-NOT-APPLICABLE",
        "ROUTE-SPECIALIST-HANDOFF",
    ),
}

ROUTE_REQUIRED_CONTRACTS = {
    "research_execution": {"ROUTE-EXECUTION", "REPORT-SECTIONS"},
    "research_task_pack": {"ROUTE-TASK-PACK", "TASK-PACK-SECTIONS"},
    "research_execution_plus_task_pack": {
        "ROUTE-DUAL",
        "REPORT-SECTIONS",
        "TASK-PACK-SECTIONS",
    },
    "research_degraded_bundle": {
        "ROUTE-PARTIAL",
        "PARTIAL-DELIVERY",
        "TASK-PACK-SECTIONS",
    },
    "non_trigger": {"ROUTE-NOT-APPLICABLE"},
}


class EvalInfrastructureError(RuntimeError):
    """表示评测基础设施或 fixture schema 不合法。"""


def read_utf8(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise EvalInfrastructureError(f"cannot read UTF-8 file {path}: {exc}") from exc


def parse_frontmatter(text: str) -> tuple[list[str], dict[str, str]]:
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise EvalInfrastructureError("SKILL.md must start with YAML frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise EvalInfrastructureError("SKILL.md frontmatter is not closed") from exc

    keys: list[str] = []
    values: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.startswith((" ", "\t")) or ":" not in line:
            raise EvalInfrastructureError(f"unsupported frontmatter line: {line!r}")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key in values or not value:
            raise EvalInfrastructureError(f"invalid frontmatter field: {key!r}")
        keys.append(key)
        values[key] = value
    return keys, values


def validate_structure() -> list[str]:
    errors: list[str] = []
    required_paths = [
        SKILL_ROOT / "SKILL.md",
        SKILL_ROOT / "agents" / "openai.yaml",
        SKILL_ROOT / "scripts" / "run_eval.py",
    ] + [SKILL_ROOT / "references" / name for name in REQUIRED_REFERENCE_FILES]
    for path in required_paths:
        if not path.is_file():
            errors.append(f"missing required file: {path.relative_to(SKILL_ROOT)}")

    required_root = {"SKILL.md", "agents", "references", "scripts", "tests"}
    allowed_root = required_root | {"LICENSE.txt"}
    if SKILL_ROOT.is_dir():
        actual_root = {path.name for path in SKILL_ROOT.iterdir()}
        if not required_root.issubset(actual_root) or not actual_root.issubset(allowed_root):
            errors.append(
                "root entries differ: "
                f"required={sorted(required_root)} allowed={sorted(allowed_root)} "
                f"actual={sorted(actual_root)}"
            )

    expected_agents = {"openai.yaml"}
    agents_dir = SKILL_ROOT / "agents"
    if agents_dir.is_dir() and {path.name for path in agents_dir.iterdir()} != expected_agents:
        errors.append("agents/ must contain only openai.yaml")

    scripts_dir = SKILL_ROOT / "scripts"
    expected_scripts = {
        "run_eval.py",
        "check-update.ps1",
        "check-update.sh",
        "update-version.txt",
    }
    if scripts_dir.is_dir() and {path.name for path in scripts_dir.iterdir()} != expected_scripts:
        errors.append(
            "scripts/ entries differ: "
            f"expected={sorted(expected_scripts)} "
            f"actual={sorted(path.name for path in scripts_dir.iterdir())}"
        )

    references_dir = SKILL_ROOT / "references"
    if references_dir.is_dir():
        actual_references = {path.name for path in references_dir.iterdir()}
        if actual_references != REQUIRED_REFERENCE_FILES:
            errors.append(
                "references/ entries differ: "
                f"expected={sorted(REQUIRED_REFERENCE_FILES)} actual={sorted(actual_references)}"
            )

    tests_dir = SKILL_ROOT / "tests"
    if tests_dir.is_dir() and {path.name for path in tests_dir.iterdir()} not in (
        {"test_contract.py", "fixtures"},
        {"fixtures"},
    ):
        errors.append("tests/ must contain fixtures/ and may contain test_contract.py")

    for path in SKILL_ROOT.rglob("*"):
        if path.name in {"README.md", "CHANGELOG.md", "PROGRESS.md", "BLOCKED.md", "dist"}:
            errors.append(f"prohibited path in Skill: {path.relative_to(SKILL_ROOT)}")
        if path.name == "__pycache__" or path.suffix in {".pyc", ".pyo"}:
            errors.append(f"cache artifact in Skill: {path.relative_to(SKILL_ROOT)}")

    skill_path = SKILL_ROOT / "SKILL.md"
    if skill_path.is_file():
        try:
            skill_text = read_utf8(skill_path)
            keys, values = parse_frontmatter(skill_text)
            if keys != ["name", "description", "license"]:
                errors.append(f"frontmatter keys/order must be name,description,license; got {keys}")
            if values.get("name") != "sg-research":
                errors.append("frontmatter name must be sg-research")
            if values.get("license") != "SGSkills Internal Use License 1.0":
                errors.append("frontmatter license is incorrect")
            description = values.get("description", "")
            for fragment in ("研究报告", "研究任务包", "无法联网", "简单事实", "翻译", "润色"):
                if fragment not in description:
                    errors.append(f"description missing trigger boundary: {fragment}")
            if "TODO" in skill_text:
                errors.append("SKILL.md contains TODO")
            for marker in (
                "<!-- AIBP-UPDATE-CHECK:START -->",
                "<!-- AIBP-UPDATE-CHECK:END -->",
            ):
                if skill_text.count(marker) != 1:
                    errors.append(f"SKILL.md must contain exactly one managed marker: {marker}")
            if len(skill_text.splitlines()) > 500:
                errors.append("SKILL.md exceeds 500 lines")
            for match in re.finditer(r"\]\(([^)]+)\)", skill_text):
                raw_target = match.group(1).split("#", 1)[0]
                if not raw_target or "://" in raw_target:
                    continue
                target = (SKILL_ROOT / raw_target).resolve()
                try:
                    target.relative_to(SKILL_ROOT.resolve())
                except ValueError:
                    errors.append(f"local link escapes Skill root: {raw_target}")
                    continue
                if not target.is_file():
                    errors.append(f"broken local link: {raw_target}")
        except EvalInfrastructureError as exc:
            errors.append(str(exc))

    version_path = SKILL_ROOT / "scripts" / "update-version.txt"
    if version_path.is_file():
        try:
            version_text = read_utf8(version_path)
            if not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\n", version_text):
                errors.append("scripts/update-version.txt must contain X.Y.Z plus one LF")
        except EvalInfrastructureError as exc:
            errors.append(str(exc))

    metadata_path = SKILL_ROOT / "agents" / "openai.yaml"
    if metadata_path.is_file():
        try:
            metadata = read_utf8(metadata_path).strip()
            expected_metadata = "\n".join(
                [
                    "interface:",
                    '  display_name: "深度研究"',
                    '  short_description: "执行证据可审计的深度研究，或生成可独立复制执行的完整研究任务包"',
                    '  default_prompt: "使用 $sg-research 研究这个复杂问题；如果联网不可用，就生成可独立执行的研究任务包。"',
                ]
            )
            if metadata != expected_metadata:
                errors.append("agents/openai.yaml does not match the required three-field interface")
        except EvalInfrastructureError as exc:
            errors.append(str(exc))

    for contract, filename in CONTRACT_FILES.items():
        path = SKILL_ROOT / "references" / filename
        if path.is_file():
            try:
                if f"[{contract}]" not in read_utf8(path):
                    errors.append(f"missing contract marker [{contract}] in references/{filename}")
            except EvalInfrastructureError as exc:
                errors.append(str(exc))

    return errors


def calculate_route(case: dict[str, Any]) -> str:
    intent = case["intent"]
    if not intent["research"]:
        return "non_trigger"
    if intent["explicit_task_pack_only"]:
        return "research_task_pack"
    if case["tool_state"] in {"OFFLINE", "SEARCH_ONLY"}:
        return "research_task_pack"
    if case["execution_state"] in {"interrupted", "evidence_insufficient"}:
        return "research_degraded_bundle"
    if intent["wants_report"] and intent["wants_task_pack"]:
        return "research_execution_plus_task_pack"
    if intent["wants_report"]:
        return "research_execution"
    if intent["wants_task_pack"]:
        return "research_task_pack"
    return "non_trigger"


def load_cases() -> list[dict[str, Any]]:
    if not FIXTURES_ROOT.is_dir():
        raise EvalInfrastructureError("tests/fixtures directory is missing")
    paths = sorted(FIXTURES_ROOT.glob("*/case.json"))
    expected_dirs = set(CASE_MANIFEST)
    actual_dirs = {path.parent.name for path in paths}
    if actual_dirs != expected_dirs:
        raise EvalInfrastructureError(
            f"fixture directories differ: expected={sorted(expected_dirs)} actual={sorted(actual_dirs)}"
        )
    if len(paths) != len(CASE_MANIFEST):
        raise EvalInfrastructureError(
            f"expected exactly {len(CASE_MANIFEST)} case.json files, found {len(paths)}"
        )

    cases: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for path in paths:
        if {entry.name for entry in path.parent.iterdir()} != {"case.json"}:
            raise EvalInfrastructureError(f"fixture directory must contain only case.json: {path.parent}")
        try:
            case = json.loads(read_utf8(path))
        except json.JSONDecodeError as exc:
            raise EvalInfrastructureError(f"invalid JSON in {path}: {exc}") from exc
        if not isinstance(case, dict):
            raise EvalInfrastructureError(f"case must be an object: {path}")
        if set(case) != {
            "schema_version",
            "id",
            "category",
            "prompt",
            "tool_state",
            "intent",
            "execution_state",
            "expected",
        }:
            raise EvalInfrastructureError(f"case has unknown or missing keys: {path}")
        if case["schema_version"] != SCHEMA_VERSION:
            raise EvalInfrastructureError(f"unsupported schema_version in {path}")
        case_id = case["id"]
        if not isinstance(case_id, str) or case_id != path.parent.name or case_id not in CASE_MANIFEST:
            raise EvalInfrastructureError(f"case id/path mismatch: {path}")
        if case_id in seen_ids:
            raise EvalInfrastructureError(f"duplicate case id: {case_id}")
        seen_ids.add(case_id)
        if not isinstance(case["category"], str) or not case["category"]:
            raise EvalInfrastructureError(f"category must be non-empty: {case_id}")
        if not isinstance(case["prompt"], str) or not case["prompt"].strip():
            raise EvalInfrastructureError(f"prompt must be non-empty: {case_id}")
        if case["tool_state"] not in TOOL_STATES:
            raise EvalInfrastructureError(f"invalid tool_state: {case_id}")
        if case["execution_state"] not in EXECUTION_STATES:
            raise EvalInfrastructureError(f"invalid execution_state: {case_id}")
        intent = case["intent"]
        if not isinstance(intent, dict) or set(intent) != INTENT_KEYS:
            raise EvalInfrastructureError(f"invalid intent schema: {case_id}")
        if any(type(intent[key]) is not bool for key in INTENT_KEYS):
            raise EvalInfrastructureError(f"intent values must be booleans: {case_id}")
        expected = case["expected"]
        if not isinstance(expected, dict) or set(expected) != {"route", "contracts"}:
            raise EvalInfrastructureError(f"invalid expected schema: {case_id}")
        if expected["route"] not in ROUTES:
            raise EvalInfrastructureError(f"invalid expected route: {case_id}")
        contracts = expected["contracts"]
        if (
            not isinstance(contracts, list)
            or not contracts
            or any(not isinstance(item, str) for item in contracts)
            or len(contracts) != len(set(contracts))
        ):
            raise EvalInfrastructureError(f"contracts must be a non-empty unique string list: {case_id}")
        unknown_contracts = set(contracts) - set(CONTRACT_FILES)
        if unknown_contracts:
            raise EvalInfrastructureError(
                f"unknown contracts for {case_id}: {sorted(unknown_contracts)}"
            )
        cases.append(case)
    return cases


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    case_id = case["id"]
    spec = CASE_MANIFEST[case_id]
    failures: list[str] = []
    assertions = 0

    assertions += 1
    if case["category"] != spec["category"]:
        failures.append(
            f"category expected={spec['category']} actual={case['category']}"
        )

    assertions += 1
    if case["expected"]["route"] != spec["route"]:
        failures.append(
            f"fixture route expected_by_manifest={spec['route']} "
            f"actual_fixture={case['expected']['route']}"
        )

    assertions += 1
    actual_contracts = set(case["expected"]["contracts"])
    if actual_contracts != spec["contracts"]:
        failures.append(
            "contracts differ: "
            f"expected={sorted(spec['contracts'])} actual={sorted(actual_contracts)}"
        )

    assertions += 1
    required_for_route = ROUTE_REQUIRED_CONTRACTS[spec["route"]]
    if not required_for_route.issubset(actual_contracts):
        failures.append(
            f"route contracts missing={sorted(required_for_route - actual_contracts)}"
        )

    assertions += 1
    calculated = calculate_route(case)
    if calculated != case["expected"]["route"]:
        failures.append(
            f"calculated_route={calculated} expected_route={case['expected']['route']}"
        )

    return {
        "id": case_id,
        "category": case["category"],
        "calculatedRoute": calculated,
        "expectedRoute": case["expected"]["route"],
        "passed": not failures,
        "failures": failures,
        "assertions": assertions,
    }


def build_summary(results: list[dict[str, Any]], suite_errors: list[str]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    failed = total - passed
    pass_rate = round((passed / total * 100.0), 1) if total else 0.0
    return {
        "suite": "sg-research-golden-set",
        "scope": SCOPE_NOTICE,
        "total": total,
        "passed": passed,
        "failed": failed,
        "assertions": sum(result["assertions"] for result in results),
        "passRate": pass_rate,
        "results": results,
        "suiteErrors": suite_errors,
    }


def evaluate() -> tuple[dict[str, Any], int]:
    structure_errors = validate_structure()
    if structure_errors:
        return build_summary([], structure_errors), 2
    try:
        cases = load_cases()
    except EvalInfrastructureError as exc:
        return build_summary([], [str(exc)]), 2
    results = [evaluate_case(case) for case in cases]
    summary = build_summary(results, [])
    return summary, 0 if summary["failed"] == 0 else 1


def render_human(summary: dict[str, Any]) -> str:
    lines = [
        "sg-research deterministic contract evaluation",
        f"Scope: {summary['scope']}",
    ]
    for error in summary["suiteErrors"]:
        lines.append(f"[ERROR] {error}")
    for result in summary["results"]:
        status = "PASS" if result["passed"] else "FAIL"
        lines.append(
            f"[{status}] {result['id']} route={result['calculatedRoute']} "
            f"assertions={result['assertions']}"
        )
        for failure in result["failures"]:
            lines.append(f"  - {failure}")
    lines.append(
        "Summary: "
        f"total={summary['total']} passed={summary['passed']} failed={summary['failed']} "
        f"assertions={summary['assertions']} passRate={summary['passRate']:.1f}%"
    )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("human", "json"), default="human")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary, exit_code = evaluate()
    if args.format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(render_human(summary))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
