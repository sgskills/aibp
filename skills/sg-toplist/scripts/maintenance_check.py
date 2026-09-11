#!/usr/bin/env python3
"""使用时检查30天本地复核时效；不联网、不安装、不自行升级。"""
from __future__ import annotations
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Sequence

INTERVAL_DAYS = 30
CHECK_SCOPE = "local_golden_and_syntax"
SKILL_ROOT = Path(__file__).resolve().parents[1]

def skill_fingerprint(root: Path) -> str:
    """内容而非mtime作为依据，代码、规则、测试与元数据变化立即失效。"""
    digest = hashlib.sha256()
    paths = [root / "SKILL.md"]
    for directory in ("scripts", "references", "agents", "tests"):
        paths.extend(p for p in (root / directory).rglob("*") if p.is_file() and p.suffix in {".py", ".md", ".json", ".yaml", ".yml"} and "__pycache__" not in p.parts)
    for path in sorted(set(paths)):
        if path.is_symlink():
            raise ValueError("Skill文件不能通过符号链接替换已核验内容")
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()

def maintenance_status(root: Path = SKILL_ROOT, state_path: Path | None = None, *, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    result: dict[str, Any] = {
        "interval_days": INTERVAL_DAYS, "check_due": True, "status": "due", "reason": "missing_state",
        "checked_at": None, "remote_update_status": "unverified_not_configured", "automatic_network": False,
        "automatic_install": False, "state_written": False, "check_scope": CHECK_SCOPE,
        "message": "本地维护检查待执行；未配置已确认上游，无法判断是否有新版。当前榜单分析可继续。",
    }
    try:
        fingerprint = skill_fingerprint(root)
        result["skill_fingerprint"] = fingerprint
        if state_path is None or not state_path.exists():
            return result
        if state_path.stat().st_size > 65536:
            raise ValueError("维护状态文件过大")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or state.get("schema_version") != 1 or state.get("check_scope") != CHECK_SCOPE:
            raise ValueError("维护状态schema不支持")
        checked = datetime.fromisoformat(state["last_checked_at"])
        if checked.tzinfo is None or current.tzinfo is None:
            raise ValueError("维护时间须包含时区")
        age = (current - checked).total_seconds()
        result["checked_at"] = checked.isoformat()
        if age < 0:
            result["reason"] = "future_timestamp"
        elif state.get("skill_fingerprint") != fingerprint:
            result["reason"] = "skill_changed"
        elif age >= INTERVAL_DAYS * 86400:
            result["reason"] = "30_days_elapsed"
        else:
            result.update(check_due=False, status="current", reason="within_30_days")
            result["message"] = "同指纹本地复核未满30天；复用本地检查状态，不代表核验过上游新版或获准发布。"
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        result.update(status="due", check_due=True, reason="invalid_or_unreadable_state")
    return result

def record_local_check(state_path: Path, root: Path = SKILL_ROOT) -> dict[str, Any]:
    """只有真实语法和Golden复跑通过才落盘；失败不刷新旧时间。"""
    state_path = state_path.resolve()
    if state_path.suffix.lower() != ".json" or state_path.is_relative_to(root.resolve()):
        raise ValueError("维护状态须为Skill目录外、用户明确指定的JSON文件")
    before = skill_fingerprint(root)
    for source in (root / "scripts").glob("*.py"):
        ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    command = [sys.executable, "-B", str(root / "scripts/run_eval.py"), "--format", "json"]
    completed = subprocess.run(command, cwd=root, env=env, capture_output=True, timeout=120)
    report = json.loads(completed.stdout.decode("utf-8"))
    if completed.returncode or not isinstance(report, dict) or report.get("failed") != 0 or report.get("passed", 0) < 48 or report.get("assertions", 0) < 137:
        raise ValueError("本地Golden未通过，维护状态不更新")
    if skill_fingerprint(root) != before:
        raise ValueError("检查期间Skill变化，维护状态不更新")
    state = {"schema_version": 1, "last_checked_at": datetime.now(timezone.utc).isoformat(), "skill_fingerprint": before, "check_scope": CHECK_SCOPE, "golden": {k: report[k] for k in ("passed", "failed", "assertions")}, "remote_update_status": "unverified_not_configured"}
    # 同目录原子替换避免中断留下半截状态；显式输出路径不默认写入安装目录。
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=state_path.parent, suffix=".json.tmp", delete=False) as handle:
            temporary = handle.name
            json.dump(state, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, state_path)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
    return {**maintenance_status(root, state_path), "state_written": True, "golden": state["golden"]}

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, help="用户工作目录中的维护状态JSON；不提供则只提示首检")
    parser.add_argument("--record", action="store_true", help="实际复跑本地语法与Golden，通过后更新指定状态")
    args = parser.parse_args(argv)
    if args.record and args.state is None:
        parser.error("--record需要明确--state输出路径")
    try:
        result = record_local_check(args.state) if args.record else maintenance_status(state_path=args.state)
    except (OSError, ValueError, SyntaxError, subprocess.TimeoutExpired) as exc:
        sys.stdout.write(json.dumps({"status": "check_failed", "state_written": False, "error": str(exc)}, ensure_ascii=False) + "\n")
        return 2
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
