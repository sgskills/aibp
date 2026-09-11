#!/usr/bin/env python3
"""重新计算 sg-toplist Golden cases，并执行声明式断言。"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURES = SKILL_ROOT / "tests" / "fixtures"
REQUIRED_TAGS = {
    "single_period",
    "two_periods",
    "multi_period",
    "incomparable_island",
    "different_top_n",
    "missing_id",
    "duplicate_id",
    "missing_rank",
    "duplicate_rank",
    "link_reuse",
    "same_title_different_id",
    "entry",
    "platform_new_listed",
    "reentry",
    "exit_window",
    "interval_overlap",
    "missing_price",
    "missing_amount",
    "pollution",
    "all_network",
    "tmall_only",
    "own_product",
    "mode_consistency",
    "routing",
    "cell_injection",
    "corrupted_file",
}

if str(SKILL_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from analyze_rankings import analyze_payload  # noqa: E402
from ranking_engine import validate_result_guards  # noqa: E402


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _contains_forbidden_expected(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            str(key).lower() == "expected" or _contains_forbidden_expected(child)
            for key, child in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_forbidden_expected(child) for child in value)
    return False


def _resolve(document: Any, dotted_path: str) -> list[Any]:
    values: list[Any] = [document]
    for segment in dotted_path.split("."):
        expanded: list[Any] = []
        if segment == "*":
            for value in values:
                if isinstance(value, Mapping):
                    expanded.extend(value.values())
                elif isinstance(value, Sequence) and not isinstance(
                    value, (str, bytes, bytearray)
                ):
                    expanded.extend(value)
        else:
            for value in values:
                if isinstance(value, Mapping) and segment in value:
                    expanded.append(value[segment])
                elif (
                    isinstance(value, Sequence)
                    and not isinstance(value, (str, bytes, bytearray))
                    and segment.isdigit()
                ):
                    index = int(segment)
                    if 0 <= index < len(value):
                        expanded.append(value[index])
        values = expanded
    return values


def _text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _assert_result(result: Mapping[str, Any], assertion: Mapping[str, Any]) -> str | None:
    path = str(assertion.get("path", ""))
    operation = str(assertion.get("op", ""))
    target = assertion.get("value")
    actual = _resolve(result, path)

    if operation == "eq":
        return None if actual == [target] else f"{path}: {_text(actual)} != {_text(target)}"
    if operation == "contains":
        if any(
            target in value
            for value in actual
            if isinstance(value, (str, list, tuple, set, dict))
        ):
            return None
        return f"{path}: {_text(actual)} does not contain {_text(target)}"
    if operation == "not_contains":
        if all(
            target not in value
            for value in actual
            if isinstance(value, (str, list, tuple, set, dict))
        ):
            return None
        return f"{path}: {_text(actual)} unexpectedly contains {_text(target)}"
    if operation == "len":
        if len(actual) == 1 and hasattr(actual[0], "__len__") and len(actual[0]) == target:
            return None
        return f"{path}: length mismatch in {_text(actual)}"
    if operation == "ge":
        return None if len(actual) == 1 and actual[0] >= target else f"{path}: {_text(actual)} < {target}"
    if operation == "le":
        return None if len(actual) == 1 and actual[0] <= target else f"{path}: {_text(actual)} > {target}"
    if operation == "truthy":
        return None if len(actual) == 1 and bool(actual[0]) else f"{path}: not truthy"
    if operation == "falsy":
        return None if len(actual) == 1 and not bool(actual[0]) else f"{path}: not falsy"
    if operation == "regex":
        return (
            None
            if len(actual) == 1 and re.search(str(target), str(actual[0])) is not None
            else f"{path}: {_text(actual)} does not match {target!r}"
        )
    return f"{path}: unsupported assertion op {operation!r}"


def _execute_case(case: Mapping[str, Any], case_path: Path) -> Mapping[str, Any]:
    operation = str(case.get("operation", "analyze"))
    mode = str(case.get("mode", "auto"))
    if operation == "analyze":
        payload = case.get("input")
        if not isinstance(payload, Mapping):
            raise ValueError("analyze case input must be an object")
        return analyze_payload(payload, mode=mode)

    if operation == "corrupted_file":
        from audit_input import audit_paths

        with tempfile.TemporaryDirectory(prefix="sg-toplist-eval-") as temp_dir:
            broken = Path(temp_dir) / "broken.xlsx"
            broken.write_bytes(b"not an xlsx archive")
            return audit_paths([broken])

    raise ValueError(f"unsupported case operation: {operation} ({case_path})")


def _discover_cases(fixtures_dir: Path) -> list[Path]:
    return sorted(fixtures_dir.glob("*/case.json"), key=lambda path: path.parent.name)


def run_evaluations(fixtures_dir: Path = DEFAULT_FIXTURES) -> dict[str, Any]:
    case_paths = _discover_cases(fixtures_dir)
    failures: list[str] = []
    case_results: list[dict[str, Any]] = []
    tags_seen: set[str] = set()
    assertion_count = 0

    if len(case_paths) < 36:
        failures.append(f"MANIFEST: requires at least 36 cases, found {len(case_paths)}")

    ids: list[str] = []
    for path in case_paths:
        case_failures: list[str] = []
        try:
            case = _read_json(path)
            if not isinstance(case, Mapping):
                raise ValueError("case root must be an object")
            if _contains_forbidden_expected(case):
                raise ValueError("fixture must not contain an expected field")
            case_id = str(case.get("id", ""))
            if not case_id:
                raise ValueError("case id is required")
            ids.append(case_id)
            tags = case.get("tags")
            if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
                raise ValueError("tags must be a string array")
            tags_seen.update(tags)
            assertions = case.get("assertions")
            if not isinstance(assertions, list) or not assertions:
                raise ValueError("assertions must be a non-empty array")
            result = _execute_case(case, path)
            if str(case.get("operation", "analyze")) == "analyze":
                recomputed_guards = validate_result_guards(result)
                nonzero_guards = {
                    key: value for key, value in recomputed_guards.items() if value != 0
                }
                if nonzero_guards:
                    case_failures.append(
                        f"recomputed severe errors must be zero: {_text(nonzero_guards)}"
                    )
                if result.get("severe_error_guards") != recomputed_guards:
                    case_failures.append(
                        "published severe_error_guards differ from independent recomputation"
                    )
            assertion_count += len(assertions)
            for assertion in assertions:
                if not isinstance(assertion, Mapping):
                    case_failures.append("assertion must be an object")
                    continue
                failure = _assert_result(result, assertion)
                if failure is not None:
                    case_failures.append(failure)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            case_id = path.parent.name
            case_failures.append(f"{type(exc).__name__}: {exc}")

        if case_failures:
            failures.extend(f"{case_id}: {failure}" for failure in case_failures)
            case_results.append({"id": case_id, "status": "FAIL", "failures": case_failures})
        else:
            case_results.append(
                {"id": case_id, "status": "PASS", "assertions": len(assertions)}
            )

    if len(ids) != len(set(ids)):
        failures.append("MANIFEST: case ids must be unique")
    missing_tags = sorted(REQUIRED_TAGS - tags_seen)
    if missing_tags:
        failures.append(f"MANIFEST: missing coverage tags: {', '.join(missing_tags)}")

    passed = sum(result["status"] == "PASS" for result in case_results)
    return {
        "total": len(case_paths),
        "passed": passed,
        "failed": len(case_paths) - passed + sum(item.startswith("MANIFEST:") for item in failures),
        "assertions": assertion_count,
        "coverage_tags": sorted(tags_seen),
        "missing_tags": missing_tags,
        "failures": failures,
        "cases": case_results,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run sg-toplist deterministic Golden cases.")
    parser.add_argument("--fixtures-dir", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    summary = run_evaluations(args.fixtures_dir.resolve())
    if args.format == "json":
        sys.stdout.write(json.dumps(summary, ensure_ascii=False, sort_keys=True) + "\n")
    else:
        for case in summary["cases"]:
            sys.stdout.write(f"{case['status']} {case['id']}\n")
        for failure in summary["failures"]:
            sys.stdout.write(f"FAIL {failure}\n")
        sys.stdout.write(
            "SUMMARY "
            f"total={summary['total']} passed={summary['passed']} "
            f"failed={summary['failed']} assertions={summary['assertions']}\n"
        )
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
