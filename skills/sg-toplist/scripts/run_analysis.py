#!/usr/bin/env python3
"""有超时和输出契约检查的分析入口；失败时只报告运行问题。"""
from __future__ import annotations
import argparse
import html
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence

def _failure(code: str, message: str, **details: Any) -> dict[str, Any]:
    issue = {"code": code, "severity": "error", "message": message, "evidence": details}
    return {
        "status": "rejected",
        "runtime_error": {"code": code, "message": message, **details},
        "audit": {
            "valid": False,
            "status": "blocking",
            "conclusion": message,
            "error_count": 1,
            "warning_count": 0,
            "issues": [issue],
            "period_count": 0,
            "islands": [],
            "comparisons": [],
        },
        "facts": [],
        "opportunities": [],
        "actions": {"product_selection": None, "product_development": None, "main_promotion": None},
        "max_limitation": "分析程序未成功完成；不能使用旧输出代替本次结果。",
    }

def run_checked(
    command: list[str], *, timeout: float = 60, result_exit_codes: frozenset[int] = frozenset()
) -> tuple[dict[str, Any], int]:
    """调用方提供已授权的固定程序；CLI不接受任意命令或shell片段。"""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    try:
        completed = subprocess.run(command, env=env, capture_output=True, timeout=timeout, shell=False)
    except subprocess.TimeoutExpired:
        return _failure("TIMEOUT", "分析超时，子进程已终止；缩小输入范围或确认合理时限", timeout_seconds=timeout), 3
    except OSError as exc:
        return _failure("START_FAILED", "无法启动分析程序；检查解释器和入口路径", error_type=type(exc).__name__), 3
    # 默认不采信非零进程碰巧输出的 JSON。只有调用方明确列出的业务结果码
    # 才继续校验完整契约；本 CLI 仅为固定 analyze_rankings.py 放行其拒绝码 2。
    stderr = completed.stderr.decode("utf-8", errors="replace")[-4000:]
    if completed.returncode and completed.returncode not in result_exit_codes:
        return _failure("NONZERO_EXIT", "分析程序返回非零退出码", exit_code=completed.returncode, stderr=stderr), 3
    if len(completed.stdout) > 32 * 1024 * 1024:
        return _failure("OUTPUT_TOO_LARGE", "分析输出超过32MiB，拆分独立数据岛后重跑"), 3
    try:
        result = json.loads(completed.stdout.decode("utf-8"))
        if not isinstance(result, dict) or result.get("status") not in {"analyzed", "limited", "partial", "rejected"}:
            raise ValueError("status字段无效")
        for field, kind in (("audit", dict), ("facts", list), ("opportunities", list), ("actions", dict)):
            if not isinstance(result.get(field), kind):
                raise ValueError(f"{field}字段缺失或类型错误")
    except (UnicodeError, ValueError) as exc:
        return _failure("INVALID_OUTPUT", "分析输出不是有效的结果JSON", detail=str(exc), stderr=stderr), 3
    expected_code = 2 if result["status"] == "rejected" else 0
    if completed.returncode != expected_code:
        return _failure(
            "EXIT_STATUS_MISMATCH",
            "分析状态与子进程退出码不一致",
            exit_code=completed.returncode,
            result_status=result["status"],
            stderr=stderr,
        ), 3
    return result, expected_code

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="XLSX/CSV/TSV路径")
    parser.add_argument("--mode", choices=("auto", "quick", "deep"), default="auto")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--own-store", action="append", default=[])
    parser.add_argument("--request", default="")
    parser.add_argument("--maintenance-state", type=Path)
    parser.add_argument("--select-revision", action="append", default=[])
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args(argv)
    if not 0 < args.timeout <= 600:
        parser.error("--timeout须大于0且不超过600秒")
    command = [sys.executable, "-B", str(Path(__file__).with_name("analyze_rankings.py")), *args.paths, "--mode", args.mode, "--format", "json", "--request", args.request]
    for store in args.own_store:
        command.extend(["--own-store", store])
    if args.maintenance_state:
        command.extend(["--maintenance-state", str(args.maintenance_state)])
    for digest in args.select_revision:
        command.extend(["--select-revision", digest])
    result, code = run_checked(command, timeout=args.timeout, result_exit_codes=frozenset({2}))
    if args.format == "json":
        output = json.dumps(result, ensure_ascii=False, indent=2)
    elif "runtime_error" in result:
        output = "# 分析未完成\n\n" + html.escape(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        from analyze_rankings import render_markdown
        output = render_markdown(result)
    sys.stdout.write(output + "\n")
    return code

if __name__ == "__main__":
    raise SystemExit(main())
