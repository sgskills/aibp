"""sg-skill-optimizer 的共享解析与触发审计工具。

用法：由 health_check.py 与 audit_description.py 导入，不直接执行。
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any


ANTI_TRIGGER_HINTS = (
    "不适用",
    "不用于",
    "不适合",
    "不要用",
    "not for",
    "do not use",
)

STOPWORDS = {
    "的",
    "了",
    "和",
    "与",
    "或",
    "在",
    "是",
    "当",
    "把",
    "对",
    "为",
    "用户",
    "一个",
    "这是",
    "可以",
    "进行",
    "以及",
    "能够",
    "帮助",
    "use",
    "uses",
    "using",
    "user",
    "skill",
    "codex",
    "with",
    "from",
    "this",
    "that",
    "not",
    "for",
    "and",
    "the",
}

IGNORED_DISCOVERY_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "fixtures",
    "node_modules",
    "tests",
    "venv",
}


def read_text(path: str | Path) -> str:
    """按常见编码读取文本；最后用替换字符保证诊断不中断。"""
    file_path = Path(path)
    for encoding in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return file_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return file_path.read_text(encoding="utf-8", errors="replace")


def parse_frontmatter(content: str) -> dict[str, Any]:
    """解析 Agent Skill 的核心 frontmatter，并拒绝明显非法的 YAML 标量。"""
    normalized = content.lstrip("\ufeff")
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", normalized, re.DOTALL)
    if not match:
        return {
            "valid": False,
            "frontmatter": "",
            "name": None,
            "description": "",
            "body": normalized,
            "frontmatterErrors": ["缺少合法的 YAML 边界"],
        }

    frontmatter = match.group(1)
    name_match = re.search(r"^name:\s*(.+)$", frontmatter, re.MULTILINE)
    description_header = re.search(
        r"^description:\s*(.*)$", frontmatter, re.MULTILINE
    )
    errors: list[str] = []
    for line_number, line in enumerate(frontmatter.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or line[:1].isspace():
            continue
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_-]*:\s*.*$", line):
            errors.append(f"第 {line_number} 行不是合法键值")

    def parse_scalar(raw: str | None, field: str) -> str:
        if raw is None:
            return ""
        value = re.sub(r"\s+", " ", raw).strip()
        if not value:
            return ""
        if value[0] in "[{&*!":
            errors.append(f"{field} 必须是字符串标量")
            return ""
        if value[0] in "\"'":
            if len(value) < 2 or value[-1] != value[0]:
                errors.append(f"{field} 引号未闭合")
                return ""
            try:
                parsed_value = ast.literal_eval(value)
            except (SyntaxError, ValueError):
                errors.append(f"{field} 引号内容非法")
                return ""
            if not isinstance(parsed_value, str):
                errors.append(f"{field} 必须是字符串")
                return ""
            return parsed_value.strip()
        if value.endswith(("]", "}")):
            errors.append(f"{field} 必须是字符串标量")
            return ""
        return value.strip()

    name = parse_scalar(name_match.group(1) if name_match else None, "name")
    description_raw = description_header.group(1) if description_header else None
    if description_raw is not None and description_raw.strip() in {"|", ">", "|-", ">-", "|+", ">+"}:
        description_lines: list[str] = []
        remainder = frontmatter[description_header.end() :].splitlines()
        for line in remainder:
            if line and not line[:1].isspace():
                break
            if line.strip():
                description_lines.append(line.strip())
        description_raw = " ".join(description_lines)
    description = parse_scalar(description_raw, "description")

    return {
        "valid": not errors,
        "frontmatter": frontmatter,
        "name": name or None,
        "description": description,
        "body": normalized[match.end() :],
        "frontmatterErrors": errors,
    }


def tokenize(text: str) -> set[str]:
    """生成大小写统一的中英触发词集合。"""
    raw_tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,4}", text)
    tokens = {token.casefold() for token in raw_tokens}
    return {token for token in tokens if token not in STOPWORDS and len(token) >= 2}


def first_sentence(text: str) -> str:
    parts = re.split(r"[。.!！?？\n]", text, maxsplit=1)
    return parts[0].strip() if parts else text.strip()


def has_any(patterns: tuple[str, ...] | list[str], text: str) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE | re.MULTILINE) for pattern in patterns)


def find_skill_files(root: str | Path) -> list[Path]:
    root_path = Path(root)
    if not root_path.is_dir():
        return []
    files: list[Path] = []
    seen_file_ids: set[tuple[int, int]] = set()
    for path in root_path.rglob("SKILL.md"):
        if not path.is_file():
            continue
        relative_parts = path.relative_to(root_path).parts[:-1]
        if any(part.casefold() in IGNORED_DISCOVERY_DIRS for part in relative_parts):
            continue
        stat = path.stat()
        file_id = (stat.st_dev, stat.st_ino)
        if file_id in seen_file_ids:
            continue
        seen_file_ids.add(file_id)
        files.append(path)
    return sorted(files)


def detect_trigger_overlaps(
    skill_dir: str | Path,
    skill_name: str,
    description: str,
    skills_root: str | Path,
) -> list[dict[str, Any]]:
    """仅报告同时满足共享词数量与重叠比例阈值的候选冲突。"""
    target_dir = Path(skill_dir).resolve()
    target_tokens = tokenize(description)
    if len(target_tokens) < 3:
        return []

    overlaps: list[dict[str, Any]] = []
    for skill_path in find_skill_files(skills_root):
        other_dir = skill_path.parent.resolve()
        if other_dir == target_dir:
            continue

        parsed = parse_frontmatter(read_text(skill_path))
        other_description = str(parsed.get("description") or "")
        if parsed.get("name") == skill_name and other_description == description:
            continue
        other_tokens = tokenize(other_description)
        shared = sorted(target_tokens & other_tokens)
        denominator = max(1, min(len(target_tokens), len(other_tokens)))
        overlap_ratio = len(shared) / denominator
        if len(shared) >= 4 and overlap_ratio >= 0.35:
            overlaps.append(
                {
                    "skill": parsed.get("name") or other_dir.name,
                    "sharedTokens": shared[:12],
                    "count": len(shared),
                    "ratio": round(overlap_ratio, 3),
                    "path": os.fspath(skill_path),
                }
            )

    return overlaps


def referenced_resource_paths(body: str) -> list[str]:
    """抽取正文直接引用的标准资源路径。"""
    patterns = (
        r"`((?:references|scripts|assets|agents|tests)/[^`]+?)`",
        r"\((?:\.?/)?((?:references|scripts|assets|agents|tests)/[^)\s]+?)\)",
    )
    found: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, body):
            clean = match.strip().replace("\\", "/")
            if clean not in found:
                found.append(clean)
    return found
