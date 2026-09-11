#!/usr/bin/env python3
"""运行 sg-title 冻结 Golden cases。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from title_guard import classify_route, load_profiles, validate_title


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = SKILL_ROOT / "tests" / "fixtures" / "golden_cases.json"
TEST_OVERRIDES = SKILL_ROOT / "tests" / "fixtures" / "platform-overrides.json"


def merge_profiles(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(base, ensure_ascii=False))
    merged.setdefault("platforms", {}).update(override.get("platforms") or {})
    return merged


def load_eval_profiles(extra_path: Path | None = None) -> dict[str, Any]:
    profiles = load_profiles()
    if TEST_OVERRIDES.exists():
        profiles = merge_profiles(
            profiles, json.loads(TEST_OVERRIDES.read_text(encoding="utf-8"))
        )
    if extra_path:
        profiles = merge_profiles(
            profiles, json.loads(extra_path.read_text(encoding="utf-8"))
        )
    return profiles


def evaluate_case(case: dict[str, Any], profiles: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    actual: dict[str, Any]
    expected = case.get("expected") or {}
    if case.get("kind") == "route":
        route = classify_route(str(case.get("raw_request") or ""))
        actual = {"route": route}
        if route != expected.get("route"):
            failures.append(f"route 期望 {expected.get('route')}，实际 {route}")
    else:
        actual = validate_title(case.get("request") or {}, profiles)
        if actual.get("allowed") != expected.get("allowed"):
            failures.append(
                f"allowed 期望 {expected.get('allowed')}，实际 {actual.get('allowed')}"
            )
        error_codes = {item["code"] for item in actual.get("errors") or []}
        warning_codes = {item["code"] for item in actual.get("warnings") or []}
        for code in expected.get("error_codes") or []:
            if code not in error_codes:
                failures.append(f"errors 缺少 {code}，实际 {sorted(error_codes)}")
        for code in expected.get("warning_codes") or []:
            if code not in warning_codes:
                failures.append(f"warnings 缺少 {code}，实际 {sorted(warning_codes)}")
        if "active_profile_id" in expected:
            if actual.get("active_profile_id") != expected["active_profile_id"]:
                failures.append(
                    "active_profile_id 期望 "
                    f"{expected['active_profile_id']}，实际 {actual.get('active_profile_id')}"
                )
    return {
        "id": case.get("id"),
        "kind": case.get("kind", "guard"),
        "tags": case.get("tags") or [],
        "passed": not failures,
        "failures": failures,
        "actual": actual,
    }


def build_acceptance(results: list[dict[str, Any]]) -> dict[str, Any]:
    allowed_guard_results = [
        item
        for item in results
        if item["kind"] == "guard" and item["actual"].get("allowed")
    ]
    unsupported = sum(
        len(item["actual"]["checks"].get("unsupported_core_terms") or [])
        for item in allowed_guard_results
    )
    unverified = sum(
        len(item["actual"]["checks"].get("unverified_attribute_hits") or [])
        for item in allowed_guard_results
    )
    forbidden = sum(
        len(item["actual"]["checks"].get("forbidden_hits") or [])
        for item in allowed_guard_results
    )
    required_total = sum(
        item["actual"]["checks"].get("required_terms_total", 0)
        for item in allowed_guard_results
    )
    required_met = sum(
        item["actual"]["checks"].get("required_terms_met", 0)
        for item in allowed_guard_results
    )
    active_total = len(allowed_guard_results)
    active_passed = sum(
        1 for item in allowed_guard_results if item["actual"]["checks"]["hard_rule_compliant"]
    )
    cross_profile_leakage = sum(
        1
        for item in results
        if "跨profile泄漏" in item["tags"]
        and item["actual"].get("active_profile_id") is not None
    )
    return {
        "无来源核心词": unsupported,
        "未证实属性": unverified,
        "必留覆盖率": round(required_met / required_total * 100, 1)
        if required_total
        else 100.0,
        "禁用命中": forbidden,
        "激活规则合规率": round(active_passed / active_total * 100, 1)
        if active_total
        else 0.0,
        "跨profile泄漏": cross_profile_leakage,
    }


def run_all(
    cases_path: Path = DEFAULT_CASES,
    profiles_path: Path | None = None,
    only: set[str] | None = None,
) -> dict[str, Any]:
    fixture = json.loads(cases_path.read_text(encoding="utf-8"))
    cases = fixture.get("cases") or []
    if only:
        cases = [case for case in cases if case.get("id") in only]
    profiles = load_eval_profiles(profiles_path)
    results = [evaluate_case(case, profiles) for case in cases]
    passed = sum(1 for item in results if item["passed"])
    tags = sorted({tag for item in results for tag in item["tags"]})
    return {
        "suite": "sg-title-golden-cases",
        "frozen_at": fixture.get("frozen_at"),
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "skipped": 0,
        "pass_rate": round(passed / len(results) * 100, 1) if results else 0.0,
        "acceptance": build_acceptance(results),
        "coverage_tags": tags,
        "results": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--profiles", type=Path, help="额外平台 profile 覆盖，仅用于评测/临时证明")
    parser.add_argument("--only", action="append", default=[], help="只运行指定 case id，可重复")
    return parser.parse_args()


def render_text(result: dict[str, Any]) -> None:
    print(
        f"Golden cases: {result['passed']}/{result['total']} passed; "
        f"failed={result['failed']}; skipped={result['skipped']}"
    )
    for item in result["results"]:
        print(f"- {'PASS' if item['passed'] else 'FAIL'} {item['id']}")
        for failure in item["failures"]:
            print(f"  - {failure}")
    print("Acceptance: " + json.dumps(result["acceptance"], ensure_ascii=False))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = parse_args()
    result = run_all(args.cases, args.profiles, set(args.only) or None)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        render_text(result)
    acceptance = result["acceptance"]
    acceptance_ok = (
        acceptance["无来源核心词"] == 0
        and acceptance["未证实属性"] == 0
        and acceptance["必留覆盖率"] == 100.0
        and acceptance["禁用命中"] == 0
        and acceptance["激活规则合规率"] == 100.0
        and acceptance["跨profile泄漏"] == 0
    )
    return 0 if result["total"] and result["failed"] == 0 and acceptance_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
