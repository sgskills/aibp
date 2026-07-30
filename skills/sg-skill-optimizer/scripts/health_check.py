#!/usr/bin/env python3
"""对单个 Agent Skill 进行静态体检，并显式区分真实回归状态。

用法：
  python health_check.py <skill目录>
  python health_check.py <skill目录> --format json
  python health_check.py <skill目录> --skills-root <skills根目录>
  python health_check.py <skill目录> --verify-eval
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

from common import (
    ANTI_TRIGGER_HINTS,
    detect_trigger_overlaps,
    first_sentence,
    has_any,
    parse_frontmatter,
    read_text,
    referenced_resource_paths,
)


try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


DIMENSIONS: "OrderedDict[str, int]" = OrderedDict(
    [
        ("结构与上下文健康", 12),
        ("触发与路由质量", 15),
        ("任务契约清晰度", 9),
        ("执行流程可操作性", 9),
        ("输出稳定性", 10),
        ("运行稳定性与故障恢复", 10),
        ("工具化与确定性", 8),
        ("评测与回归能力", 10),
        ("沉淀与演进", 5),
        ("安全与边界", 8),
        ("可维护性", 4),
    ]
)

STATUS_PRIORITY = {"FAIL": 0, "WARN": 1, "MANUAL": 2, "N/A": 3, "OK": 4}


def add_check(
    checks: list[dict[str, Any]],
    dimension: str,
    item: str,
    status: str,
    max_points: float,
    evidence: str,
    recommendation: str,
    *,
    points: float | None = None,
    blocker: bool = False,
    method: str = "",
) -> None:
    if points is None:
        points = max_points if status == "OK" else 0.0
    checks.append(
        {
            "dimension": dimension,
            "item": item,
            "status": status,
            "points": float(points),
            "maxPoints": float(max_points),
            "scored": status not in {"MANUAL", "N/A"},
            "evidence": evidence,
            "recommendation": recommendation,
            "method": method,
            "blocker": blocker,
        }
    )


def line_count(text: str) -> int:
    return len(text.splitlines())


def load_operational_examples(skill_dir: Path) -> str:
    examples_path = skill_dir / "references" / "examples.md"
    return read_text(examples_path) if examples_path.is_file() else ""


def evaluation_state(
    skill_dir: Path,
    verify_eval: bool,
    allow_target_code: bool,
) -> dict[str, Any]:
    references_dir = skill_dir / "references"
    golden_files = (
        [
            path
            for path in references_dir.iterdir()
            if path.is_file() and re.search(r"golden|eval|基准", path.name, re.IGNORECASE)
        ]
        if references_dir.is_dir()
        else []
    )
    runner = skill_dir / "scripts" / "run_eval.py"
    fixture_root = skill_dir / "tests" / "fixtures"
    fixture_cases = (
        sorted(fixture_root.rglob("case.json"))
        if fixture_root.is_dir()
        else []
    )

    if not golden_files:
        state = "MISSING"
    elif runner.is_file() and len(fixture_cases) >= 3:
        state = "EXECUTABLE"
    else:
        state = "SPEC_ONLY"

    result: dict[str, Any] = {
        "state": state,
        "verified": False,
        "goldenFiles": [path.name for path in golden_files],
        "fixtureCount": len(fixture_cases),
        "runner": os.fspath(runner) if runner.is_file() else None,
        "passRate": None,
        "reportedPassRate": None,
        "lastError": None,
        "executionAuthorized": allow_target_code,
    }

    if verify_eval and state == "EXECUTABLE":
        if not allow_target_code:
            result["lastError"] = (
                "未执行目标代码：需要人工确认后显式提供 --allow-target-code"
            )
            return result
        try:
            completed = subprocess.run(
                [sys.executable, "-B", os.fspath(runner), "--format", "json"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=skill_dir,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            result["lastError"] = "目标 runner 超过 30 秒，已终止"
            return result
        try:
            eval_result = json.loads(completed.stdout)
        except json.JSONDecodeError:
            eval_result = {}
        total = eval_result.get("total")
        passed = eval_result.get("passed")
        failed = eval_result.get("failed")
        cases = eval_result.get("results")
        summary_consistent = (
            isinstance(total, int)
            and total >= 3
            and passed == total
            and failed == 0
            and eval_result.get("passRate") == 100.0
            and isinstance(cases, list)
            and len(cases) == total
            and all(
                isinstance(case, dict) and case.get("passed") is True
                for case in cases
            )
        )
        if completed.returncode == 0 and summary_consistent:
            result["state"] = "VERIFIED"
            result["verified"] = True
            result["passRate"] = 100.0
        else:
            result["passRate"] = None
            result["reportedPassRate"] = eval_result.get("passRate")
            if completed.returncode == 0 and not summary_consistent:
                result["lastError"] = (
                    "目标 runner 摘要一致性校验失败；自报通过率仅保留为 "
                    "reportedPassRate，不作为可信结果"
                )
            else:
                result["lastError"] = (
                    completed.stderr.strip()
                    or completed.stdout.strip()
                    or f"eval exit={completed.returncode}"
                )
    return result


def add_structure_checks(
    checks: list[dict[str, Any]],
    blockers: list[str],
    skill_dir: Path,
    parsed: dict[str, Any],
) -> None:
    valid = bool(parsed["valid"])
    add_check(
        checks,
        "结构与上下文健康",
        "frontmatter 可解析",
        "OK" if valid else "FAIL",
        3,
        "边界与核心字符串字段通过结构校验"
        if valid
        else "frontmatter 边界或核心字符串字段非法",
        "修复 frontmatter 边界、name 与 description 字符串字段。",
        blocker=not valid,
        method="#1",
    )
    if not valid:
        blockers.append("frontmatter 无法解析")

    name = str(parsed.get("name") or "")
    description = str(parsed.get("description") or "")
    for item, value, message in (
        ("frontmatter 含 name", name, "缺少非空 name"),
        ("frontmatter 含 description", description, "缺少非空 description"),
    ):
        ok = bool(value)
        add_check(
            checks,
            "结构与上下文健康",
            item,
            "OK" if ok else "FAIL",
            2,
            value if ok else message,
            f"补齐 {item.split()[-1]}。",
            blocker=not ok,
            method="#1/#5",
        )
        if not ok:
            blockers.append(message)

    body = str(parsed.get("body") or "")
    concise = line_count(body) <= 300
    add_check(
        checks,
        "结构与上下文健康",
        "SKILL.md 主体精简",
        "OK" if concise else "WARN",
        2,
        f"主体 {line_count(body)} 行",
        "主体超过 300 行时把非核心细节拆入 references/。",
        method="#1",
    )

    has_index = has_any(
        [r"资源索引", r"references/", r"scripts/", r"assets/", r"tests/"],
        body,
    )
    add_check(
        checks,
        "结构与上下文健康",
        "提供资源索引",
        "OK" if has_index else "WARN",
        1.5,
        "正文含资源入口" if has_index else "正文没有资源索引",
        "列出每个资源及何时读取或运行。",
        method="#1",
    )

    missing = [
        path
        for path in referenced_resource_paths(body)
        if not (skill_dir / path).exists()
    ]
    add_check(
        checks,
        "结构与上下文健康",
        "直接引用资源存在",
        "OK" if not missing else "FAIL",
        1.5,
        "未发现缺失引用" if not missing else f"缺失：{', '.join(missing)}",
        "补齐缺失资源或删除无效引用。",
        blocker=bool(missing),
        method="#1",
    )
    if missing:
        blockers.append("SKILL.md 引用的资源缺失")


def add_trigger_checks(
    checks: list[dict[str, Any]],
    skill_dir: Path,
    parsed: dict[str, Any],
    skills_root: str | None,
    trigger_audit: dict[str, Any],
) -> None:
    description = str(parsed.get("description") or "")
    first = first_sentence(description)
    length_ok = len(description) <= 1024
    add_check(
        checks,
        "触发与路由质量",
        "description 长度",
        "OK" if length_ok else "WARN",
        3,
        f"{len(description)} 字符",
        "压缩到 1024 字符以内。",
        method="#5",
    )

    trigger_signal = has_any(
        [r"Use when", r"当用户", r"用于", r"诊断", r"优化", r"审计", r"触发"],
        first,
    )
    add_check(
        checks,
        "触发与路由质量",
        "核心触发词前置",
        "OK" if trigger_signal and len(first) <= 140 else "WARN",
        4,
        f"首句 {len(first)} 字符；触发信号={'有' if trigger_signal else '无'}",
        "第一句写清何时使用及核心对象。",
        method="#5",
    )

    anti_trigger = any(hint in description.casefold() for hint in ANTI_TRIGGER_HINTS)
    add_check(
        checks,
        "触发与路由质量",
        "包含反触发边界",
        "OK" if anti_trigger else "WARN",
        3,
        "检测到不适用场景" if anti_trigger else "未检测到反触发",
        "补充不适用于哪些相邻任务。",
        method="#5",
    )

    yaml_path = skill_dir / "agents" / "openai.yaml"
    add_check(
        checks,
        "触发与路由质量",
        "存在 agents/openai.yaml",
        "OK" if yaml_path.is_file() else "WARN",
        2,
        "元数据文件存在" if yaml_path.is_file() else "元数据文件缺失",
        "补充显示名、默认提示和触发策略。",
        method="#6/#19",
    )

    if skills_root:
        root_path = Path(skills_root)
        if root_path.is_dir():
            overlaps = detect_trigger_overlaps(
                skill_dir,
                str(parsed.get("name") or skill_dir.name),
                description,
                root_path,
            )
            trigger_audit["crossSkillStatus"] = "WARN" if overlaps else "OK"
            trigger_audit["overlaps"] = overlaps
            add_check(
                checks,
                "触发与路由质量",
                "跨 Skill 冲突审计",
                "WARN" if overlaps else "OK",
                3,
                (
                    "; ".join(
                        f"{item['skill']}({item['count']}词,{item['ratio']:.0%})"
                        for item in overlaps
                    )
                    if overlaps
                    else "未发现达到阈值的候选冲突"
                ),
                "人工确认真实语义边界后再调整描述或触发开关。",
                method="#6",
            )
        else:
            trigger_audit["crossSkillStatus"] = "N/A"
            trigger_audit["reason"] = "skills-root 不存在"
            add_check(
                checks,
                "触发与路由质量",
                "跨 Skill 冲突审计",
                "N/A",
                3,
                f"skills-root 不存在：{skills_root}",
                "提供有效根目录后再运行；当前不扣分。",
                method="#6",
            )
    else:
        trigger_audit["crossSkillStatus"] = "N/A"
        trigger_audit["reason"] = "未提供 skills-root；独立 Skill 场景不适用"
        add_check(
            checks,
            "触发与路由质量",
            "跨 Skill 冲突审计",
            "N/A",
            3,
            "未提供 skills-root；不扣分，也不算已通过",
            "仅在用户要求环境级审计时提供 skills-root。",
            method="#6",
        )


def add_behavior_checks(
    checks: list[dict[str, Any]],
    skill_dir: Path,
    parsed: dict[str, Any],
    evaluation: dict[str, Any],
) -> None:
    body = str(parsed.get("body") or "")
    examples = load_operational_examples(skill_dir)

    has_input_output = has_any(
        [r"\bINPUT\b", r"\bOUTPUT\b", r"输入.*输出", r"IPO\s*契约"],
        body,
    )
    add_check(
        checks,
        "任务契约清晰度",
        "定义输入输出契约",
        "OK" if has_input_output else "WARN",
        4,
        "正文定义输入与输出" if has_input_output else "未发现明确契约",
        "写清输入来源、输出字段和不适用输入。",
        method="#8",
    )
    missing_policy = has_any(
        [r"缺少.*(?:提问|询问|降级)", r"信息不足", r"缺参", r"无法读取"],
        body,
    )
    add_check(
        checks,
        "任务契约清晰度",
        "缺参处理明确",
        "OK" if missing_policy else "WARN",
        2,
        "检测到缺参处理" if missing_policy else "未发现缺参处理",
        "说明何时继续、提问或降级。",
        method="#8/#11",
    )
    scope = has_any([r"不适用", r"禁止", r"边界", r"仅限"], body)
    add_check(
        checks,
        "任务契约清晰度",
        "范围边界明确",
        "OK" if scope else "WARN",
        3,
        "正文含范围边界" if scope else "正文缺少范围边界",
        "明确适用与不适用场景。",
        method="#5/#8",
    )

    has_steps = has_any(
        [r"第\s*\d+\s*步", r"^\s*\d+[.、)]", r"路径\s*[A-D]", r"SOP"],
        body,
    )
    add_check(
        checks,
        "执行流程可操作性",
        "存在可执行步骤",
        "OK" if has_steps else "WARN",
        3,
        "检测到编号步骤或路径" if has_steps else "未检测到明确步骤",
        "将流程拆成有序步骤并写清每步输出。",
        method="#1",
    )
    has_branch = has_any(
        [
            r"\bIF\b",
            r"\bELIF\b",
            r"if-then",
            r"如果.+(?:则|→)",
            r"否则",
            r"触发条件",
        ],
        body,
    )
    add_check(
        checks,
        "执行流程可操作性",
        "专家判断显性化",
        "OK" if has_branch else "WARN",
        3,
        "检测到真实条件分支" if has_branch else "未检测到条件分支",
        "使用 if-then 或触发条件表，不把普通编号当决策树。",
        method="#4",
    )
    fallback = has_any(
        [r"失败", r"fallback", r"仍失败", r"降级", r"无法.*(?:则|→)", r"异常"],
        body,
    )
    add_check(
        checks,
        "执行流程可操作性",
        "失败与降级路径",
        "OK" if fallback else "WARN",
        3,
        "正文包含失败分支" if fallback else "正文只有正向流程",
        "补充触发条件→首选处理→仍失败兜底。",
        method="#11",
    )

    assets_dir = skill_dir / "assets"
    template = assets_dir.is_dir() and any(path.is_file() for path in assets_dir.iterdir())
    output_contract_path = skill_dir / "references" / "output-contract.md"
    output_contract = read_text(output_contract_path) if output_contract_path.is_file() else ""
    format_rules = has_any(
        [r"输出模式", r"输出格式", r"字段", r"JSON", r"HTML", r"Markdown"],
        body + "\n" + output_contract,
    )
    add_check(
        checks,
        "输出稳定性",
        "固定模板与格式",
        "OK" if template and format_rules else "WARN",
        4,
        f"模板={'有' if template else '无'}；格式规则={'有' if format_rules else '无'}",
        "提供模板并说明默认输出档位。",
        method="#3",
    )
    few_shot = has_any([r"优化前", r"优化后", r"示例", r"范例"], examples)
    add_check(
        checks,
        "输出稳定性",
        "存在操作示例",
        "OK" if few_shot else "WARN",
        2,
        "examples.md 含示例" if few_shot else "缺少可复用示例",
        "补一个完整输入→诊断→计划示例。",
        method="#2",
    )
    blacklist = has_any([r"禁止事项", r"不要做", r"反例", r"❌"], body)
    add_check(
        checks,
        "输出稳定性",
        "包含反例或禁止事项",
        "OK" if blacklist else "WARN",
        2,
        "正文含禁止事项" if blacklist else "正文缺少反例",
        "列出会导致优化失败的行为。",
        method="#4",
    )
    quality_gate = has_any([r"验收", r"验证", r"回归", r"通过率"], body)
    add_check(
        checks,
        "输出稳定性",
        "输出后有验收",
        "OK" if quality_gate else "WARN",
        2,
        "正文含验收要求" if quality_gate else "缺少验收要求",
        "要求用固定测试验证结果。",
        method="#12/#14",
    )

    failure_matrix = has_any(
        [r"触发条件.+首选处理.+仍失败", r"失败模式", r"fallback"],
        body,
    )
    add_check(
        checks,
        "运行稳定性与故障恢复",
        "显式失败矩阵",
        "OK" if failure_matrix else "WARN",
        4,
        "检测到失败矩阵" if failure_matrix else "未检测到三段式失败矩阵",
        "覆盖脚本、权限、目录、JSON 和回归失败。",
        method="#11",
    )
    checkpoint = has_any([r"🔴\s*CHECKPOINT", r"🛑\s*STOP"], body)
    add_check(
        checks,
        "运行稳定性与故障恢复",
        "修改前显式检查点",
        "OK" if checkpoint else "WARN",
        3,
        "检测到 CHECKPOINT/STOP" if checkpoint else "仅有普通确认措辞",
        "在修改前增加视觉检查点。",
        method="#16",
    )
    recovery = has_any([r"备份", r"回滚", r"恢复", r"只读", r"原文件"], body)
    add_check(
        checks,
        "运行稳定性与故障恢复",
        "恢复路径明确",
        "OK" if recovery else "WARN",
        3,
        "正文含恢复规则" if recovery else "缺少恢复规则",
        "说明改动失败如何恢复。",
        method="#16",
    )

    scripts = sorted((skill_dir / "scripts").glob("*.py")) if (skill_dir / "scripts").is_dir() else []
    add_check(
        checks,
        "工具化与确定性",
        "确定性检查脚本化",
        "OK" if scripts else "MANUAL",
        3,
        f"{len(scripts)} 个 Python 脚本" if scripts else "无脚本，需判断是否必要",
        "把字符统计、JSON 和回归断言放入脚本。",
        method="#10",
    )
    documented = sum(
        1
        for path in scripts
        if "argparse" in read_text(path) or "用法" in read_text(path) or "usage" in read_text(path).casefold()
    )
    add_check(
        checks,
        "工具化与确定性",
        "脚本提供 CLI",
        "OK" if scripts and documented == len(scripts) else "WARN",
        2,
        f"{documented}/{len(scripts)} 个脚本含 CLI/用法",
        "为每个可执行脚本提供 argparse 或明确用法。",
        method="#11",
    )
    robust = sum(
        1
        for path in scripts
        if "try:" in read_text(path)
        and ("encoding=" in read_text(path) or "errors=" in read_text(path))
    )
    add_check(
        checks,
        "工具化与确定性",
        "脚本处理常见异常",
        "OK" if scripts and robust >= max(1, len(scripts) - 1) else "WARN",
        3,
        f"{robust}/{len(scripts)} 个脚本含异常与编码处理",
        "处理编码、路径、参数和子进程失败。",
        method="#11",
    )

    eval_points = {
        "MISSING": 0,
        "SPEC_ONLY": 1,
        "EXECUTABLE": 3,
        "VERIFIED": 4,
    }[str(evaluation["state"])]
    eval_status = "OK" if evaluation["state"] == "VERIFIED" else "WARN"
    eval_recommendation = {
        "MISSING": "建立 Golden Set 规格、fixture 与机器断言 runner。",
        "SPEC_ONLY": "把书面案例落成 fixture，并增加机器断言 runner。",
        "EXECUTABLE": (
            "先检查目标 runner 并取得确认，再用 "
            "--verify-eval --allow-target-code 运行本轮验证。"
        ),
        "VERIFIED": "保持 fixture 与实现同步，新增失败案例时先复现再修复。",
    }[str(evaluation["state"])]
    add_check(
        checks,
        "评测与回归能力",
        "Golden Set 执行状态",
        eval_status,
        4,
        f"{evaluation['state']}；fixtures={evaluation['fixtureCount']}",
        eval_recommendation,
        points=eval_points,
        method="#12/#14",
    )
    add_check(
        checks,
        "评测与回归能力",
        "存在机器断言 runner",
        "OK" if evaluation["runner"] else "WARN",
        3,
        evaluation["runner"] or "未找到 scripts/run_eval.py",
        "runner 必须输出通过率，失败返回非零退出码。",
        method="#12",
    )
    enough_cases = int(evaluation["fixtureCount"]) >= 5
    add_check(
        checks,
        "评测与回归能力",
        "真实案例覆盖",
        "OK" if enough_cases else "WARN",
        3,
        f"{evaluation['fixtureCount']} 个可执行案例",
        "至少覆盖健康、坏 frontmatter、安全红线、输出缺失、触发冲突。",
        method="#12",
    )


def add_iteration_security_maintainability_checks(
    checks: list[dict[str, Any]],
    blockers: list[str],
    skill_dir: Path,
    parsed: dict[str, Any],
) -> None:
    body = str(parsed.get("body") or "")
    name = str(parsed.get("name") or "")
    patch = skill_dir / "SKILL.patch.md"
    has_version = has_any([r"v\d+\.\d+", r"版本", r"回滚"], body + ("\n" + read_text(patch) if patch.is_file() else ""))
    add_check(
        checks,
        "沉淀与演进",
        "版本与变更记录",
        "OK" if patch.is_file() and has_version else "WARN",
        3,
        f"patch={'有' if patch.is_file() else '无'}；版本记录={'有' if has_version else '无'}",
        "记录版本、变更原因与回滚方式。",
        method="#15/#16",
    )
    feedback = has_any([r"失败案例", r"回填", r"沉淀", r"反馈"], body)
    add_check(
        checks,
        "沉淀与演进",
        "失败案例回填机制",
        "OK" if feedback else "WARN",
        2,
        "正文含回填规则" if feedback else "缺少回填规则",
        "把漏报和误报加入可执行 fixture。",
        method="#15/#17",
    )

    dangerous_patterns = [
        r"直接.*(?:覆盖|删除|发送|发布|上传|修改)",
        r"(?:覆盖|删除|发送|发布|上传).*原文件",
        r"无需确认",
        r"不需要确认",
        r"不经确认",
    ]
    dangerous = has_any(dangerous_patterns, body)
    approval_text = re.sub(r"(?:无需|不需要|不必|不经)\s*确认", "", body)
    approval = has_any([r"用户.*确认", r"明确确认", r"二次确认", r"CHECKPOINT", r"STOP"], approval_text)
    recovery = has_any([r"备份", r"回滚", r"恢复", r"原文件"], body)
    safe_write = not dangerous or (approval and recovery)
    add_check(
        checks,
        "安全与边界",
        "不可逆动作有确认与恢复",
        "OK" if safe_write else "FAIL",
        4,
        (
            "未发现无保护不可逆动作"
            if safe_write
            else "检测到覆盖/删除等动作，但缺少有效确认或恢复"
        ),
        "默认只读；修改前确认并建立可回滚点。",
        blocker=not safe_write,
        method="#11/#16",
    )
    if not safe_write:
        blockers.append("涉及不可逆动作但缺少确认或恢复边界")

    least_privilege = has_any(
        [r"只读", r"最小权限", r"不得.*(?:密钥|token)", r"不输出.*(?:密钥|token)", r"脱敏"],
        body,
    )
    add_check(
        checks,
        "安全与边界",
        "最小权限与敏感信息",
        "OK" if least_privilege else "WARN",
        2,
        "正文含最小权限规则" if least_privilege else "缺少最小权限说明",
        "只读取必要文件，不输出密钥、Token 或敏感数据。",
        method="#11/#19",
    )
    refusal = has_any([r"禁止", r"拒绝", r"不得", r"停止"], body)
    add_check(
        checks,
        "安全与边界",
        "高风险先问或拒绝",
        "OK" if refusal else "WARN",
        2,
        "正文含拒绝边界" if refusal else "缺少高风险拒绝规则",
        "明确哪些高风险操作必须停止。",
        method="#5/#11",
    )

    kebab = bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name))
    add_check(
        checks,
        "可维护性",
        "名称符合 kebab-case",
        "OK" if kebab else "WARN",
        1,
        f"name={name}",
        "仅使用小写字母、数字和连字符。",
        method="#18",
    )
    standard_dirs = sum(
        int((skill_dir / directory).is_dir())
        for directory in ("references", "assets", "scripts", "agents")
    )
    add_check(
        checks,
        "可维护性",
        "资源目录规范",
        "OK" if standard_dirs >= 3 else "WARN",
        1,
        f"{standard_dirs}/4 个标准目录",
        "把运行资源放入标准目录。",
        method="#1",
    )
    internal_refs = referenced_resource_paths(body)
    add_check(
        checks,
        "可维护性",
        "内部引用可追踪",
        "OK" if internal_refs else "WARN",
        1,
        f"{len(internal_refs)} 个直接资源引用",
        "从 SKILL.md 直接链接必要资源。",
        method="#1",
    )
    standalone = has_any(
        [r"不依赖 Darwin", r"不依赖.*其他 Skill", r"完全独立", r"独立于"],
        body,
    )
    add_check(
        checks,
        "可维护性",
        "独立运行边界明确",
        "OK" if standalone else "WARN",
        1,
        "正文声明独立运行" if standalone else "未声明外部 Skill 依赖边界",
        "明确核心能力不依赖其他 Skill。",
        method="#19",
    )


def finalize_report(
    skill_dir: Path,
    parsed: dict[str, Any],
    checks: list[dict[str, Any]],
    blockers: list[str],
    evaluation: dict[str, Any],
    trigger_audit: dict[str, Any],
) -> dict[str, Any]:
    dimensions: list[dict[str, Any]] = []
    weighted_total = 0.0
    weighted_max = 0.0
    weighted_coverage = 0.0
    total_dimension_weight = sum(DIMENSIONS.values())
    counts = {"OK": 0, "WARN": 0, "FAIL": 0, "MANUAL": 0, "N/A": 0}
    for check in checks:
        counts[check["status"]] += 1

    for dimension, weight in DIMENSIONS.items():
        selected = [check for check in checks if check["dimension"] == dimension]
        scored = [check for check in selected if check["scored"]]
        points = sum(float(check["points"]) for check in scored)
        maximum = sum(float(check["maxPoints"]) for check in scored)
        full_maximum = sum(float(check["maxPoints"]) for check in selected)
        coverage = round(maximum / full_maximum * 100) if full_maximum else 0
        score = round(points / maximum * 100) if maximum else None
        weighted_score = round((score or 0) / 100 * weight, 2) if score is not None else None
        if score is not None:
            weighted_total += float(weighted_score)
            weighted_max += weight
        weighted_coverage += coverage / 100 * weight
        dimensions.append(
            {
                "name": dimension,
                "weight": weight,
                "score": score,
                "weightedScore": weighted_score,
                "scoreCoverage": coverage,
                "status": (
                    "阻塞"
                    if any(item["status"] == "FAIL" for item in selected)
                    else "优秀"
                    if score is not None and score >= 90
                    else "健康"
                    if score is not None and score >= 80
                    else "需优化"
                ),
                "issues": sum(
                    1
                    for item in selected
                    if item["status"] in {"WARN", "FAIL", "MANUAL"}
                ),
            }
        )

    total_score = round(weighted_total / weighted_max * 100) if weighted_max else 0
    score_coverage = (
        round(weighted_coverage / total_dimension_weight * 100)
        if total_dimension_weight
        else 0
    )
    normalized_blockers = sorted(set(blockers))
    if evaluation["state"] in {"MISSING", "SPEC_ONLY"}:
        confidence = "LOW"
    elif counts["MANUAL"] > 2:
        confidence = "LOW"
    elif counts["N/A"] or counts["MANUAL"] or evaluation["state"] == "EXECUTABLE":
        confidence = "PARTIAL"
    else:
        confidence = "FULL"

    issues = sorted(
        [
            check
            for check in checks
            if check["status"] in {"FAIL", "WARN", "MANUAL"}
        ],
        key=lambda item: (
            STATUS_PRIORITY[item["status"]],
            -float(item["maxPoints"] - item["points"]),
        ),
    )
    top_fixes = [
        {
            "priority": "P0" if item["status"] == "FAIL" else "P1",
            "dimension": item["dimension"],
            "issue": item["item"],
            "evidence": item["evidence"],
            "action": item["recommendation"],
            "method": item["method"],
        }
        for item in issues[:5]
    ]
    optimization_plan = [
        {
            "order": index,
            "phase": fix["priority"],
            "target": fix["dimension"],
            "action": fix["action"],
            "verification": f"重跑 health_check.py 并验证「{fix['issue']}」状态。",
            "status": "待用户确认",
        }
        for index, fix in enumerate(top_fixes, start=1)
    ]

    return {
        "skillName": parsed.get("name") or skill_dir.name,
        "skillDir": os.fspath(skill_dir),
        "totalScore": total_score,
        "staticScore": total_score,
        "scoreScope": "applicable-static-checks",
        "scoreCoverage": score_coverage,
        "grade": (
            "BLOCKED"
            if normalized_blockers
            else "A"
            if total_score >= 90
            else "B"
            if total_score >= 80
            else "C"
            if total_score >= 70
            else "D"
        ),
        "blocked": bool(normalized_blockers),
        "blockers": normalized_blockers,
        "confidence": confidence,
        "counts": counts,
        "dimensions": dimensions,
        "checks": checks,
        "topFixes": top_fixes,
        "optimizationPlan": optimization_plan,
        "evaluation": evaluation,
        "triggerAudit": trigger_audit,
    }


def build_missing_report(skill_dir: Path) -> dict[str, Any]:
    return {
        "skillName": skill_dir.name,
        "skillDir": os.fspath(skill_dir),
        "totalScore": 0,
        "staticScore": 0,
        "scoreScope": "applicable-static-checks",
        "scoreCoverage": 0,
        "grade": "BLOCKED",
        "blocked": True,
        "blockers": ["缺少 SKILL.md"],
        "confidence": "LOW",
        "counts": {"OK": 0, "WARN": 0, "FAIL": 1, "MANUAL": 0, "N/A": 0},
        "dimensions": [],
        "checks": [],
        "topFixes": [
            {
                "priority": "P0",
                "dimension": "结构与上下文健康",
                "issue": "缺少 SKILL.md",
                "evidence": os.fspath(skill_dir / "SKILL.md"),
                "action": "创建包含 name 与 description 的 SKILL.md。",
                "method": "#1",
            }
        ],
        "optimizationPlan": [],
        "evaluation": {
            "state": "MISSING",
            "verified": False,
            "fixtureCount": 0,
            "passRate": None,
            "reportedPassRate": None,
        },
        "triggerAudit": {
            "crossSkillStatus": "N/A",
            "reason": "目标 Skill 缺失",
            "overlaps": [],
        },
    }


def build_report(
    skill_dir: str | Path,
    *,
    skills_root: str | None = None,
    verify_eval: bool = False,
    allow_target_code: bool = False,
) -> dict[str, Any]:
    root = Path(skill_dir).resolve()
    skill_path = root / "SKILL.md"
    if not skill_path.is_file():
        return build_missing_report(root)

    parsed = parse_frontmatter(read_text(skill_path))
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []
    trigger_audit: dict[str, Any] = {
        "crossSkillStatus": "N/A",
        "reason": "",
        "overlaps": [],
    }
    evaluation = evaluation_state(root, verify_eval, allow_target_code)

    add_structure_checks(checks, blockers, root, parsed)
    add_trigger_checks(checks, root, parsed, skills_root, trigger_audit)
    add_behavior_checks(checks, root, parsed, evaluation)
    add_iteration_security_maintainability_checks(checks, blockers, root, parsed)
    return finalize_report(root, parsed, checks, blockers, evaluation, trigger_audit)


def render_text(report: dict[str, Any], detail: str) -> None:
    print("=" * 72)
    print(f"Skill 体检：{report['skillName']}")
    print("=" * 72)
    print(
        f"适用项静态分 {report['staticScore']}/100 | 证据覆盖 {report['scoreCoverage']}% | "
        f"等级 {report['grade']} | 置信度 {report['confidence']} | "
        f"回归 {report['evaluation']['state']}"
    )
    print(
        f"OK {report['counts']['OK']} / WARN {report['counts']['WARN']} / "
        f"FAIL {report['counts']['FAIL']} / MANUAL {report['counts']['MANUAL']} / "
        f"N/A {report['counts']['N/A']}"
    )
    if report["blockers"]:
        print("\n红线：")
        for blocker in report["blockers"]:
            print(f"- {blocker}")

    print("\n维度：")
    for dimension in report["dimensions"]:
        print(
            f"- {dimension['name']}: {dimension['score']}/100 "
            f"(覆盖 {dimension['scoreCoverage']}%, {dimension['status']}, "
            f"问题 {dimension['issues']})"
        )

    print("\nTop 修复：")
    if not report["topFixes"]:
        print("- 无自动修复项；仍需结合真实任务人工复核。")
    for fix in report["topFixes"]:
        print(
            f"- [{fix['priority']}] {fix['dimension']} / {fix['issue']}："
            f"{fix['action']}"
        )

    print("\n系统化待确认执行计划：")
    if not report["optimizationPlan"]:
        print("- 当前自动检查无待修项；真实任务表现仍需人工对照验证。")
    for item in report["optimizationPlan"]:
        print(
            f"- [{item['phase']}] {item['target']}：{item['action']} "
            f"| 验收：{item['verification']} | {item['status']}"
        )

    if detail == "full":
        print("\n全部检查：")
        for check in report["checks"]:
            print(
                f"- {check['status']} [{check['dimension']}] {check['item']}："
                f"{check['evidence']}"
            )

    print("\n🔴 CHECKPOINT · 🛑 STOP")
    print("以上仅为诊断与待确认计划；用户确认前不得修改目标 Skill。")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_dir", help="目标 Skill 目录")
    parser.add_argument("--skills-root", help="可选：环境级跨 Skill 审计根目录")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--detail", choices=("standard", "full"), default="standard")
    parser.add_argument(
        "--verify-eval",
        action="store_true",
        help="请求运行目标目录的 scripts/run_eval.py；还需显式允许目标代码",
    )
    parser.add_argument(
        "--allow-target-code",
        action="store_true",
        help="确认信任目标 runner，并允许在 30 秒超时限制下执行",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(
        args.skill_dir,
        skills_root=args.skills_root,
        verify_eval=args.verify_eval,
        allow_target_code=args.allow_target_code,
    )
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        render_text(report, args.detail)
    return 1 if report["blocked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
