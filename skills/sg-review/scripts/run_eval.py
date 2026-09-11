#!/usr/bin/env python3
"""执行 sg-review 的确定性 Golden Set。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any


def _default_root() -> Path:
    override = os.environ.get("SG_REVIEW_ROOT")
    return Path(override).resolve() if override else Path(__file__).resolve().parents[1]


def _load_runtime(root: Path) -> None:
    scripts = root / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))


def _resolve_path(value: Any, path: str) -> Any:
    if path == "":
        return value
    current = value
    for part in path.split("."):
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise KeyError(path)
    return current


def _contains_item(actual: Any, expected: dict[str, Any]) -> bool:
    return isinstance(actual, list) and any(
        isinstance(item, dict) and all(item.get(key) == value for key, value in expected.items())
        for item in actual
    )


def _check_assertion(result: Any, assertion: dict[str, Any]) -> tuple[bool, str]:
    path = assertion["path"]
    operation = assertion["op"]
    expected = assertion.get("value")
    try:
        actual = _resolve_path(result, path)
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        return False, f"路径 {path!r} 不存在: {exc}"

    if operation == "eq":
        passed = actual == expected
    elif operation == "contains":
        passed = expected in actual
    elif operation == "contains_item":
        passed = _contains_item(actual, expected)
    elif operation == "length_gte":
        passed = len(actual) >= int(expected)
    elif operation == "approx":
        passed = abs(float(actual) - float(expected)) <= 1e-6
    elif operation == "serialized_not_contains":
        passed = str(expected) not in json.dumps(actual, ensure_ascii=False, sort_keys=True)
    else:
        return False, f"未知断言操作: {operation}"
    if passed:
        return True, ""
    return False, f"{path or '<root>'} {operation}: actual={actual!r}, expected={expected!r}"


def _execute_case(case: dict[str, Any], root: Path) -> Any:
    from review_stats import AnalysisConfig, analyze_payload, analyze_records, assess_task_scope, load_input

    if case["kind"] == "route":
        return {"route": assess_task_scope(case["task"])}
    defaults = asdict(AnalysisConfig())
    defaults.update(case.get("config", {}))
    config = AnalysisConfig(**defaults)
    annotations = case.get("annotations", [])
    comparison_scope = case.get("comparison_scope")
    if case["kind"] == "analysis":
        return analyze_payload(case.get("payload", {}), annotations, config, comparison_scope)
    if case["kind"] == "file":
        records, metadata = load_input(root / case["input"])
        return analyze_records(records, metadata, annotations, config, comparison_scope)
    raise ValueError(f"未知 case kind: {case['kind']}")


def run(root: Path, cases_path: Path) -> int:
    _load_runtime(root)
    payload = json.loads(cases_path.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    if not isinstance(cases, list) or not cases:
        print("[FAIL] Golden Set 为空")
        return 2
    ids = [case.get("id") for case in cases]
    if len(ids) != len(set(ids)):
        print("[FAIL] Golden Set case id 不唯一")
        return 2
    categories = {case.get("category") for case in cases}
    if None in categories or len(categories) < 12:
        print(f"[FAIL] Golden Set 类别不足 12，实际 {len(categories - {None})}")
        return 2

    failures: list[str] = []
    for case in cases:
        assertions = case.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            failures.append(f"{case.get('id', '<unknown>')}: assertions 必须是非空数组")
            print(f"[FAIL] {case.get('id', '<unknown>')} | assertions-empty")
            continue
        try:
            result = _execute_case(case, root)
            case_failures = []
            for assertion in assertions:
                passed, message = _check_assertion(result, assertion)
                if not passed:
                    case_failures.append(message)
            if case_failures:
                failures.append(f"{case['id']}: " + " | ".join(case_failures))
                print(f"[FAIL] {case['id']} | {case['category']}")
            else:
                print(f"[PASS] {case['id']} | {case['category']}")
        except Exception as exc:  # Golden runner 必须把异常作为失败证据展示。
            failures.append(f"{case.get('id', '<unknown>')}: {type(exc).__name__}: {exc}")
            print(f"[FAIL] {case.get('id', '<unknown>')} | exception")

    print(f"Golden Set: {len(cases) - len(failures)}/{len(cases)} passed; categories={len(categories)}")
    if failures:
        for failure in failures:
            print(f"  - {failure}")
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行 sg-review Golden Set")
    parser.add_argument("--root", type=Path, default=_default_root())
    parser.add_argument("--cases", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    cases_path = args.cases.resolve() if args.cases else root / "tests" / "golden" / "cases.json"
    return run(root, cases_path)


if __name__ == "__main__":
    raise SystemExit(main())
