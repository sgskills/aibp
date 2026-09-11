#!/usr/bin/env python3
"""轻量检查 sg-review 的 V1.1 五模块报告结构与关键业务边界。"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path


REQUIRED_SECTIONS = (
    "本期总体评价",
    "用户需求分析",
    "场景分析",
    "人群分析",
    "情绪分析",
    "综合结论与优先行动项",
)

OPPORTUNITY_FIELDS = (
    "机会类型",
    "目标人群",
    "触发场景",
    "未满足结果",
    "机会假设",
    "证据",
    "证据强度与置信度",
    "为什么不只是整改",
    "反证或替代解释",
    "验证动作",
    "主指标与分母",
    "周期与判定",
    "停止条件",
)

QUALIFIERS = (
    "不", "未", "无", "非", "不能", "无法", "不可", "不得", "并非",
    "尚未", "不能证明", "不代表", "避免", "禁止",
)

STRONG_CLAIMS = (
    "市场空白",
    "已被市场验证",
    "市场已验证",
    "必然提升",
    "ROI最高",
    "ROI 最高",
    "核心转化因子",
    "护城河",
    "确定带来新增",
)


@dataclass(frozen=True)
class Violation:
    code: str
    message: str


@dataclass
class Section:
    level: int
    title: str
    body: str = ""


def _clean_inline_markdown(value: str) -> str:
    value = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"[`*_~]+", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _markdown_sections(text: str) -> tuple[list[Section], str]:
    sections: list[Section] = []
    preamble: list[str] = []
    current: Section | None = None
    in_fence = False

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if match:
            if current is not None:
                sections.append(current)
            current = Section(len(match.group(1)), _clean_inline_markdown(match.group(2)))
            continue
        if current is None:
            preamble.append(line)
        else:
            current.body += line + "\n"

    if current is not None:
        sections.append(current)
    visible = "\n".join(preamble + [f"{s.title}\n{s.body}" for s in sections])
    return sections, _clean_visible(visible)


class _HTMLSections(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sections: list[Section] = []
        self.preamble: list[str] = []
        self.current: Section | None = None
        self.heading_level: int | None = None
        self.heading_parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "template", "noscript", "svg", "canvas"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if re.fullmatch(r"h[1-6]", lowered):
            self.heading_level = int(lowered[1])
            self.heading_parts = []

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "template", "noscript", "svg", "canvas"}:
            if self.skip_depth:
                self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if self.heading_level is not None and lowered == f"h{self.heading_level}":
            if self.current is not None:
                self.sections.append(self.current)
            title = _clean_inline_markdown(" ".join(self.heading_parts))
            self.current = Section(self.heading_level, title)
            self.heading_level = None
            self.heading_parts = []

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        value = html.unescape(data)
        if self.heading_level is not None:
            self.heading_parts.append(value)
        elif self.current is None:
            self.preamble.append(value)
        else:
            self.current.body += value + "\n"

    def finish(self) -> tuple[list[Section], str]:
        if self.current is not None:
            self.sections.append(self.current)
            self.current = None
        visible = "\n".join(self.preamble + [f"{s.title}\n{s.body}" for s in self.sections])
        return self.sections, _clean_visible(visible)


def _html_sections(text: str) -> tuple[list[Section], str]:
    parser = _HTMLSections()
    parser.feed(text)
    parser.close()
    return parser.finish()


def _clean_visible(value: str) -> str:
    value = html.unescape(value).replace("\u200b", "").replace("\ufeff", "")
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def parse_report(text: str) -> tuple[list[Section], str]:
    if re.search(r"<(?:html|body|h[1-6]|section|article|p|table)\b", text, re.I):
        return _html_sections(text)
    return _markdown_sections(text)


def _canonical(title: str) -> str | None:
    compact = re.sub(r"[\s：:、·|｜0-9一二三四五六七八九十模块第章节（）()【】\-—_]+", "", title)
    if "综合结论" in compact and ("优先行动" in compact or "行动项" in compact):
        return "综合结论与优先行动项"
    for required in REQUIRED_SECTIONS[:-1]:
        if required in compact:
            return required
    if "隐藏商业机会" in compact or compact.startswith("商业机会"):
        return "隐藏商业机会"
    return None


def _section_by_canonical(sections: list[Section], name: str) -> Section | None:
    return next((item for item in sections if _canonical(item.title) == name), None)


def _section_content(sections: list[Section], index: int) -> str:
    """Return a section body together with all of its nested subsections."""
    root = sections[index]
    parts = [root.body]
    for item in sections[index + 1:]:
        if item.level <= root.level:
            break
        parts.extend((item.title, item.body))
    return _clean_visible("\n".join(parts))


def _has_unqualified_claim(text: str, claim: str) -> bool:
    start = 0
    while True:
        index = text.find(claim, start)
        if index < 0:
            return False
        prefix = text[max(0, index - 18):index]
        if not any(token in prefix for token in QUALIFIERS):
            return True
        start = index + len(claim)


def _has_labeled_field(text: str, field: str) -> bool:
    return bool(re.search(
        rf"(?:^|\n)\s*(?:[-*+]\s*)?(?:\*{{0,2}})?{re.escape(field)}\s*[：:](?:\*{{0,2}})?",
        text,
    ))


def validate_report(text: str, *, mode: str = "complete") -> list[Violation]:
    sections, visible = parse_report(text)
    violations: list[Violation] = []

    if mode not in {"complete", "targeted"}:
        return [Violation("RPT-000", "mode 只能是 complete 或 targeted")]

    if mode == "complete":
        title_ok = any(
            "评价分析报告" in section.title
            and ("【" in section.title and "】" in section.title)
            for section in sections
        )
        if not title_ok:
            violations.append(Violation("RPT-001", "缺少 `# 评价分析报告【产品名称】` 标题"))

        for field in ("统计周期", "评价总量", "数据来源"):
            if field not in visible:
                violations.append(Violation("RPT-002", f"报告头缺少 `{field}`"))

        ordered = [(_canonical(item.title), index) for index, item in enumerate(sections)]
        positions: list[int] = []
        for required in REQUIRED_SECTIONS:
            found = next((index for name, index in ordered if name == required), None)
            if found is None:
                violations.append(Violation("RPT-003", f"缺少模块 `{required}`"))
            else:
                positions.append(found)
                if len(_section_content(sections, found)) < 20:
                    violations.append(Violation("RPT-004", f"模块 `{required}` 只有标题或内容过少"))
        if len(positions) == len(REQUIRED_SECTIONS) and positions != sorted(positions):
            violations.append(Violation("RPT-005", "五模块与综合结论顺序不符合 V1.1"))

        opportunity = _section_by_canonical(sections, "隐藏商业机会")
        if opportunity is None:
            violations.append(Violation("RPT-006", "完整报告必须有可见的 `隐藏商业机会` 小节"))
        else:
            opportunity_text = _clean_visible(f"{opportunity.title}\n{opportunity.body}")
            if re.search(r"(?:暂无|未发现|没有|无)(?:足够证据支持的)?隐藏?商业机会", opportunity_text):
                violations.append(Violation("RPT-007", "隐藏商业机会不能用“暂无/未发现”代替"))
            for field in OPPORTUNITY_FIELDS:
                if not _has_labeled_field(opportunity_text, field):
                    violations.append(Violation("RPT-008", f"隐藏商业机会缺少 `{field}`"))
            evidence_ids = set(re.findall(r"\bR\d{6}\b", opportunity_text))
            if not evidence_ids:
                violations.append(Violation("RPT-009", "隐藏商业机会没有内部评价编号证据"))
            elif len(evidence_ids) == 1:
                for label in ("单点信号", "低置信度", "探索性假设"):
                    if label not in opportunity_text:
                        violations.append(Violation("RPT-010", f"单条机会证据必须标注 `{label}`"))
            if "评价资产" in opportunity_text and not any(
                token in opportunity_text for token in ("低信息", "信息不足", "评价采集", "反馈采集")
            ):
                violations.append(Violation("RPT-011", "评价资产机会必须说明低信息或反馈采集问题"))

        for priority in ("P0", "P1", "P2"):
            if not re.search(rf"(?<![A-Za-z0-9]){priority}(?![A-Za-z0-9])", visible):
                violations.append(Violation("RPT-012", f"优先行动缺少 `{priority}`"))

        if "建议补充的数据项" not in visible:
            violations.append(Violation("RPT-013", "报告末尾缺少 `建议补充的数据项`"))

    else:
        if len(visible) < 50:
            violations.append(Violation("RPT-020", "定向报告内容过少"))
        if not re.search(r"\bR\d{6}\b|数据不足|不可分析", visible):
            violations.append(Violation("RPT-021", "定向报告缺少评价证据或明确降级说明"))

    for claim in STRONG_CLAIMS:
        if _has_unqualified_claim(visible, claim):
            violations.append(Violation("RPT-030", f"存在未经限定的强结论：`{claim}`"))

    return violations


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"报告不是可读取的 UTF-8 文本：{exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查 sg-review V1.1 五模块报告")
    parser.add_argument("--report", required=True, type=Path, help="Markdown 或 HTML 报告")
    parser.add_argument("--mode", choices=("complete", "targeted"), default="complete")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    try:
        text = _read_text(args.report)
        violations = validate_report(text, mode=args.mode)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps({
            "ok": not violations,
            "mode": args.mode,
            "report": str(args.report),
            "violations": [asdict(item) for item in violations],
        }, ensure_ascii=False, indent=2))
    elif violations:
        for item in violations:
            print(f"[{item.code}] {item.message}")
    else:
        print("[PASS] V1.1 五模块、隐藏商业机会与行动结构检查通过")

    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
