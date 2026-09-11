#!/usr/bin/env python3
"""验证黑猫的目录、冻结场景路由与输出合同。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURES = SKILL_ROOT / "tests" / "fixtures"

CASE_MANIFEST = {
    "BC-001-bounded-definition": "bounded_definition",
    "BC-002-manageable-ambiguity": "manageable_ambiguity",
    "BC-003-answer-changing-ambiguity": "answer_changing_ambiguity",
    "BC-004-typo-correction": "typo_correction",
    "BC-005-acronym-domain": "acronym_domain",
    "BC-006-etymology-rumor": "etymology_rumor",
    "BC-007-word-vs-concept-history": "word_vs_concept_history",
    "BC-008-near-neighbor": "near_neighbor_distinction",
    "BC-009-antonym-hierarchy": "antonym_and_hierarchy",
    "BC-010-translation-loss": "translation_loss",
    "BC-011-new-term-current": "new_term_current_usage",
    "BC-012-controversial-term": "controversial_term",
    "BC-013-learning-check": "learning_self_test",
    "BC-014-writing-material": "writing_material",
    "BC-015-offline-degradation": "offline_degradation",
    "BC-016-source-conflict": "source_conflict",
    "BC-017-broken-citation": "broken_citation",
    "BC-018-prompt-injection": "prompt_injection",
    "BC-019-high-risk-medical": "high_risk_education",
    "BC-020-pure-translation": "pure_translation_non_trigger",
    "BC-021-polish": "polish_non_trigger",
    "BC-022-summary": "summary_non_trigger",
    "BC-023-whole-article": "whole_article_non_trigger",
    "BC-024-single-fact": "single_fact_non_trigger",
    "BC-025-complex-research": "complex_research_defer",
    "BC-026-due-diligence": "due_diligence_defer",
    "BC-027-decision-report": "decision_report_defer",
    "BC-028-forecast": "forecast_defer",
    "BC-029-research-task-pack": "research_task_pack_defer",
    "BC-030-over-five-split": "over_five_split",
    "BC-031-causal-synthesis": "causal_synthesis_label",
    "BC-032-original-example": "original_example_label",
    "BC-033-pair-concept-distinction": "paired_concept_distinction",
    "BC-034-pair-decision-comparison": "paired_decision_comparison",
    "BC-035-pair-concept-with-fact": "paired_concept_with_fact",
    "BC-036-pair-single-fact": "paired_single_fact",
    "BC-037-complex-event-object": "complex_event_deep_map",
    "BC-038-complex-policy-object": "complex_policy_deep_map",
    "BC-039-deep-subculture": "deep_subculture_map",
    "BC-040-standard-product": "standard_product_map",
    "BC-041-standard-person": "standard_person_map",
}

REQUEST_KINDS = {
    "concept_explanation",
    "concept_distinction",
    "translation_loss",
    "learning_check",
    "writing_material",
    "pure_translation",
    "polish",
    "summary",
    "whole_article",
    "single_fact_check",
    "deep_research",
    "due_diligence",
    "decision_analysis",
    "forecast_report",
    "research_task_pack",
    "topic_exploration",
    "deep_exploration",
}
OBJECT_KINDS = {
    "bounded_concept",
    "bounded_phrase",
    "network_term",
    "proposition",
    "acronym",
    "high_risk_concept",
    "complex_person",
    "complex_company",
    "complex_event",
    "complex_industry",
    "complex_policy",
    "complex_market",
    "bounded_topic",
    "work",
    "product",
    "technology",
    "subculture",
    "hobby",
}
AMBIGUITY_LEVELS = {"none", "manageable", "answer_changing"}
EVIDENCE_STATES = {
    "online_fulltext",
    "offline",
    "search_only",
    "source_conflict",
    "broken_citation",
    "untrusted_instructions",
    "disputed_current",
}
RISK_LEVELS = {"ordinary", "medical", "legal", "financial"}
FLAGS = {
    "short_answer",
    "spelling_candidate",
    "history",
    "sensitive_claim",
    "translation_loss",
    "learning",
    "writing_material",
    "dynamic_usage",
    "controversial",
    "causal_claim",
    "original_example",
    "needs_distinction",
    "community_usage",
    "correction",
    "current_landscape",
    "insider_culture",
    "cross_insight",
    "first_principles",
}
ROUTES = {
    "concept_card",
    "concept_card_offline",
    "concept_card_clarify",
    "concept_card_split",
    "topic_map",
    "deep_map",
    "defer_sg_research",
    "non_trigger",
}
NON_TRIGGER_KINDS = {
    "pure_translation",
    "polish",
    "summary",
    "whole_article",
    "single_fact_check",
}
DEFER_KINDS = {
    "deep_research",
    "due_diligence",
    "decision_analysis",
    "forecast_report",
    "research_task_pack",
}

ROUTE_CONTRACTS = {
    "concept_card": {
        "[ROUTE-CONCEPT]",
        "[DOMAIN-LOCK]",
        "[THIRTY-SECOND]",
        "[DEFINITION-BOUNDARY]",
        "[EXAMPLE-CONTRAST]",
        "[ADAPTIVE-OUTPUT]",
    },
    "concept_card_offline": {
        "[ROUTE-OFFLINE]",
        "[DOMAIN-LOCK]",
        "[THIRTY-SECOND]",
        "[DEFINITION-BOUNDARY]",
        "[EXAMPLE-CONTRAST]",
        "[OFFLINE-DEGRADED]",
        "[UNKNOWN-PENDING-CHECK]",
        "[FULLTEXT-EVIDENCE]",
    },
    "concept_card_clarify": {
        "[ROUTE-CLARIFY-ONCE]",
        "[DOMAIN-LOCK]",
        "[AMBIGUITY-CANDIDATES]",
    },
    "concept_card_split": {
        "[ROUTE-SPLIT]",
        "[DOMAIN-LOCK]",
        "[ADAPTIVE-OUTPUT]",
    },
    "defer_sg_research": {"[ROUTE-SG-RESEARCH]"},
    "non_trigger": {"[ROUTE-NOT-APPLICABLE]"},
    "topic_map": {
        "[ROUTE-TOPIC-MAP]",
        "[DOMAIN-LOCK]",
        "[THIRTY-SECOND]",
        "[VERTICAL-AXIS]",
        "[HORIZONTAL-AXIS]",
        "[CROSS-INSIGHT]",
        "[TOPIC-MAP-OUTPUT]",
        "[ADAPTIVE-OUTPUT]",
    },
    "deep_map": {
        "[ROUTE-DEEP-MAP]",
        "[DOMAIN-LOCK]",
        "[THIRTY-SECOND]",
        "[VERTICAL-AXIS]",
        "[HORIZONTAL-AXIS]",
        "[CROSS-INSIGHT]",
        "[FIRST-PRINCIPLES]",
        "[INSIDER-GUIDE]",
        "[DEEP-MAP-OUTPUT]",
        "[VERIFY-SENSITIVE-CLAIMS]",
        "[SOURCE-HIERARCHY]",
        "[FULLTEXT-EVIDENCE]",
        "[NEARBY-CITATIONS]",
        "[CITATION-INTEGRITY]",
        "[EVIDENCE-LABELS]",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate sg-blackcat contracts.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    return parser.parse_args()


def decide_route(scenario: dict[str, Any]) -> str:
    """只依据冻结场景判路由，不读取 prompt 或 expected。"""
    request_kind = scenario["request_kind"]
    if request_kind in NON_TRIGGER_KINDS:
        return "non_trigger"
    if request_kind in DEFER_KINDS:
        return "defer_sg_research"
    if scenario["concept_count"] > 5:
        return "concept_card_split"
    if scenario["ambiguity"] == "answer_changing":
        return "concept_card_clarify"
    if scenario["evidence_state"] in {"offline", "search_only"}:
        return "concept_card_offline"
    if request_kind == "deep_exploration":
        return "deep_map"
    if request_kind == "topic_exploration" or str(scenario["object_kind"]).startswith("complex_"):
        return "topic_map"
    if scenario["object_kind"] in {"bounded_topic", "work", "product", "technology", "subculture", "hobby"}:
        return "topic_map"
    return "concept_card"


def decide_contracts(scenario: dict[str, Any], route: str) -> set[str]:
    """由路由和冻结风险信号计算必须合同。"""
    contracts = set(ROUTE_CONTRACTS[route])
    if route not in {"concept_card", "concept_card_offline", "topic_map", "deep_map"}:
        if route == "concept_card_clarify" and scenario["risk"] != "ordinary":
            contracts.add("[HIGH-RISK-EDUCATION]")
        return contracts

    flags = set(scenario["flags"])
    request_kind = scenario["request_kind"]
    evidence_state = scenario["evidence_state"]

    if route in {"topic_map", "deep_map"}:
        contracts.update({"[VERTICAL-AXIS]", "[HORIZONTAL-AXIS]", "[CROSS-INSIGHT]"})
    if route == "deep_map":
        contracts.update({"[FIRST-PRINCIPLES]", "[INSIDER-GUIDE]", "[DEEP-MAP-OUTPUT]"})

    if scenario["ambiguity"] == "manageable":
        contracts.add("[AMBIGUITY-CANDIDATES]")
    if scenario["object_kind"] == "acronym":
        contracts.add("[ACRONYM-DOMAIN]")
    if "spelling_candidate" in flags:
        contracts.add("[SPELLING-TRANSPARENCY]")
    if request_kind == "concept_distinction" or "needs_distinction" in flags:
        contracts.add("[NEIGHBOR-DISTINCTION]")
    if "short_answer" in flags:
        contracts.add("[SHORT-ANSWER]")
    if request_kind == "translation_loss" or "translation_loss" in flags:
        contracts.add("[TRANSLATION-LOSS]")
    if request_kind == "learning_check" or "learning" in flags:
        contracts.update({"[LEARNING-CHECK]", "[LEARNING-TRANSFER]"})
    if request_kind == "writing_material" or "writing_material" in flags:
        contracts.update({"[WRITING-NO-GHOSTWRITE]", "[WRITING-MATERIAL]"})
    if "history" in flags:
        contracts.add("[WORD-CONCEPT-HISTORY]")
    if flags.intersection({"history", "sensitive_claim", "dynamic_usage", "current_landscape", "community_usage", "insider_culture"}):
        contracts.update(
            {
                "[VERIFY-SENSITIVE-CLAIMS]",
                "[SOURCE-HIERARCHY]",
                "[FULLTEXT-EVIDENCE]",
                "[NEARBY-CITATIONS]",
                "[EVIDENCE-LABELS]",
            }
        )
    if flags.intersection({"dynamic_usage", "current_landscape"}):
        contracts.add("[DYNAMIC-AS-OF]")
    if "controversial" in flags:
        contracts.update({"[EVIDENCE-LABELS]", "[UNCERTAINTY-TYPES]"})
    if evidence_state in {"source_conflict", "disputed_current"}:
        contracts.update(
            {"[CONFLICT-LINEAGE]", "[UNCERTAINTY-TYPES]", "[EVIDENCE-LABELS]"}
        )
    if evidence_state == "broken_citation":
        contracts.update(
            {"[CITATION-INTEGRITY]", "[NEARBY-CITATIONS]", "[CORRECTION-PROTOCOL]"}
        )
    if evidence_state == "untrusted_instructions":
        contracts.add("[PROMPT-INJECTION]")
    if "causal_claim" in flags:
        contracts.update({"[CAUSALITY-GATE]", "[EVIDENCE-LABELS]", "[UNCERTAINTY-TYPES]"})
    if "original_example" in flags:
        contracts.add("[EVIDENCE-LABELS]")
    if "correction" in flags:
        contracts.add("[CORRECTION-PROTOCOL]")
    if scenario["risk"] != "ordinary":
        contracts.update(
            {"[HIGH-RISK-EDUCATION]", "[SOURCE-HIERARCHY]", "[FULLTEXT-EVIDENCE]"}
        )
    if route == "concept_card_offline" and flags.intersection(
        {"history", "sensitive_claim", "dynamic_usage", "controversial"}
    ):
        contracts.add("[UNKNOWN-PENDING-CHECK]")
    return contracts


def runtime_contract_markers() -> set[str]:
    markers: set[str] = set()
    for path in (SKILL_ROOT / "references").glob("*.md"):
        markers.update(re.findall(r"\[[A-Z][A-Z0-9-]+\]", path.read_text(encoding="utf-8")))
    return markers


def validate_runtime() -> list[str]:
    required = {
        "SKILL.md",
        "agents/openai.yaml",
        "references/scope-and-routing.md",
        "references/concept-workflow.md",
        "references/evidence-and-source-policy.md",
        "references/output-contract.md",
        "references/uncertainty-and-correction.md",
        "scripts/run_eval.py",
        "tests/test_contract.py",
    }
    errors = [f"missing_runtime_file:{path}" for path in sorted(required) if not (SKILL_ROOT / path).is_file()]
    if (SKILL_ROOT / "assets").exists():
        errors.append("unexpected_assets_directory")
    return errors


def validate_scenario(scenario: Any) -> list[str]:
    if not isinstance(scenario, dict):
        return ["scenario_not_object"]
    errors: list[str] = []
    if scenario.get("request_kind") not in REQUEST_KINDS:
        errors.append("invalid_request_kind")
    if scenario.get("object_kind") not in OBJECT_KINDS:
        errors.append("invalid_object_kind")
    count = scenario.get("concept_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        errors.append("invalid_concept_count")
    if scenario.get("ambiguity") not in AMBIGUITY_LEVELS:
        errors.append("invalid_ambiguity")
    if scenario.get("evidence_state") not in EVIDENCE_STATES:
        errors.append("invalid_evidence_state")
    if scenario.get("risk") not in RISK_LEVELS:
        errors.append("invalid_risk")
    flags = scenario.get("flags")
    if not isinstance(flags, list) or any(not isinstance(item, str) for item in flags):
        errors.append("invalid_flags")
    elif len(flags) != len(set(flags)) or not set(flags).issubset(FLAGS):
        errors.append("invalid_flags")
    return errors


def load_cases(fixtures_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    if not fixtures_root.is_dir():
        return [], ["fixtures_directory_missing"]
    cases: list[dict[str, Any]] = []
    errors: list[str] = []
    for directory in sorted(path for path in fixtures_root.iterdir() if path.is_dir()):
        files = sorted(path.name for path in directory.iterdir() if path.is_file())
        if files != ["case.json"]:
            errors.append(f"fixture_file_shape:{directory.name}")
            continue
        try:
            case = json.loads((directory / "case.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            errors.append(f"fixture_json_invalid:{directory.name}")
            continue
        if not isinstance(case, dict):
            errors.append(f"fixture_not_object:{directory.name}")
            continue
        case["_directory"] = directory.name
        cases.append(case)
    return cases, errors


def validate_case_shape(case: dict[str, Any], known_markers: set[str]) -> list[str]:
    errors: list[str] = []
    required_keys = {"schema_version", "id", "category", "prompt", "scenario", "expected", "_directory"}
    if set(case) != required_keys:
        errors.append("case_keys_invalid")
    if case.get("schema_version") != "1.0.0":
        errors.append("schema_version_invalid")
    case_id = case.get("id")
    if not isinstance(case_id, str) or case_id != case.get("_directory"):
        errors.append("case_id_directory_mismatch")
    if not isinstance(case.get("category"), str):
        errors.append("category_invalid")
    if not isinstance(case.get("prompt"), str) or not case.get("prompt", "").strip():
        errors.append("prompt_invalid")
    errors.extend(validate_scenario(case.get("scenario")))
    expected = case.get("expected")
    if not isinstance(expected, dict) or set(expected) != {"route", "contracts"}:
        errors.append("expected_shape_invalid")
    else:
        if expected.get("route") not in ROUTES:
            errors.append("expected_route_invalid")
        contracts = expected.get("contracts")
        if (
            not isinstance(contracts, list)
            or any(not isinstance(item, str) for item in contracts)
            or contracts != sorted(set(contracts))
        ):
            errors.append("expected_contracts_invalid")
        elif not set(contracts).issubset(known_markers):
            errors.append("expected_contract_marker_missing")
    return errors


def evaluate(fixtures_root: Path) -> tuple[dict[str, Any], int]:
    suite_errors = validate_runtime()
    known_markers = runtime_contract_markers()
    cases, load_errors = load_cases(fixtures_root)
    suite_errors.extend(load_errors)

    ids = [case.get("id") for case in cases]
    categories = [case.get("category") for case in cases]
    if set(ids) != set(CASE_MANIFEST) or len(ids) != len(CASE_MANIFEST):
        suite_errors.append("frozen_case_ids_changed")
    if len(categories) != len(set(categories)):
        suite_errors.append("duplicate_categories")
    for case_id, category in CASE_MANIFEST.items():
        matching = [case for case in cases if case.get("id") == case_id]
        if len(matching) == 1 and matching[0].get("category") != category:
            suite_errors.append(f"frozen_category_changed:{case_id}")

    results: list[dict[str, Any]] = []
    for case in cases:
        errors = validate_case_shape(case, known_markers)
        assertions = 1
        if not errors:
            route = decide_route(case["scenario"])
            contracts = decide_contracts(case["scenario"], route)
            assertions += 2
            if route != case["expected"]["route"]:
                errors.append("route_decision_failed")
            if contracts != set(case["expected"]["contracts"]):
                errors.append("contract_decision_failed")
        results.append(
            {
                "id": case.get("id", case.get("_directory", "unknown")),
                "category": case.get("category", "unknown"),
                "status": "pass" if not errors else "fail",
                "assertions": assertions,
                "errors": errors,
            }
        )

    total = len(results)
    passed = sum(result["status"] == "pass" for result in results)
    failed = total - passed
    payload = {
        "scope": "structure_and_normalized_routing_contracts_only",
        "total": total,
        "passed": passed,
        "failed": failed,
        "passRate": round((passed / total * 100.0) if total else 0.0, 1),
        "totalAssertions": sum(result["assertions"] for result in results),
        "results": results,
        "suiteErrors": sorted(set(suite_errors)),
    }
    if suite_errors:
        return payload, 2
    return payload, 0 if failed == 0 else 1


def render_text(payload: dict[str, Any]) -> str:
    lines = [
        "Scope: structure and normalized routing contracts only",
        f"Cases: {payload['passed']}/{payload['total']} passed",
        f"Assertions: {payload['totalAssertions']}",
    ]
    for result in payload["results"]:
        if result["status"] == "fail":
            lines.append(f"FAIL {result['id']}: {', '.join(result['errors'])}")
    for error in payload["suiteErrors"]:
        lines.append(f"SUITE ERROR: {error}")
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    payload, exit_code = evaluate(args.fixtures.resolve())
    if args.format == "json":
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write(render_text(payload))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
