#!/usr/bin/env python3
"""为 sg-review 生成可复核的评价审计与统计底稿。仅使用 Python 标准库。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import unquote, urlsplit, urlunsplit


class ReviewInputError(ValueError):
    """输入无法在不猜测的前提下规范化。"""


def _strict_json_loads(value: str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ReviewInputError("JSON 对象包含重复字段，无法确定唯一输入含义")
            result[key] = item
        return result
    return json.loads(value, object_pairs_hook=reject_duplicates)


@dataclass(frozen=True)
class AnalysisConfig:
    positive_min: float = 4.0
    negative_max: float = 2.0
    small_sample_threshold: int = 10
    low_info_min_chars: int = 4
    sku_imbalance_threshold: float = 0.8

    def validate(self) -> None:
        if not 1 <= self.negative_max < self.positive_min <= 5:
            raise ReviewInputError("评分阈值必须满足 1 <= negative_max < positive_min <= 5")
        if self.small_sample_threshold < 1:
            raise ReviewInputError("small_sample_threshold 必须大于 0")
        if self.low_info_min_chars < 1:
            raise ReviewInputError("low_info_min_chars 必须大于 0")
        if not 0 < self.sku_imbalance_threshold <= 1:
            raise ReviewInputError("sku_imbalance_threshold 必须在 (0, 1] 内")


FIELD_ALIASES: dict[str, set[str]] = {
    "review_id": {"reviewid", "id", "评价编号", "评论编号", "序号", "编号"},
    "review_text": {
        "reviewtext", "text", "content", "comment", "评价正文", "评价内容",
        "评论内容", "评价", "评论", "初评内容", "初次评价"
    },
    "follow_up": {"followup", "additionalreview", "appendedreview", "追评", "追加评论", "追加评价"},
    "date": {"date", "reviewdate", "评价时间", "评论时间", "时间", "日期"},
    "rating": {"rating", "stars", "star", "score", "评价星级", "评论星级", "星级", "评分"},
    "sku": {"sku", "skuname", "规格", "商品规格", "购买规格", "型号", "款式"},
    "product": {"product", "productname", "商品", "商品名称", "产品", "产品名称"},
    "platform": {"platform", "平台", "来源平台"},
    "version": {"version", "productversion", "商品版本", "产品版本", "版本"},
    "fulfillment": {"fulfillment", "fulfillmentmethod", "履约", "履约方式", "服务履约"},
    "inclusion_rule": {"inclusionrule", "sampleinclusionrule", "纳入规则", "样本纳入规则"},
    "competitor": {"competitor", "iscompetitor", "竞品", "竞品标记", "是否竞品"},
}


def normalize_key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    return re.sub(r"[\s_\-./\\:：()（）\[\]【】]+", "", text)


ALIAS_TO_FIELD = {
    normalize_key(alias): field
    for field, aliases in FIELD_ALIASES.items()
    for alias in aliases | {field}
}


PRIVACY_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "email",
        re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9_-])"),
        "[邮箱已脱敏]",
    ),
    ("phone", re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)"), "[手机号已脱敏]"),
    ("id_number", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "[证件号已脱敏]"),
    ("wechat", re.compile(r"(?:微信|vx|wechat)\s*[:：]?\s*[A-Za-z0-9_-]{5,}", re.I), "[微信号已脱敏]"),
    (
        "address",
        re.compile(
            r"(?:[\u4e00-\u9fff]{2,}(?:省|自治区|市|区|县)){1,3}"
            r"[\u4e00-\u9fffA-Za-z0-9]{0,24}(?:路|街|道|巷)\d{0,6}号"
            r"(?:\d{0,6}(?:栋|单元|室))?"
        ),
        "[地址已脱敏]",
    ),
)


INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ignore_instructions", re.compile(r"忽略.{0,12}(?:要求|指令|提示)|ignore.{0,12}instructions?", re.I)),
    ("role_override", re.compile(r"你现在是|you are now|system prompt|系统提示词", re.I)),
    ("execute_command", re.compile(r"执行.{0,8}(?:命令|脚本)|run.{0,8}(?:command|script)", re.I)),
    ("open_external", re.compile(r"打开.{0,8}(?:链接|网址)|open.{0,8}(?:link|url)", re.I)),
)

POSITIVE_MARKERS = ("满意", "喜欢", "推荐", "不错", "漂亮", "精致", "舒服", "准确", "结实", "好用", "很快", "值得", "赞")
NEGATIVE_MARKERS = ("失望", "退货", "难用", "不准", "异味", "瑕疵", "破损", "碎了", "坏了", "断了", "漏水", "太慢", "不值", "太贵", "很差")
LOW_INFO_PHRASES = {"好评", "不错", "很好", "满意", "可以", "还行", "ok", "good", "赞", "默认好评"}


def redact_privacy(text: Any) -> tuple[str, Counter[str]]:
    value = unicodedata.normalize("NFKC", str(text or ""))
    counts: Counter[str] = Counter()
    for name, pattern, replacement in PRIVACY_PATTERNS:
        value, count = pattern.subn(replacement, value)
        if count:
            counts[name] += count
    return value.strip(), counts


def sanitize_scalar(
    value: Any,
    max_length: int = 160,
    external_identifiers: Mapping[str, str] | None = None,
) -> str | None:
    raw = unicodedata.normalize("NFKC", str(value or ""))
    raw, _ = _replace_external_identifiers(raw, external_identifiers or {})
    text, _ = redact_privacy(raw)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    return text[:max_length]


def safe_source_url(
    value: Any, external_identifiers: Mapping[str, str] | None = None
) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return "[来源链接格式无效]"
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return "[已记录的非 HTTP 来源]"
    try:
        port = parsed.port
    except ValueError:
        return "[来源链接格式无效]"
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = f"{host}:{port}" if port is not None else host
    decoded_path = unquote(parsed.path)
    decoded_path, external_count = _replace_external_identifiers(
        decoded_path, external_identifiers or {}
    )
    path, path_privacy = redact_privacy(decoded_path)
    if path_privacy or external_count:
        path = "/[路径已脱敏]"
    else:
        path = parsed.path
    return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


def _duplicate_values(items: Iterable[str]) -> list[str]:
    counter = Counter(items)
    return sorted(value for value, count in counter.items() if count > 1)


def _read_delimited(text: str, delimiter: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise ReviewInputError("表格文本缺少表头")
    normalized = [normalize_key(name) for name in reader.fieldnames]
    # 不同原表头可能映射到同一标准字段；这同样属于规范化后的重复表头。
    canonical_headers = [ALIAS_TO_FIELD.get(name, name) for name in normalized]
    duplicates = _duplicate_values(canonical_headers)
    if duplicates:
        raise ReviewInputError(f"规范化后存在重复表头，共 {len(duplicates)} 组")
    rows = [dict(row) for row in reader]
    if any(None in row for row in rows):
        raise ReviewInputError("表格存在超出表头的单元格，不能静默丢弃")
    return rows


def load_input(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls", ".xlsm"}:
        raise ReviewInputError("脚本不原生读取 XLSX；请先用表格工具只读审计并导出 CSV/JSON")
    text = path.read_text(encoding="utf-8-sig")
    if suffix == ".json":
        payload = _strict_json_loads(text)
        return records_and_metadata(payload)
    if suffix in {".csv", ".tsv"}:
        return _read_delimited(text, "\t" if suffix == ".tsv" else ","), {}
    if suffix in {".txt", ".md", ""}:
        nonempty = [line for line in text.splitlines() if line.strip()]
        if nonempty and "\t" in nonempty[0]:
            candidate_headers = {ALIAS_TO_FIELD.get(normalize_key(part)) for part in nonempty[0].split("\t")}
            if "review_text" in candidate_headers:
                return _read_delimited("\n".join(nonempty), "\t"), {}
        records = []
        for line in nonempty:
            cleaned = re.sub(r"^\s*(?:[-*+•]\s+|\d+[.)、]\s*)", "", line).strip()
            if cleaned:
                records.append({"review_text": cleaned})
        return records, {}
    raise ReviewInputError(f"不支持的输入格式: {suffix or '[无扩展名]'}")


def records_and_metadata(payload: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if isinstance(payload, list):
        records = payload
        metadata: dict[str, Any] = {}
    elif isinstance(payload, dict):
        candidate = payload["reviews"] if "reviews" in payload else payload.get("data", [])
        if not isinstance(candidate, list):
            raise ReviewInputError("reviews/data 字段必须是评价数组")
        records = candidate
        metadata = {key: value for key, value in payload.items() if key not in {"reviews", "data"}}
    else:
        raise ReviewInputError("JSON 顶层必须是评价数组或包含 reviews 数组的对象")
    if any(not isinstance(item, dict) for item in records):
        raise ReviewInputError("每条评价必须是 JSON 对象")
    return [dict(item) for item in records], metadata


def _canonicalize_record(raw: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    values: dict[str, list[Any]] = defaultdict(list)
    for key, value in raw.items():
        field = ALIAS_TO_FIELD.get(normalize_key(key))
        if field and value is not None and str(value).strip():
            values[field].append(value)
    conflicts: list[str] = []
    result: dict[str, Any] = {}
    for field, candidates in values.items():
        unique = {unicodedata.normalize("NFKC", str(value)).strip() for value in candidates}
        if len(unique) > 1:
            conflicts.append(field)
            result[field] = None
        else:
            result[field] = candidates[0]
    return result, sorted(conflicts)


def parse_rating(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
    else:
        text = unicodedata.normalize("NFKC", str(value)).strip()
        numeric = re.fullmatch(r"((?:[1-4](?:\.\d+)?|5(?:\.0+)?))\s*(?:星|分|[⭐★])?", text)
        star_only = re.fullmatch(r"[⭐★]{1,5}", text)
        if numeric:
            number = float(numeric.group(1))
        elif star_only:
            number = float(len(text))
        else:
            return None
    return number if 1 <= number <= 5 else None


def parse_date(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = unicodedata.normalize("NFKC", str(value)).strip()
    iso_candidate = text.replace("/", "-").replace(".", "-")
    try:
        return datetime.fromisoformat(iso_candidate).date().isoformat()
    except ValueError:
        pass
    for fmt in ("%Y年%m月%d日", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_bool(value: Any) -> bool | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, bool):
        return value
    text = normalize_key(value)
    if text in {"true", "1", "yes", "y", "是", "竞品"}:
        return True
    if text in {"false", "0", "no", "n", "否", "本品", "自有"}:
        return False
    return None


def _text_key(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", normalized)


def _visible_length(text: str) -> int:
    return len(re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", text))


def _prompt_injection_signals(text: str) -> list[str]:
    return [name for name, pattern in INJECTION_PATTERNS if pattern.search(text)]


def _allocate_review_id(
    serial: int, reserved_external_ids: set[str], used_internal_ids: set[str]
) -> tuple[str, int]:
    """生成与全部外部编号不相交的内部编号，关闭字符串命名空间碰撞。"""
    candidate = f"R{serial:06d}"
    while candidate in reserved_external_ids or candidate in used_internal_ids:
        serial += 1
        candidate = f"R{serial:06d}"
    used_internal_ids.add(candidate)
    return candidate, serial + 1


def _external_review_id_key(raw_id: Any) -> tuple[str | None, str, Counter[str]]:
    """只为审计重复状态短暂规范外部编号；任何原值都不得写入输出。"""
    value = unicodedata.normalize("NFKC", str(raw_id or "")).strip()
    if not value:
        return None, "missing_external", Counter()
    _, privacy = redact_privacy(value)
    if privacy:
        return None, "sensitive_external", privacy
    if len(value) > 256:
        return None, "oversized_external", Counter()
    return value, "external_internalized", Counter()


def _review_text_value(value: Any) -> str:
    """只接受真正的文本字段。

    JSON 对象、数组和数值不是评价正文；将它们字符串化会把结构化数据
    或攻击载荷冒充成用户表达。
    """
    if not isinstance(value, str):
        return ""
    return value


class ExternalIdentifierReplacements(dict[str, str]):
    """一次构建的 Unicode 精确匹配树；替换时不按评价数量反复遍历。"""

    _END = ""

    def __init__(self, replacements: Mapping[str, str]):
        super().__init__(replacements)
        self._trie: dict[str, Any] = {}
        for identifier, replacement in replacements.items():
            node = self._trie
            for character in identifier:
                node = node.setdefault(character, {})
            node[self._END] = replacement

    def replace_in(self, text: str) -> tuple[str, int]:
        value = unicodedata.normalize("NFKC", text)
        if not value or not self._trie:
            return value, 0
        output: list[str] = []
        count = 0
        index = 0
        while index < len(value):
            # ASCII 字母数字/下划线紧邻已知编号时，当前位置只是更长型号的
            # 内部子串；中文自然语流没有空格，不能把相邻汉字误作编号边界。
            if index > 0 and _is_identifier_extension_character(value[index - 1]):
                output.append(value[index])
                index += 1
                continue
            node = self._trie
            cursor = index
            longest_end: int | None = None
            longest_replacement: str | None = None
            while cursor < len(value) and value[cursor] in node:
                node = node[value[cursor]]
                cursor += 1
                if self._END in node and (
                    cursor == len(value)
                    or not _is_identifier_extension_character(value[cursor])
                ):
                    longest_end = cursor
                    longest_replacement = node[self._END]
            if longest_end is None:
                output.append(value[index])
                index += 1
            else:
                output.append(longest_replacement or "[外部编号已脱敏]")
                count += 1
                index = longest_end
        return "".join(output), count


def _is_identifier_extension_character(character: str) -> bool:
    """识别常见的型号连续字符，同时不把无空格中文句误判为长编号。"""
    return character == "_" or character.isdigit() or (
        character.isascii() and character.isalpha()
    )


def _collect_external_identifiers(records: list[dict[str, Any]]) -> ExternalIdentifierReplacements:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in records:
        for key, value in raw.items():
            if (
                ALIAS_TO_FIELD.get(normalize_key(key)) == "review_id"
                and isinstance(value, (str, int))
                and not isinstance(value, bool)
            ):
                identifier = unicodedata.normalize("NFKC", str(value)).strip()
                if len(identifier) >= 5 and identifier not in seen:
                    seen.add(identifier)
                    ordered.append(identifier)
    replacements = {
        identifier: f"[外部编号X{index:06d}]"
        for index, identifier in enumerate(ordered, start=1)
    }
    return ExternalIdentifierReplacements(
        dict(sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True))
    )


def _replace_external_identifiers(
    text: str, replacements: Mapping[str, str]
) -> tuple[str, int]:
    """替换 ASCII、Unicode、混合脚本及带分隔符的完整外部编号。"""
    if not text or not replacements:
        return text, 0
    matcher = (
        replacements
        if isinstance(replacements, ExternalIdentifierReplacements)
        else ExternalIdentifierReplacements(replacements)
    )
    return matcher.replace_in(text)


def _json_safe(value: Any) -> Any:
    """为指纹生成可重现 JSON，不把原值写入产物。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return f"<{type(value).__name__}>:{value}"


def _annotation_basis_sha256(
    records: list[dict[str, Any]], config: AnalysisConfig, metadata: dict[str, Any]
) -> str:
    """绑定原始记录身份、顺序、文本和分析配置；输出只保留摘要。"""
    basis = {
        "contract": "sg-review-annotation-binding-v1",
        "records": _json_safe(records),
        "config": asdict(config),
        "source_metadata": _json_safe(metadata),
    }
    canonical = json.dumps(basis, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _looks_like_normalized_output(records: list[dict[str, Any]]) -> bool:
    return bool(records) and all(
        {"review_id", "analysis_text", "source_row"}.issubset(record)
        for record in records
    )


def normalize_records(
    records: list[dict[str, Any]], config: AnalysisConfig
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    invalid_rows: list[int] = []
    privacy_counts: Counter[str] = Counter()
    privacy_review_ids: set[str] = set()
    injection_signals: list[dict[str, Any]] = []
    field_conflicts: list[dict[str, Any]] = []
    invalid_rating_rows: list[int] = []
    invalid_date_rows: list[int] = []
    non_textual_follow_up_rows: list[int] = []
    external_id_candidates: dict[str, list[str]] = defaultdict(list)
    external_id_status: dict[str, str] = {}
    canonical_records = [_canonicalize_record(raw) for raw in records]
    external_identifiers = _collect_external_identifiers(records)
    reserved_external_ids = {
        unicodedata.normalize("NFKC", str(value)).strip()
        for raw in records
        for key, value in raw.items()
        if ALIAS_TO_FIELD.get(normalize_key(key)) == "review_id"
        and value is not None
        and str(value).strip()
    }
    used_internal_ids: set[str] = set()
    next_serial = 1

    for index, (canonical, conflicts) in enumerate(canonical_records, start=1):
        review_id, next_serial = _allocate_review_id(
            next_serial, reserved_external_ids, used_internal_ids
        )
        external_id_key, external_status, external_privacy = _external_review_id_key(canonical.get("review_id"))
        if conflicts:
            field_conflicts.append({"source_row": index, "fields": conflicts})

        raw_review_text = _review_text_value(canonical.get("review_text"))
        raw_follow_up = _review_text_value(canonical.get("follow_up"))
        raw_review_text = unicodedata.normalize("NFKC", raw_review_text)
        raw_follow_up = unicodedata.normalize("NFKC", raw_follow_up)
        raw_review_text, review_id_redactions = _replace_external_identifiers(
            raw_review_text, external_identifiers
        )
        raw_follow_up, follow_id_redactions = _replace_external_identifiers(
            raw_follow_up, external_identifiers
        )
        review_text, text_privacy = redact_privacy(raw_review_text)
        follow_up, follow_privacy = redact_privacy(raw_follow_up)
        if follow_up and re.fullmatch(r"[\d\s.,;:：，。+\-]+", follow_up):
            # 导出表常用数字占位，不把它冒充自然语言追评；原行号留在审计中。
            non_textual_follow_up_rows.append(index)
            follow_up = ""
        privacy = text_privacy + follow_privacy + external_privacy
        if review_id_redactions or follow_id_redactions:
            privacy["external_identifier"] += review_id_redactions + follow_id_redactions
        privacy_counts.update(privacy)
        if privacy:
            privacy_review_ids.add(review_id)
        if not review_text and not follow_up:
            invalid_rows.append(index)
            continue
        external_id_status[review_id] = external_status
        if external_id_key is not None:
            external_id_candidates[external_id_key].append(review_id)

        analysis_text = review_text
        if follow_up:
            analysis_text = f"{analysis_text} [追评] {follow_up}" if analysis_text else follow_up
        signals = _prompt_injection_signals(analysis_text)
        if signals:
            injection_signals.append({"review_id": review_id, "signals": signals})

        rating_raw = canonical.get("rating")
        rating = parse_rating(rating_raw)
        if rating_raw is not None and str(rating_raw).strip() and rating is None:
            invalid_rating_rows.append(index)
        date_raw = canonical.get("date")
        review_date = parse_date(date_raw)
        if date_raw is not None and str(date_raw).strip() and review_date is None:
            invalid_date_rows.append(index)

        normalized.append(
            {
                "review_id": review_id,
                "review_text": review_text or None,
                "follow_up": follow_up or None,
                "analysis_text": analysis_text,
                "date": review_date,
                "rating": rating,
                "sku": sanitize_scalar(canonical.get("sku"), external_identifiers=external_identifiers),
                "product": sanitize_scalar(canonical.get("product"), external_identifiers=external_identifiers),
                "platform": sanitize_scalar(canonical.get("platform"), external_identifiers=external_identifiers),
                "version": sanitize_scalar(canonical.get("version"), external_identifiers=external_identifiers),
                "fulfillment": sanitize_scalar(canonical.get("fulfillment"), external_identifiers=external_identifiers),
                "inclusion_rule": sanitize_scalar(canonical.get("inclusion_rule"), external_identifiers=external_identifiers),
                "competitor": parse_bool(canonical.get("competitor")),
                "source_row": index,
            }
        )

    ambiguous_internal_ids: set[str] = set()
    ambiguous_alias_count = 0
    reserved_namespace_internal_ids: set[str] = set()
    for external_id, review_ids in external_id_candidates.items():
        if len(review_ids) != 1:
            ambiguous_alias_count += 1
            ambiguous_internal_ids.update(review_ids)
        elif re.fullmatch(r"R\d{6,}", external_id):
            reserved_namespace_internal_ids.update(review_ids)

    generated_id_reasons: Counter[str] = Counter()
    for review_id, status in external_id_status.items():
        if review_id in ambiguous_internal_ids:
            reason = "ambiguous_external"
        elif review_id in reserved_namespace_internal_ids:
            reason = "reserved_namespace_external"
        else:
            reason = status
        generated_id_reasons[reason] += 1

    audit_details = {
        "invalid_text_rows": invalid_rows,
        "generated_review_ids": len(normalized),
        "generated_id_reasons": dict(generated_id_reasons),
        "external_review_ids_internalized": sum(
            count for reason, count in generated_id_reasons.items() if reason != "missing_external"
        ),
        "ambiguous_external_review_id_count": ambiguous_alias_count,
        "field_conflicts": field_conflicts,
        "invalid_rating_rows": invalid_rating_rows,
        "invalid_date_rows": invalid_date_rows,
        "non_textual_follow_up_rows": non_textual_follow_up_rows,
        "non_textual_follow_up_count": len(non_textual_follow_up_rows),
        "privacy_redactions": dict(privacy_counts),
        "privacy_review_ids": sorted(privacy_review_ids),
        "prompt_injection_signals": injection_signals,
    }
    return normalized, audit_details


def _coverage(records: list[dict[str, Any]], field: str) -> dict[str, Any]:
    count = sum(record.get(field) is not None for record in records)
    total = len(records)
    return {"count": count, "denominator": total, "rate": round(count / total, 6) if total else None}


def _mix_summary(records: list[dict[str, Any]], field: str) -> dict[str, Any]:
    counts = Counter(str(record[field]) for record in records if record.get(field) is not None)
    return {
        "mixed": len(counts) > 1,
        "distinct_count": len(counts),
        "values": [{"value": value, "count": count} for value, count in counts.most_common(20)],
    }


def _duplicate_audit(records: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[str]] = defaultdict(list)
    for record in records:
        key = _text_key(record["analysis_text"])
        if key:
            groups[key].append(record["review_id"])
    output = []
    suspected_ids: set[str] = set()
    for key, review_ids in groups.items():
        if len(review_ids) < 2:
            continue
        suspected_ids.update(review_ids)
        output.append(
            {
                "fingerprint": hashlib.sha256(key.encode("utf-8")).hexdigest()[:12],
                "review_ids": review_ids,
                "count": len(review_ids),
                "label": "疑似重复或模板化",
            }
        )
    output.sort(key=lambda item: (-item["count"], item["fingerprint"]))
    return {"group_count": len(output), "suspected_review_count": len(suspected_ids), "groups": output}


def _sentiment_signal(text: str) -> str | None:
    positive = any(marker in text for marker in POSITIVE_MARKERS)
    negative = any(marker in text for marker in NEGATIVE_MARKERS)
    if positive and not negative:
        return "positive"
    if negative and not positive:
        return "negative"
    return None


def score_overview(records: list[dict[str, Any]], config: AnalysisConfig) -> dict[str, Any]:
    rated = [record for record in records if record["rating"] is not None]
    distribution = Counter()
    conflicts: list[str] = []
    for record in rated:
        rating = float(record["rating"])
        bucket = "positive" if rating >= config.positive_min else "negative" if rating <= config.negative_max else "neutral"
        distribution[bucket] += 1
        signal = _sentiment_signal(record["analysis_text"])
        if (bucket == "positive" and signal == "negative") or (bucket == "negative" and signal == "positive"):
            conflicts.append(record["review_id"])
    count = len(rated)
    return {
        "available": bool(rated),
        "thresholds": {"positive_min": config.positive_min, "negative_max": config.negative_max},
        "rated_review_count": count,
        "mean_rating": round(sum(float(record["rating"]) for record in rated) / count, 4) if count else None,
        "distribution": {
            key: {"count": distribution[key], "rate": round(distribution[key] / count, 6) if count else None}
            for key in ("positive", "neutral", "negative")
        },
        "rating_text_conflict_review_ids": conflicts,
        "rating_text_conflict_count": len(conflicts),
        "conflict_method": "仅基于通用正负文本信号的审计提示，不覆盖星级或人工判断",
    }


COMPARISON_SCOPE_CHECKS: tuple[tuple[str, str], ...] = (
    ("product_scope_aligned", "商品口径"),
    ("platform_scope_aligned", "平台口径"),
    ("version_scope_aligned", "版本口径"),
    ("fulfillment_scope_aligned", "履约口径"),
    ("inclusion_rules_aligned", "纳入规则"),
)


def _comparison_basis_sha256(records: list[dict[str, Any]], config: AnalysisConfig) -> str:
    basis = {"records": records, "config": asdict(config)}
    canonical = json.dumps(basis, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _comparison_scope_audit(
    scope: dict[str, Any] | None,
    expected_type: str,
    basis_sha256: str,
) -> tuple[dict[str, Any], list[str]]:
    scope = scope or {}
    audit_confirmed = scope.get("audit_confirmed") is True
    checks = {key: scope.get(key) is True for key, _ in COMPARISON_SCOPE_CHECKS}
    declared_type = scope.get("comparison_type")
    type_matches = declared_type in {expected_type, "both"}
    hash_matches = str(scope.get("basis_sha256") or "").lower() == basis_sha256
    reasons: list[str] = []
    if not audit_confirmed:
        reasons.append("比较口径尚未标记为审计确认")
    reasons.extend(f"{label}未确认一致" for key, label in COMPARISON_SCOPE_CHECKS if not checks[key])
    if not type_matches:
        reasons.append(f"比较口径文件未授权 {expected_type} 比较")
    if not hash_matches:
        reasons.append("比较口径文件与当前规范数据或配置不匹配")
    return {
        "audit_confirmed": audit_confirmed,
        "checks": checks,
        "comparison_type_matches": type_matches,
        "basis_sha256_matches": hash_matches,
        "ready": audit_confirmed and all(checks.values()) and type_matches and hash_matches,
    }, reasons


def _single_scope_field_reasons(
    records: list[dict[str, Any]], field: str, label: str
) -> list[str]:
    values = [record.get(field) for record in records]
    reasons: list[str] = []
    if not records or any(value is None for value in values):
        reasons.append(f"{label}字段覆盖不完整")
    if len({value for value in values if value is not None}) > 1:
        reasons.append(f"{label}存在混杂")
    return reasons


def _group_scope_field_reasons(
    groups: tuple[list[dict[str, Any]], ...], field: str, label: str
) -> list[str]:
    reasons: list[str] = []
    if any(any(record.get(field) is None for record in group) for group in groups):
        reasons.append(f"至少一组的{label}字段覆盖不完整")
    if any(len({record[field] for record in group if record.get(field) is not None}) > 1 for group in groups):
        reasons.append(f"至少一组存在多个{label}")
    return reasons


def _comparison_group_audit(records: list[dict[str, Any]]) -> dict[str, Any]:
    dates = [record["date"] for record in records if record.get("date")]
    return {
        "review_count": len(records),
        "date_coverage": _coverage(records, "date"),
        "date_range": {"start": min(dates), "end": max(dates)} if dates else None,
        "rating_coverage": _coverage(records, "rating"),
        "scope_field_coverage": {
            field: _coverage(records, field)
            for field in ("product", "platform", "version", "fulfillment", "inclusion_rule")
        },
    }


def sku_overview(
    records: list[dict[str, Any]],
    config: AnalysisConfig,
    comparison_scope: dict[str, Any] | None,
    basis_sha256: str,
) -> dict[str, Any]:
    sku_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("sku"):
            sku_groups[str(record["sku"])].append(record)
    counts = Counter({sku: len(group) for sku, group in sku_groups.items()})
    denominator = sum(counts.values())
    items = [
        {
            "sku": sku,
            "count": count,
            "share": round(count / denominator, 6),
            "audit": _comparison_group_audit(sku_groups[sku]),
            "score_overview": score_overview(sku_groups[sku], config),
        }
        for sku, count in counts.most_common()
    ]
    max_share = items[0]["share"] if items else None
    imbalance = bool(len(items) >= 2 and max_share is not None and max_share >= config.sku_imbalance_threshold)
    scope_audit, comparison_reasons = _comparison_scope_audit(
        comparison_scope, "sku", basis_sha256
    )
    if len(items) < 2:
        comparison_reasons.append("少于两个 SKU")
    else:
        if imbalance:
            comparison_reasons.append("SKU 样本严重失衡")
        if min(counts.values()) < 2:
            comparison_reasons.append("至少一个 SKU 只有 1 条评价")
        date_rates = [sum(item.get("date") is not None for item in group) / len(group) for group in sku_groups.values()]
        if max(date_rates) == 0:
            comparison_reasons.append("SKU 均缺少可解析日期，无法核对周期")
        elif min(date_rates) < 1:
            comparison_reasons.append("至少一个 SKU 的日期覆盖不完整")
        else:
            date_ranges = [
                (min(str(item["date"]) for item in group), max(str(item["date"]) for item in group))
                for group in sku_groups.values()
            ]
            if max(start for start, _ in date_ranges) > min(end for _, end in date_ranges):
                comparison_reasons.append("SKU 日期区间无共同重叠")
        rating_rates = [sum(item.get("rating") is not None for item in group) / len(group) for group in sku_groups.values()]
        if max(rating_rates) - min(rating_rates) > 0.2:
            comparison_reasons.append("SKU 星级字段覆盖率差异超过 20 个百分点")
        sku_records = [item for item in records if item.get("sku")]
        for field, label in (
            ("product", "商品"),
            ("platform", "平台"),
            ("version", "版本"),
            ("fulfillment", "履约"),
            ("inclusion_rule", "纳入规则"),
        ):
            comparison_reasons.extend(_single_scope_field_reasons(sku_records, field, label))
    comparison_ready = bool(len(items) >= 2 and not comparison_reasons)
    comparable_metrics = (
        ["mean_rating", "rating_distribution"]
        if len(items) >= 2 and all(item["score_overview"]["available"] for item in items)
        else []
    )
    return {
        "available": bool(items),
        "review_count_with_sku": denominator,
        "distinct_skus": len(items),
        "items": items,
        "imbalance_warning": imbalance,
        "imbalance_threshold": config.sku_imbalance_threshold,
        "comparison_scope": scope_audit,
        "comparison_ready": comparison_ready,
        "outcome_comparison_ready": bool(comparison_ready and comparable_metrics),
        "comparable_metrics": comparable_metrics,
        "comparison_reasons": comparison_reasons,
    }


def trend_overview(records: list[dict[str, Any]]) -> dict[str, Any]:
    dates = [record["date"] for record in records if record.get("date")]
    months = Counter(value[:7] for value in dates)
    return {
        "available": bool(dates),
        "dated_review_count": len(dates),
        "date_range": {"start": min(dates), "end": max(dates)} if dates else None,
        "monthly_counts": [{"month": month, "count": months[month]} for month in sorted(months)],
        "interpretation_gate": "仅在日期覆盖与连续性足够时解释趋势；本表只给确定性计数",
    }


def comparison_readiness(
    records: list[dict[str, Any]],
    config: AnalysisConfig,
    comparison_scope: dict[str, Any] | None,
    basis_sha256: str,
) -> dict[str, Any]:
    base = [record for record in records if record.get("competitor") is False]
    competitor = [record for record in records if record.get("competitor") is True]
    scope_audit, scope_reasons = _comparison_scope_audit(
        comparison_scope, "competitor", basis_sha256
    )
    if not base or not competitor:
        return {
            "available": False,
            "comparable": None,
            "comparison_scope": scope_audit,
            "outcome_comparison_ready": False,
            "comparable_metrics": [],
            "reasons": ["缺少本品组或竞品组"],
        }
    reasons: list[str] = list(scope_reasons)
    if min(len(base), len(competitor)) < 2:
        reasons.append("至少一组只有 1 条评价")
    larger_group_share = max(len(base), len(competitor)) / (len(base) + len(competitor))
    if larger_group_share >= config.sku_imbalance_threshold:
        reasons.append("本品与竞品样本严重失衡")

    def field_rate(group: list[dict[str, Any]], field: str) -> float:
        return sum(item.get(field) is not None for item in group) / len(group)

    if abs(field_rate(base, "rating") - field_rate(competitor, "rating")) > 0.2:
        reasons.append("两组星级字段覆盖率差异超过 20 个百分点")
    base_date_rate = field_rate(base, "date")
    comp_date_rate = field_rate(competitor, "date")
    base_dates = [item["date"] for item in base if item.get("date")]
    comp_dates = [item["date"] for item in competitor if item.get("date")]
    if not base_dates and not comp_dates:
        reasons.append("两组均缺少可解析日期，无法核对周期")
    elif bool(base_dates) != bool(comp_dates):
        reasons.append("只有一组具有可解析日期")
    else:
        if base_date_rate < 1 or comp_date_rate < 1:
            reasons.append("至少一组日期覆盖不完整")
        if max(base_dates) < min(comp_dates) or max(comp_dates) < min(base_dates):
            reasons.append("两组日期区间不重叠")
    for field, label in (("product", "商品"), ("version", "版本")):
        reasons.extend(_group_scope_field_reasons((base, competitor), field, label))
    combined = base + competitor
    for field, label in (
        ("platform", "平台"),
        ("fulfillment", "履约"),
        ("inclusion_rule", "纳入规则"),
    ):
        reasons.extend(_single_scope_field_reasons(combined, field, label))
    comparable = not reasons
    base_score = score_overview(base, config)
    competitor_score = score_overview(competitor, config)
    comparable_metrics = (
        ["mean_rating", "rating_distribution"]
        if base_score["available"] and competitor_score["available"]
        else []
    )
    return {
        "available": True,
        "comparable": comparable,
        "outcome_comparison_ready": bool(comparable and comparable_metrics),
        "comparable_metrics": comparable_metrics,
        "comparison_scope": scope_audit,
        "groups": {"base": len(base), "competitor": len(competitor)},
        "group_audits": {
            "base": {**_comparison_group_audit(base), "score_overview": base_score},
            "competitor": {
                **_comparison_group_audit(competitor),
                "score_overview": competitor_score,
            },
        },
        "larger_group_share": round(larger_group_share, 6),
        "imbalance_threshold": config.sku_imbalance_threshold,
        "reasons": reasons,
        "gate": "未通过时仅分别审计，不做排名式优劣结论",
    }


def _quote_is_locatable(quote: str, text: str) -> bool:
    if quote in text:
        return True
    return re.sub(r"\s+", "", quote) in re.sub(r"\s+", "", text)


def _quote_spans(quote: str, text: str) -> list[tuple[int, int]]:
    """Locate every normalized non-whitespace occurrence for overlap control."""
    compact_quote = re.sub(r"\s+", "", unicodedata.normalize("NFKC", quote))
    compact_text = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))
    if not compact_quote:
        return []
    spans: list[tuple[int, int]] = []
    start = 0
    while True:
        position = compact_text.find(compact_quote, start)
        if position < 0:
            break
        spans.append((position, position + len(compact_quote)))
        start = position + 1
    return spans


def _first_nonoverlapping_span(
    quote: str,
    text: str,
    occupied: list[tuple[int, int]],
) -> tuple[int, int] | None:
    for start, end in _quote_spans(quote, text):
        if all(end <= prior_start or start >= prior_end for prior_start, prior_end in occupied):
            return start, end
    return None


def _payload_sha256(value: Any) -> str:
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _prepare_annotations(
    payload: Any,
    known_review_ids: set[str],
    basis_sha256: str,
) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
    """区分无标注、旧版未绑定标注与可审计的绑定信封。"""
    if payload is None:
        return [], {
            "binding_status": "none",
            "complete": False,
            "reviewed_review_count": 0,
            "unreviewed_review_count": len(known_review_ids),
            "valid_review_count": len(known_review_ids),
            "coverage_scope": "no_reviews_marked_as_reviewed",
        }, False
    if isinstance(payload, list):
        return payload, {
            "binding_status": "legacy_unbound",
            "complete": False,
            "reviewed_review_count": 0,
            "unreviewed_review_count": len(known_review_ids),
            "valid_review_count": len(known_review_ids),
            "coverage_scope": "legacy_annotations_without_dataset_binding",
        }, False
    if not isinstance(payload, dict):
        raise ReviewInputError("标注必须是旧版数组或绑定信封对象")
    if set(payload) == {"annotations"} and isinstance(payload["annotations"], list):
        # 0.1.x 曾公开支持这种包装；保留读取能力，但不冒充数据集绑定。
        return _prepare_annotations(payload["annotations"], known_review_ids, basis_sha256)

    required = {"basis_sha256", "reviewed_review_ids", "annotations"}
    allowed = required | {"producer_id"}
    missing = sorted(required - payload.keys())
    unknown = sorted(payload.keys() - allowed)
    if missing or unknown:
        details = []
        if missing:
            details.append(f"缺少字段: {', '.join(missing)}")
        if unknown:
            details.append(f"包含 {len(unknown)} 个未知字段（字段名不回显）")
        raise ReviewInputError("标注信封结构无效；" + "；".join(details))
    declared_basis = str(payload["basis_sha256"] or "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", declared_basis):
        raise ReviewInputError("标注 basis_sha256 必须是 64 位十六进制摘要")
    if declared_basis != basis_sha256:
        raise ReviewInputError("标注信封与当前原始数据、顺序或配置不匹配")
    if "producer_id" in payload and (
        not isinstance(payload["producer_id"], str) or not payload["producer_id"].strip()
    ):
        raise ReviewInputError("producer_id 必须是非空字符串")

    reviewed = payload["reviewed_review_ids"]
    items = payload["annotations"]
    if not isinstance(reviewed, list) or not all(isinstance(item, str) for item in reviewed):
        raise ReviewInputError("reviewed_review_ids 必须是内部评价编号数组")
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise ReviewInputError("annotations 必须是标注对象数组")
    allowed_annotation_fields = {
        "review_id", "theme_mentions", "scene_clues", "purchaser_clues", "user_clues",
    }
    for item in items:
        if set(item) - allowed_annotation_fields:
            raise ReviewInputError("annotations[*] 包含未声明字段；请按标注契约修正字段名")
        mentions = item.get("theme_mentions", [])
        if isinstance(mentions, list):
            for mention in mentions:
                if isinstance(mention, dict) and set(mention) - {"theme", "quote", "sentiment"}:
                    raise ReviewInputError("theme_mentions[*] 包含未声明字段；请按标注契约修正字段名")
        for field in ("scene_clues", "purchaser_clues", "user_clues"):
            clues = item.get(field, [])
            if isinstance(clues, list):
                for clue in clues:
                    if isinstance(clue, dict) and set(clue) - {"label", "quote"}:
                        raise ReviewInputError(f"{field}[*] 包含未声明字段；请按标注契约修正字段名")
    normalized_reviewed = [unicodedata.normalize("NFKC", item).strip() for item in reviewed]
    if len(normalized_reviewed) != len(set(normalized_reviewed)):
        raise ReviewInputError("reviewed_review_ids 存在重复编号")
    if set(normalized_reviewed) - known_review_ids:
        raise ReviewInputError("reviewed_review_ids 包含当前数据中不存在的编号")
    annotated_id_list = [
        unicodedata.normalize("NFKC", str(item.get("review_id") or "")).strip()
        for item in items
    ]
    if any(
        not isinstance(item.get("review_id"), str) or not item.get("review_id", "").strip()
        for item in items
    ):
        raise ReviewInputError("annotations[*].review_id 必须是非空字符串")
    if len(annotated_id_list) != len(set(annotated_id_list)):
        raise ReviewInputError("annotations 中同一内部评价编号只能出现一次")
    annotated_ids = set(annotated_id_list)
    if not annotated_ids.issubset(set(normalized_reviewed)):
        raise ReviewInputError("标注所引用的评价未全部列入 reviewed_review_ids")

    reviewed_count = len(normalized_reviewed)
    complete = set(normalized_reviewed) == known_review_ids
    return items, {
        "binding_status": "bound",
        "complete": complete,
        "reviewed_review_count": reviewed_count,
        "unreviewed_review_count": len(known_review_ids) - reviewed_count,
        "valid_review_count": len(known_review_ids),
        "coverage_scope": "all_valid_reviews" if complete else "reviewed_subset_of_valid_reviews",
        "basis_sha256_matches": True,
    }, True


def _aggregate_mentions(
    annotations: list[dict[str, Any]],
    records_by_id: dict[str, dict[str, Any]],
    valid_count: int,
    coverage_is_lower_bound: bool,
    coverage_scope: str,
    external_identifiers: Mapping[str, str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, list[str]]]:
    theme_groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "review_ids": set(), "mentions": 0, "sentiments": Counter(),
            "sentiment_review_ids": defaultdict(set), "quotes": [],
        }
    )
    clue_fields = ("scene_clues", "purchaser_clues", "user_clues")
    clue_groups: dict[str, dict[str, dict[str, Any]]] = {
        field: defaultdict(lambda: {"review_ids": set(), "mentions": 0, "quotes": []})
        for field in clue_fields
    }
    evidence_quotes: dict[str, list[str]] = defaultdict(list)
    rejected: list[dict[str, Any]] = []
    accepted_theme_spans: dict[str, list[tuple[int, int]]] = defaultdict(list)
    accepted_quote_themes: dict[tuple[str, str], str] = {}
    accepted_clue_spans: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)
    total_mentions = 0

    for annotation_index, annotation in enumerate(annotations, start=1):
        if not isinstance(annotation, dict):
            rejected.append({"annotation": annotation_index, "reason": "标注不是对象"})
            continue
        review_id = unicodedata.normalize("NFKC", str(annotation.get("review_id") or "")).strip()
        record = records_by_id.get(review_id)
        if not record:
            # 不回显未知外部编号，避免把订单号、会员号等带入审计产物。
            rejected.append({"annotation": annotation_index, "reason": "内部评价编号不存在"})
            continue
        text = record["analysis_text"]
        mentions = annotation.get("theme_mentions", [])
        if not isinstance(mentions, list):
            rejected.append({"annotation": annotation_index, "review_id": review_id, "reason": "theme_mentions 不是数组"})
            mentions = []
        # Longest sufficient fragments win. This makes nested keyword hits such as
        # “破损 / 有破损 / 有破损的” one semantic mention instead of three counts,
        # regardless of the order in which an annotator emitted them.
        indexed_mentions = list(enumerate(mentions, start=1))
        indexed_mentions.sort(
            key=lambda pair: (
                -_visible_length(str(pair[1].get("quote") or ""))
                if isinstance(pair[1], dict) else 0,
                pair[0],
            )
        )
        for mention_index, mention in indexed_mentions:
            if not isinstance(mention, dict):
                rejected.append({"review_id": review_id, "mention": mention_index, "reason": "主题提及不是对象"})
                continue
            if (
                not isinstance(mention.get("theme"), str)
                or not isinstance(mention.get("quote"), str)
                or ("sentiment" in mention and not isinstance(mention.get("sentiment"), str))
            ):
                rejected.append({
                    "review_id": review_id,
                    "mention": mention_index,
                    "reason": "主题、引文和情绪字段必须是字符串",
                })
                continue
            theme = sanitize_scalar(mention.get("theme"), 80, external_identifiers)
            quote, _ = redact_privacy(mention.get("quote"))
            if len(quote) > 160 or not theme or not quote or not _quote_is_locatable(quote, text):
                rejected.append({"review_id": review_id, "mention": mention_index, "reason": "主题/引文缺失或引文无法定位"})
                continue
            sentiment = normalize_key(mention.get("sentiment") or "unspecified")
            if sentiment not in {"positive", "negative", "neutral", "mixed", "unspecified"}:
                rejected.append({
                    "review_id": review_id,
                    "mention": mention_index,
                    "reason": "主题情绪必须是 positive、negative、neutral、mixed 或 unspecified",
                })
                continue
            compact_quote = re.sub(r"\s+", "", unicodedata.normalize("NFKC", quote))
            prior_theme = accepted_quote_themes.get((review_id, compact_quote))
            if prior_theme is not None and prior_theme != theme:
                rejected.append({
                    "review_id": review_id,
                    "mention": mention_index,
                    "reason": "同一评价的同一引文被多个主题复用；请拆成各自可定位片段",
                })
                continue
            if _visible_length(quote) < 3:
                rejected.append({
                    "review_id": review_id,
                    "mention": mention_index,
                    "reason": "主题引文上下文过短；请引用能独立支撑归类的最小充分片段",
                })
                continue
            accepted_span = _first_nonoverlapping_span(
                quote, text, accepted_theme_spans[review_id]
            )
            if accepted_span is None:
                rejected.append({
                    "review_id": review_id,
                    "mention": mention_index,
                    "reason": "同一评价的主题引文区间重叠；一个原文事件只能计数一次",
                })
                continue
            accepted_theme_spans[review_id].append(accepted_span)
            accepted_quote_themes[(review_id, compact_quote)] = theme
            group = theme_groups[theme]
            group["review_ids"].add(review_id)
            group["mentions"] += 1
            group["sentiments"][sentiment] += 1
            group["sentiment_review_ids"][sentiment].add(review_id)
            group["quotes"].append({
                "review_id": review_id,
                "quote": quote,
                "sentiment": sentiment,
            })
            evidence_quotes[review_id].append(quote)
            total_mentions += 1

        for field in clue_fields:
            clues = annotation.get(field, [])
            if not isinstance(clues, list):
                rejected.append({"review_id": review_id, "field": field, "reason": "线索字段不是数组"})
                continue
            indexed_clues = list(enumerate(clues, start=1))
            indexed_clues.sort(
                key=lambda pair: (
                    -_visible_length(str(pair[1].get("quote") or ""))
                    if isinstance(pair[1], dict) else 0,
                    pair[0],
                )
            )
            for clue_index, clue in indexed_clues:
                if not isinstance(clue, dict):
                    rejected.append({"review_id": review_id, "field": field, "item": clue_index, "reason": "线索不是对象"})
                    continue
                if not isinstance(clue.get("label"), str) or not isinstance(clue.get("quote"), str):
                    rejected.append({
                        "review_id": review_id,
                        "field": field,
                        "item": clue_index,
                        "reason": "线索标签和引文必须是字符串",
                    })
                    continue
                label = sanitize_scalar(clue.get("label"), 80, external_identifiers)
                quote, _ = redact_privacy(clue.get("quote"))
                if len(quote) > 160 or not label or not quote or not _quote_is_locatable(quote, text):
                    rejected.append({"review_id": review_id, "field": field, "item": clue_index, "reason": "标签/引文缺失或引文无法定位"})
                    continue
                if _visible_length(quote) < 3:
                    rejected.append({
                        "review_id": review_id,
                        "field": field,
                        "item": clue_index,
                        "reason": "线索引文上下文过短；请引用能独立支撑归类的最小充分片段",
                    })
                    continue
                accepted_span = _first_nonoverlapping_span(
                    quote, text, accepted_clue_spans[(review_id, field)]
                )
                if accepted_span is None:
                    rejected.append({
                        "review_id": review_id,
                        "field": field,
                        "item": clue_index,
                        "reason": "同一评价同类线索的引文区间重叠；一个原文事件只能计数一次",
                    })
                    continue
                accepted_clue_spans[(review_id, field)].append(accepted_span)
                group = clue_groups[field][label]
                group["review_ids"].add(review_id)
                group["mentions"] += 1
                group["quotes"].append({"review_id": review_id, "quote": quote})
                evidence_quotes[review_id].append(quote)

    theme_items = []
    for theme, group in theme_groups.items():
        review_ids = sorted(group["review_ids"])
        review_count = len(review_ids)
        theme_items.append(
            {
                "theme": theme,
                "review_count": review_count,
                "coverage_denominator": valid_count,
                "review_coverage": round(review_count / valid_count, 6) if valid_count else None,
                "coverage_is_lower_bound": coverage_is_lower_bound,
                "coverage_scope": coverage_scope,
                "mention_count": group["mentions"],
                "mention_denominator": total_mentions,
                "mention_share": round(group["mentions"] / total_mentions, 6) if total_mentions else None,
                "sentiments": dict(group["sentiments"]),
                "sentiment_review_ids": {
                    sentiment: sorted(review_ids_for_sentiment)[:20]
                    for sentiment, review_ids_for_sentiment in group["sentiment_review_ids"].items()
                },
                "evidence_review_ids": review_ids[:20],
                "evidence_review_count": review_count,
                "evidence_quotes": group["quotes"][:5],
                "signal": "multi_review" if review_count >= 2 else "single_point_signal",
            }
        )
    theme_items.sort(key=lambda item: (-item["mention_count"], -item["review_count"], item["theme"]))

    explicit_clues: dict[str, Any] = {}
    for field, groups in clue_groups.items():
        items = []
        for label, group in groups.items():
            review_ids = sorted(group["review_ids"])
            items.append(
                {
                    "label": label,
                    "review_count": len(review_ids),
                    "coverage_denominator": valid_count,
                    "review_coverage": round(len(review_ids) / valid_count, 6) if valid_count else None,
                    "coverage_is_lower_bound": coverage_is_lower_bound,
                    "coverage_scope": coverage_scope,
                    "mention_count": group["mentions"],
                    "evidence_review_ids": review_ids[:20],
                    "evidence_quotes": group["quotes"][:5],
                    "signal": "multi_review" if len(review_ids) >= 2 else "single_point_signal",
                }
            )
        items.sort(key=lambda item: (-item["review_count"], -item["mention_count"], item["label"]))
        explicit_clues[field] = items

    reviewed_with_theme_ids = set().union(
        *(group["review_ids"] for group in theme_groups.values())
    ) if theme_groups else set()
    themes = {
        "available": bool(theme_items),
        "coverage_formula": "提及该主题的不同评价数 / 有效评价数",
        "mention_share_formula": "该主题提及数 / 全部有效主题提及数",
        "coverage_denominator": valid_count,
        "coverage_is_lower_bound": coverage_is_lower_bound,
        "coverage_scope": coverage_scope,
        "mention_denominator": total_mentions,
        "reviewed_with_theme_count": len(reviewed_with_theme_ids),
        "items": theme_items,
        "rejected_annotations": rejected,
        "rejected_annotation_count": len(rejected),
    }
    return themes, explicit_clues, evidence_quotes


def analyze_records(
    records: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
    annotations: Any = None,
    config: AnalysisConfig | None = None,
    comparison_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or AnalysisConfig()
    config.validate()
    metadata = metadata or {}
    if _looks_like_normalized_output(records):
        raise ReviewInputError("不接受脱离原始身份的 normalized_reviews 作为新输入")
    external_identifiers = _collect_external_identifiers(records)
    annotation_basis_sha256 = _annotation_basis_sha256(records, config, metadata)
    normalized, details = normalize_records(records, config)
    valid_count = len(normalized)

    field_coverage = {
        field: _coverage(normalized, field)
        for field in (
            "date", "rating", "sku", "product", "platform", "version",
            "fulfillment", "inclusion_rule", "competitor",
        )
    }
    missing_optional = [field for field, coverage in field_coverage.items() if coverage["count"] == 0]
    duplicate = _duplicate_audit(normalized)
    low_info_ids = [
        record["review_id"]
        for record in normalized
        if _visible_length(record["analysis_text"]) < config.low_info_min_chars
        or _text_key(record["analysis_text"]) in {_text_key(value) for value in LOW_INFO_PHRASES}
    ]

    if valid_count == 0:
        if metadata.get("summary") is not None:
            status = "summary_only_no_raw_text"
        elif metadata.get("source_url"):
            status = "needs_exported_reviews"
        else:
            status = "no_valid_reviews"
    elif valid_count < config.small_sample_threshold:
        status = "small_sample"
    else:
        status = "ready"

    records_by_id = {record["review_id"]: record for record in normalized}
    annotation_list, annotation_audit, annotation_authoritative = _prepare_annotations(
        annotations, set(records_by_id), annotation_basis_sha256
    )
    annotation_audit["annotation_payload_sha256"] = (
        _payload_sha256(annotations)
        if annotation_authoritative and isinstance(annotations, dict)
        else None
    )
    themes, explicit_clues, evidence_quotes = _aggregate_mentions(
        annotation_list,
        records_by_id,
        valid_count,
        not annotation_audit["complete"],
        annotation_audit["coverage_scope"],
        external_identifiers,
    )
    rejected_annotation_count = themes["rejected_annotation_count"]
    annotation_audit["reviewed_with_theme_count"] = themes["reviewed_with_theme_count"]
    annotation_audit["reviewed_without_theme_count"] = max(
        0,
        annotation_audit["reviewed_review_count"] - themes["reviewed_with_theme_count"],
    )
    annotation_audit["all_annotations_valid"] = rejected_annotation_count == 0
    annotation_audit["rejected_annotation_count"] = rejected_annotation_count
    if annotation_authoritative and rejected_annotation_count:
        annotation_audit["complete"] = False
        annotation_audit["coverage_scope"] = "reviewed_scope_with_rejected_annotations"
        themes["coverage_is_lower_bound"] = True
        themes["coverage_scope"] = annotation_audit["coverage_scope"]
        for item in themes["items"]:
            item["coverage_is_lower_bound"] = True
            item["coverage_scope"] = annotation_audit["coverage_scope"]
        for items in explicit_clues.values():
            for item in items:
                item["coverage_is_lower_bound"] = True
                item["coverage_scope"] = annotation_audit["coverage_scope"]
    evidence_index = []
    for review_id in sorted(evidence_quotes):
        record = records_by_id[review_id]
        quotes = list(dict.fromkeys(evidence_quotes[review_id]))
        if not annotation_authoritative:
            # 旧版标注没有数据集绑定；仅保留能在当前数据中唯一定位的引文，
            # 共享短语不进证据索引，也绝不提升为权威主题能力。
            quotes = [
                quote for quote in quotes
                if sum(
                    _quote_is_locatable(quote, candidate["analysis_text"])
                    for candidate in normalized
                ) == 1
            ]
        if not quotes:
            continue
        evidence_index.append(
            {
                "review_id": review_id,
                "quotes": quotes[:5],
                "date": record["date"],
                "rating": record["rating"],
                "sku": record["sku"],
                "group": "competitor" if record["competitor"] is True else "base" if record["competitor"] is False else None,
            }
        )

    comparison_basis_sha256 = _comparison_basis_sha256(normalized, config)
    audit = {
        "input_record_count": len(records),
        "valid_review_count": valid_count,
        "invalid_review_count": len(records) - valid_count,
        "small_sample": bool(valid_count and valid_count < config.small_sample_threshold),
        "small_sample_threshold": config.small_sample_threshold,
        "field_coverage": field_coverage,
        "missing_optional_fields": missing_optional,
        "low_information": {"count": len(low_info_ids), "review_ids": low_info_ids, "label": "低信息"},
        "duplicate_or_template_like": duplicate,
        "product_mix": _mix_summary(normalized, "product"),
        "platform_mix": _mix_summary(normalized, "platform"),
        "comparison_basis_sha256": comparison_basis_sha256,
        "annotation_basis_sha256": annotation_basis_sha256,
        **details,
    }
    score_result = score_overview(normalized, config)
    sku_result = sku_overview(normalized, config, comparison_scope, comparison_basis_sha256)
    trend_result = trend_overview(normalized)
    comparison_result = comparison_readiness(
        normalized, config, comparison_scope, comparison_basis_sha256
    )
    capabilities = {
        "text_analysis": valid_count > 0,
        "score_overview": field_coverage["rating"]["count"] > 0,
        "trend": field_coverage["date"]["count"] > 0,
        "sku_comparison": sku_result["comparison_ready"],
        "evidence_backed_themes": bool(themes["available"] and annotation_authoritative),
    }
    return {
        "schema_version": "1.1",
        "calculation_mode": "script",
        "status": status,
        "source": {
            "source_url": safe_source_url(metadata.get("source_url"), external_identifiers),
            "source_accessible": metadata.get("source_accessible") if isinstance(metadata.get("source_accessible"), bool) else None,
            "summary_present": metadata.get("summary") is not None,
            "link_fetch_attempted": False,
        },
        "config": asdict(config),
        "audit": audit,
        "annotation_audit": annotation_audit,
        "capabilities": capabilities,
        "score_overview": score_result,
        "sku_overview": sku_result,
        "trend": trend_result,
        "comparison": comparison_result,
        "themes": themes,
        "explicit_clues": explicit_clues,
        "evidence_index": evidence_index,
        "normalized_reviews": normalized,
    }


def analyze_payload(
    payload: Any,
    annotations: Any = None,
    config: AnalysisConfig | None = None,
    comparison_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    records, metadata = records_and_metadata(payload)
    return analyze_records(records, metadata, annotations, config, comparison_scope)


def load_annotations(path: Path | None) -> Any:
    if path is None:
        return None
    payload = _strict_json_loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, (list, dict)):
        raise ReviewInputError("annotations 顶层必须是数组或包含 annotations 数组的对象")
    return payload


def load_comparison_scope(path: Path | None) -> dict[str, Any] | None:
    """只从显式传入的审计文件加载门禁，绝不信任评价输入内嵌的同名字段。"""
    if path is None:
        return None
    payload = _strict_json_loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ReviewInputError("比较口径文件必须是 JSON 对象")
    boolean_fields = {"audit_confirmed"} | {key for key, _ in COMPARISON_SCOPE_CHECKS}
    required = boolean_fields | {"comparison_type", "basis_sha256"}
    missing = sorted(required - payload.keys())
    unknown = sorted(payload.keys() - required)
    if missing or unknown:
        details = []
        if missing:
            details.append(f"缺少字段: {', '.join(missing)}")
        if unknown:
            details.append(f"包含 {len(unknown)} 个未知字段（字段名不回显）")
        raise ReviewInputError("比较口径文件结构无效；" + "；".join(details))
    non_boolean = sorted(key for key in boolean_fields if not isinstance(payload[key], bool))
    if non_boolean:
        raise ReviewInputError(f"比较口径字段必须是布尔值: {', '.join(non_boolean)}")
    if payload["comparison_type"] not in {"sku", "competitor", "both"}:
        raise ReviewInputError("comparison_type 必须是 sku、competitor 或 both")
    basis_sha256 = str(payload["basis_sha256"]).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", basis_sha256):
        raise ReviewInputError("basis_sha256 必须是 64 位十六进制摘要")
    normalized = {key: payload[key] for key in boolean_fields}
    normalized["comparison_type"] = payload["comparison_type"]
    normalized["basis_sha256"] = basis_sha256
    return normalized


def assess_task_scope(task: str) -> str:
    """Golden Set 使用的保守路由检查，不替代 Agent 的语义判断。"""
    text = normalize_key(task)
    if any(token in text for token in ("python代码", "代码审查", "找bug", "reviewcode", "codereview")):
        return "out_of_scope"
    if any(token in text for token in ("推广报表", "广告投放报表", "直通车报表", "万相台报表")):
        return "sg-tmads-report"
    if ("渠道" in text and any(token in text for token in ("国家", "市场")) and "品类" in text):
        return "sg-insight"
    if any(token in text for token in ("完整产品开发", "从零开发产品", "产品开发全案")):
        return "sg-product"
    if any(token in text for token in ("评价", "评论", "review", "voc", "差评", "好评")):
        return "sg-review"
    cross_module_hits = sum(token in text for token in ("流量", "转化", "库存", "客服", "利润", "商品"))
    if cross_module_hits >= 2:
        return "sg-mece"
    return "out_of_scope"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成电商评价审计与确定性统计底稿")
    parser.add_argument("--input", type=Path, help="UTF-8 JSON/CSV/TSV/TXT 输入")
    parser.add_argument("--annotations", type=Path, help="可选的类目自适应证据标注 JSON")
    parser.add_argument("--comparison-scope", type=Path, help="可选的独立比较口径审计 JSON")
    parser.add_argument("--output", type=Path, help="输出 JSON；省略则写标准输出")
    parser.add_argument("--force", action="store_true", help="显式确认覆盖已存在的输出文件")
    parser.add_argument("--positive-min", type=float, default=4.0)
    parser.add_argument("--negative-max", type=float, default=2.0)
    parser.add_argument("--small-sample-threshold", type=int, default=10)
    parser.add_argument("--low-info-min-chars", type=int, default=4)
    parser.add_argument("--sku-imbalance-threshold", type=float, default=0.8)
    return parser


def _paths_identical(left: Path, right: Path) -> bool:
    if left.resolve() == right.resolve():
        return True
    if left.exists() and right.exists():
        return left.samefile(right)
    return False


def validate_output_path(
    input_path: Path,
    annotations_path: Path | None,
    comparison_scope_path: Path | None,
    output_path: Path | None,
    force: bool = False,
) -> None:
    """保护输入源，并默认禁止覆盖任何已有输出。"""
    if output_path is None:
        return
    protected = [input_path]
    if annotations_path is not None:
        protected.append(annotations_path)
    if comparison_scope_path is not None:
        protected.append(comparison_scope_path)
    if any(_paths_identical(output_path, path) for path in protected):
        raise ReviewInputError("--output 不得覆盖任何输入、标注或比较口径文件")
    if output_path.exists() and not force:
        raise ReviewInputError("--output 已存在；确认需要覆盖后才可显式传入 --force")


def _write_output(output_path: Path, serialized: str, force: bool) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not force:
        try:
            with output_path.open("x", encoding="utf-8") as handle:
                handle.write(serialized)
            return
        except FileExistsError as exc:
            raise ReviewInputError(
                "--output 已存在；确认需要覆盖后才可显式传入 --force"
            ) from exc

    # 不直接截断目标：若目标在校验后被换成输入的硬链接/符号链接，原子替换目录项也不会改写源文件。
    file_descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, output_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.input is None:
            raise ReviewInputError("评价分析必须提供 --input")
        config = AnalysisConfig(
            positive_min=args.positive_min,
            negative_max=args.negative_max,
            small_sample_threshold=args.small_sample_threshold,
            low_info_min_chars=args.low_info_min_chars,
            sku_imbalance_threshold=args.sku_imbalance_threshold,
        )
        validate_output_path(
            args.input,
            args.annotations,
            args.comparison_scope,
            args.output,
            args.force,
        )
        records, metadata = load_input(args.input)
        annotations = load_annotations(args.annotations)
        comparison_scope = load_comparison_scope(args.comparison_scope)
        result = analyze_records(records, metadata, annotations, config, comparison_scope)
        serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            _write_output(args.output, serialized, args.force)
        else:
            sys.stdout.write(serialized)
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, csv.Error, ReviewInputError) as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
