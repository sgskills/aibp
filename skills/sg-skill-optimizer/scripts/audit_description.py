#!/usr/bin/env python3
"""扫描一组 Skill 的 description 长度、前置度、反触发与候选冲突。

用法：
  python audit_description.py <skills根目录>
  python audit_description.py <skills根目录> --format json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from common import (
    ANTI_TRIGGER_HINTS,
    detect_trigger_overlaps,
    find_skill_files,
    first_sentence,
    parse_frontmatter,
    read_text,
)


try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def audit(root: Path) -> dict[str, Any]:
    skill_files = find_skill_files(root)
    rows: list[dict[str, Any]] = []
    total_chars = 0
    for skill_path in skill_files:
        parsed = parse_frontmatter(read_text(skill_path))
        description = str(parsed.get("description") or "")
        total_chars += len(description)
        issues: list[str] = []
        if not parsed["valid"]:
            issues.append("frontmatter 非法")
        if not description:
            issues.append("缺少 description")
        if len(description) > 1024:
            issues.append("description 超过 1024 字符")
        if len(first_sentence(description)) > 140:
            issues.append("首句过长，核心触发词可能未前置")
        if description and not any(
            hint in description.casefold() for hint in ANTI_TRIGGER_HINTS
        ):
            issues.append("缺少反触发边界")
        rows.append(
            {
                "name": parsed.get("name") or skill_path.parent.name,
                "path": str(skill_path),
                "descriptionLength": len(description),
                "issues": issues,
                "description": description,
            }
        )

    overlap_pairs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        skill_dir = Path(row["path"]).parent
        for overlap in detect_trigger_overlaps(
            skill_dir,
            str(row["name"]),
            str(row["description"]),
            root,
        ):
            pair = tuple(sorted((str(row["name"]), str(overlap["skill"]))))
            if pair in seen:
                continue
            seen.add(pair)
            overlap_pairs.append(
                {
                    "skills": list(pair),
                    "sharedTokens": overlap["sharedTokens"],
                    "count": overlap["count"],
                    "ratio": overlap["ratio"],
                }
            )

    return {
        "root": str(root),
        "skillCount": len(rows),
        "totalDescriptionCharacters": total_chars,
        "budget": 8000,
        "budgetExceeded": total_chars > 8000,
        "skills": rows,
        "overlaps": overlap_pairs,
    }


def render_text(report: dict[str, Any]) -> None:
    print("=" * 68)
    print("Skill Description 审计")
    print("=" * 68)
    print(
        f"Skill {report['skillCount']} 个 | description "
        f"{report['totalDescriptionCharacters']}/{report['budget']} 字符"
    )
    for row in report["skills"]:
        marker = "OK" if not row["issues"] else "WARN"
        print(f"- {marker} {row['name']} ({row['descriptionLength']} 字符)")
        for issue in row["issues"]:
            print(f"  - {issue}")
    if report["overlaps"]:
        print("\n候选触发冲突（需要人工确认语义）：")
        for overlap in report["overlaps"]:
            print(
                f"- {' × '.join(overlap['skills'])}: "
                f"{overlap['count']} 词 / {overlap['ratio']:.0%}"
            )
    else:
        print("\n未发现达到数量与比例双阈值的候选冲突。")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skills_root")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.skills_root).resolve()
    if not root.is_dir():
        print(f"目录不存在：{root}", file=sys.stderr)
        return 2
    report = audit(root)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        render_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
