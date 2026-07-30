#!/usr/bin/env python3
"""运行 sg-skill-optimizer 的可执行 Golden Set。

用法：
  python run_eval.py
  python run_eval.py --format json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


SKILL_ROOT = Path(__file__).resolve().parents[1]
HEALTH_CHECK = SKILL_ROOT / "scripts" / "health_check.py"
FIXTURE_ROOT = SKILL_ROOT / "tests" / "fixtures"


def run_case(case_path: Path) -> dict[str, Any]:
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case_root = case_path.parent
    target = (case_root / case["target"]).resolve()
    command = [
        sys.executable,
        "-B",
        str(HEALTH_CHECK),
        str(target),
        "--format",
        "json",
    ]
    if case.get("skillsRoot"):
        command.extend(["--skills-root", str((case_root / case["skillsRoot"]).resolve())])

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=SKILL_ROOT,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return {
            "id": case["id"],
            "passed": False,
            "failures": ["health_check 超过 15 秒，已终止"],
            "exitCode": None,
        }
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        return {
            "id": case["id"],
            "passed": False,
            "failures": [f"输出不是合法 JSON：{error}"],
            "exitCode": completed.returncode,
        }

    expected = case["expected"]
    failures: list[str] = []
    if "blocked" in expected and report.get("blocked") != expected["blocked"]:
        failures.append(
            f"blocked 期望 {expected['blocked']}，实际 {report.get('blocked')}"
        )
    if "minScore" in expected and report.get("totalScore", 0) < expected["minScore"]:
        failures.append(
            f"totalScore 期望 ≥{expected['minScore']}，实际 {report.get('totalScore')}"
        )
    if "maxScore" in expected and report.get("totalScore", 100) > expected["maxScore"]:
        failures.append(
            f"totalScore 期望 ≤{expected['maxScore']}，实际 {report.get('totalScore')}"
        )
    if "evaluationState" in expected:
        actual = report.get("evaluation", {}).get("state")
        if actual != expected["evaluationState"]:
            failures.append(
                f"evaluation.state 期望 {expected['evaluationState']}，实际 {actual}"
            )
    if "crossSkillStatus" in expected:
        actual = report.get("triggerAudit", {}).get("crossSkillStatus")
        if actual != expected["crossSkillStatus"]:
            failures.append(
                f"crossSkillStatus 期望 {expected['crossSkillStatus']}，实际 {actual}"
            )
    for text in expected.get("blockerContains", []):
        if not any(text in blocker for blocker in report.get("blockers", [])):
            failures.append(f"blockers 未包含：{text}")
    for dimension_name, maximum in expected.get("dimensionMax", {}).items():
        dimension = next(
            (
                item
                for item in report.get("dimensions", [])
                if item["name"] == dimension_name
            ),
            None,
        )
        if dimension is None:
            failures.append(f"缺少维度：{dimension_name}")
        elif dimension.get("score", 100) > maximum:
            failures.append(
                f"{dimension_name} 期望 ≤{maximum}，实际 {dimension.get('score')}"
            )

    return {
        "id": case["id"],
        "passed": not failures,
        "failures": failures,
        "exitCode": completed.returncode,
        "score": report.get("totalScore"),
        "grade": report.get("grade"),
    }


def run_all() -> dict[str, Any]:
    case_paths = sorted(FIXTURE_ROOT.glob("*/case.json"))
    results = [run_case(path) for path in case_paths]
    passed = sum(1 for result in results if result["passed"])
    total = len(results)
    return {
        "suite": "sg-skill-optimizer-golden-set",
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "passRate": round(passed / total * 100, 1) if total else 0.0,
        "results": results,
    }


def render_text(result: dict[str, Any]) -> None:
    print(
        f"Golden Set：{result['passed']}/{result['total']} 通过 "
        f"({result['passRate']}%)"
    )
    for item in result["results"]:
        print(f"- {'PASS' if item['passed'] else 'FAIL'} {item['id']}")
        for failure in item["failures"]:
            print(f"  - {failure}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_all()
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        render_text(result)
    return 0 if result["failed"] == 0 and result["total"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
