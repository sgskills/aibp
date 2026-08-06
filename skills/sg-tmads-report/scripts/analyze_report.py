#!/usr/bin/env python3
"""天猫推广报表的标准库分析内核。

脚本接收已由宿主盘点后的 JSON，或单个 CSV/TSV。它不直接读取 XLSX，
也不负责推断平台规则；输出只包含可复核聚合、审计警告和离线 HTML。
"""

from __future__ import annotations

import argparse
import copy
import csv
import html
import io
import json
import logging
import math
import os
import re
import sys
import tempfile
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


LOGGER = logging.getLogger("sg-tmads-report")
SCHEMA_VERSION = "2.1"
UNKNOWN_VALUES = {"", "unknown", "未知", "未确认", "n/a", "na", "none", "null"}
TOTAL_LABELS = {"合计", "总计", "汇总", "全部"}
NUMERIC_FIELDS = (
    "impressions",
    "clicks",
    "spend",
    "transaction_orders",
    "buyers",
    "transaction_amount",
)
COUNT_FIELDS = {"impressions", "clicks", "transaction_orders", "buyers"}
FINANCIAL_METRICS = {"break_even_ppc", "promotion_contribution_profit"}
STORE_WIDE_SCOPE_VALUES = {
    "store-wide",
    "storewide",
    "全店",
    "全店统一",
    "全店统一口径",
}
SENSITIVE_HEADER_SIGNALS = (
    "手机号",
    "手机号码",
    "联系电话",
    "电话号码",
    "邮箱",
    "email",
    "订单号",
    "订单id",
    "收件人",
    "收货地址",
    "详细地址",
    "身份证",
    "会员名",
    "旺旺",
)
EMAIL_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
INSTRUCTION_PATTERN = re.compile(
    r"忽略(?:以上|前文|之前)|角色切换|system\s*prompt|developer\s*message|"
    r"执行(?:命令|脚本|宏)|打开(?:链接|网址)",
    re.IGNORECASE,
)
ATTRIBUTION_STATUSES = {"unknown", "reported", "user_confirmed", "conflict"}
ATTRIBUTION_SOURCES = {
    "unknown",
    "sheet_label",
    "export_metadata",
    "user",
    "legacy_field",
}
CONVERSION_OVERLAP_STATUSES = {"unknown", "confirmed_disjoint", "known_overlap"}
CHECKPOINT_STATUSES = {
    "awaiting_user",
    "bypassed_by_user",
    "no_roundtrip",
    "answered",
}
CAUSAL_TOKENS = ("新增", "增量", "带来", "导致")
CAUSAL_GUARDS = (
    "不能证明",
    "尚不能证明",
    "无法证明",
    "未能证明",
    "不足以证明",
    "不代表",
    "不等于",
    "不把",
    "并非",
    "不一定",
    "仅为假设",
    "仍待验证",
    "仍待核验",
)
ACTION_LEVELS = {"execute", "experiment", "investigate", "blocked"}
ACTION_CODES = {
    "maintain",
    "investigate",
    "request_data",
    "hold",
    "increase_budget",
    "decrease_budget",
    "reallocate",
    "increase_bid",
    "decrease_bid",
    "pause",
    "close",
}
ACTION_CODE_ALIASES = {
    "reallocate_budget": "reallocate",
    "stop": "close",
    "disable": "close",
    "terminate": "close",
}
DIRECT_CONTROL_ACTIONS = {
    "increase_budget",
    "decrease_budget",
    "reallocate",
    "increase_bid",
    "decrease_bid",
    "pause",
    "close",
}
BID_ACTIONS = {"increase_bid", "decrease_bid"}
ATTRIBUTION_SENSITIVE_ACTIONS = DIRECT_CONTROL_ACTIONS - {"reallocate"}
ACTION_TEXT_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "close": (
        re.compile(r"(?:立即|立刻|直接|马上)关闭|关闭(?:该|此|这个)?(?:广告|计划|活动)"),
        re.compile(r"(?:immediately\s+)?close\s+(?:this\s+)?(?:campaign|ad)", re.I),
        re.compile(r"(?:terminate|disable)\s+(?:this\s+)?(?:campaign|ad)", re.I),
    ),
    "pause": (
        re.compile(r"(?:立即|立刻|直接|马上)暂停|暂停(?:该|此|这个)?(?:广告|计划|活动)"),
        re.compile(r"(?:immediately\s+)?pause\s+(?:this\s+)?(?:campaign|ad)", re.I),
    ),
    "increase_bid": (
        re.compile(r"(?:增加|提高|上调)(?:点击)?出价|加价抢量"),
        re.compile(r"(?:increase|raise)\s+(?:the\s+)?bid", re.I),
    ),
    "decrease_bid": (
        re.compile(r"(?:降低|减少|下调)(?:点击)?出价"),
        re.compile(r"(?:decrease|lower|reduce)\s+(?:the\s+)?bid", re.I),
    ),
}

HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("日期", "时间", "统计日期", "数据日期", "day", "date"),
    "campaign_id": (
        "计划id",
        "计划ID",
        "推广计划id",
        "推广计划ID",
        "campaignid",
        "campaign_id",
    ),
    "campaign_name": (
        "计划名称",
        "推广计划名称",
        "campaignname",
        "campaign_name",
    ),
    "item_id": (
        "商品id",
        "商品ID",
        "宝贝id",
        "宝贝ID",
        "itemid",
        "item_id",
    ),
    "item_name": (
        "商品名称",
        "宝贝名称",
        "商品标题",
        "宝贝标题",
        "itemname",
        "item_name",
    ),
    "keyword": ("关键词", "关键词名称", "keyword"),
    "impressions": (
        "展现量",
        "展示量",
        "曝光量",
        "展现次数",
        "impressions",
    ),
    "clicks": ("点击量", "点击次数", "clicks"),
    "spend": (
        "花费",
        "花费(元)",
        "消耗",
        "消耗(元)",
        "广告花费",
        "广告花费(元)",
        "spend",
        "cost",
    ),
    "transaction_orders": (
        "总成交笔数",
        "成交笔数",
        "成交订单数",
        "总成交订单数",
        "transactionorders",
        "orders",
    ),
    "buyers": (
        "成交人数",
        "总成交人数",
        "成交买家数",
        "支付买家数",
        "buyers",
    ),
    "transaction_amount": (
        "总成交金额",
        "总成交金额(元)",
        "总支付金额",
        "总支付金额(元)",
        "transactionamount",
    ),
}

AMBIGUOUS_HEADERS = {
    "成交金额": "可能指直接、间接、引导或总成交金额，需确认口径",
    "成交金额(元)": "可能指直接、间接、引导或总成交金额，需确认口径",
    "转化率": "分子口径不明，不能确定是订单或买家转化率",
    "点击转化率": "分子口径不明，不能确定是订单或买家转化率",
    "客单价": "可能指订单均价或人均成交金额，需确认口径",
    "成交成本": "分子可能是订单数或买家数，需确认口径",
}

FIELD_LABELS = {
    "date": "日期",
    "campaign_id": "计划 ID",
    "campaign_name": "计划名称",
    "item_id": "商品 ID",
    "item_name": "商品名称",
    "keyword": "关键词",
    "impressions": "展现量",
    "clicks": "点击量",
    "spend": "花费",
    "transaction_orders": "总成交笔数",
    "buyers": "成交人数",
    "transaction_amount": "总成交金额",
}

METRIC_LABELS = {
    "roi": "ROI / 投产比",
    "cpc": "CPC",
    "ctr": "CTR",
    "order_cvr": "订单 CVR",
    "order_aov": "订单均价",
    "buyer_cvr": "买家 CVR",
    "buyer_aov": "人均成交金额",
    "transaction_value_per_click": "每点击成交金额",
    "break_even_ppc": "保本 PPC",
    "promotion_contribution_profit": "商品毛利口径推广贡献盈亏",
}


class InputFormatError(ValueError):
    """输入格式无法安全解释。"""


def _normalize_header(value: Any) -> str:
    text = unicodedata.normalize("NFKC", "" if value is None else str(value))
    text = text.replace("\ufeff", "").strip()
    return re.sub(r"\s+", "", text).lower()


NORMALIZED_ALIASES = {
    _normalize_header(alias): canonical
    for canonical, aliases in HEADER_ALIASES.items()
    for alias in aliases
}
NORMALIZED_AMBIGUOUS = {
    _normalize_header(header): reason for header, reason in AMBIGUOUS_HEADERS.items()
}


def _is_sensitive_header(value: Any) -> bool:
    normalized = _normalize_header(value)
    return any(_normalize_header(signal) in normalized for signal in SENSITIVE_HEADER_SIGNALS)


def _mask_raw_value(header: Any, value: Any) -> Any:
    """显式原始输出仍强制遮蔽常见敏感标识；这不是完整 DLP。"""

    if _is_sensitive_header(header):
        return "[已脱敏]"
    if isinstance(value, str):
        if EMAIL_PATTERN.search(value) or PHONE_PATTERN.search(value):
            return "[已脱敏]"
    return _json_safe(value)


def _mask_raw_row(
    row: Mapping[str, Any],
    allowed_headers: set[str],
) -> dict[str, Any]:
    """只输出已安全映射字段；未知原始字段即使显式请求也不序列化。"""

    return {
        str(key): _mask_raw_value(key, value)
        for key, value in row.items()
        if str(key) in allowed_headers
    }


def map_headers(headers: Iterable[Any]) -> dict[str, dict[str, Any]]:
    """映射表头，并保留歧义/未映射状态。

    返回值以原表头字符串为键，适合审计展示。重复同名列在表格接入阶段应按列序号
    另行保留，不能只依赖本函数的字典结构。
    """

    ledger: dict[str, dict[str, Any]] = {}
    for raw_value in headers:
        raw = str(raw_value)
        normalized = _normalize_header(raw)
        if normalized in NORMALIZED_AMBIGUOUS:
            ledger[raw] = {
                "canonical": None,
                "status": "ambiguous",
                "confidence": 0.0,
                "normalized": normalized,
                "reason": NORMALIZED_AMBIGUOUS[normalized],
            }
        elif normalized in NORMALIZED_ALIASES:
            canonical = NORMALIZED_ALIASES[normalized]
            exact = any(raw == alias for alias in HEADER_ALIASES[canonical])
            ledger[raw] = {
                "canonical": canonical,
                "status": "mapped",
                "confidence": 1.0 if exact else 0.95,
                "normalized": normalized,
                "reason": "明确别名" if exact else "仅规范化空白、全半角或大小写后匹配",
            }
        else:
            ledger[raw] = {
                "canonical": None,
                "status": "unmapped",
                "confidence": 0.0,
                "normalized": normalized,
                "reason": "未进入安全别名表；仅保留字段名供审计，不输出原始值",
            }
    return ledger


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    return str(value)


def _to_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = unicodedata.normalize("NFKC", str(value)).strip()
    if _normalize_header(text) in UNKNOWN_VALUES or text in {"-", "--", "—"}:
        return None
    is_percent = text.endswith("%")
    cleaned = (
        text.rstrip("%")
        .replace(",", "")
        .replace("，", "")
        .replace("¥", "")
        .replace("￥", "")
        .replace("元", "")
        .strip()
    )
    try:
        number = float(cleaned)
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return number / 100 if is_percent else number


def _to_rate(value: Any) -> tuple[float | None, str | None]:
    if value is None or value == "":
        return None, "未提供"
    if isinstance(value, str) and value.strip().endswith("%"):
        rate = _to_number(value)
    else:
        rate = _to_number(value)
        if rate is not None and rate > 1:
            return None, "裸数大于 1，无法确认是否为百分数"
    if rate is None or not 0 <= rate <= 1:
        return None, "必须是 0–1 小数或带 % 的百分数"
    return rate, None


def _to_scope(value: Any) -> tuple[str | None, str | None]:
    if value is None or str(value).strip() == "":
        return None, "未提供费率适用范围"
    normalized = _normalize_header(value)
    if normalized in {_normalize_header(item) for item in STORE_WIDE_SCOPE_VALUES}:
        return "store-wide", None
    return None, "当前统一费率只支持 store-wide（全店统一）口径"


def _parse_numeric_field(value: Any, field: str) -> tuple[float | None, str | None]:
    """按字段校验数值，避免百分数、负数和小数计数被静默纳入汇总。"""

    if value is None or _normalize_header(value) in UNKNOWN_VALUES:
        return None, None
    text = unicodedata.normalize("NFKC", str(value)).strip()
    if text in {"-", "--", "—"}:
        return None, None
    if text.endswith("%"):
        return None, "核心推广数值字段不接受百分数"
    number = _to_number(value)
    if number is None:
        return None, "不是可解析的有限数值"
    if number < 0:
        return None, "核心推广字段默认不得为负数"
    if field in COUNT_FIELDS and not number.is_integer():
        return None, "计数字段必须是非负整数"
    return number, None


def _to_identifier(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _to_date(value: Any) -> tuple[str, bool]:
    if value is None or str(value).strip() == "":
        return "", False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if 1 <= number <= 100000 and math.isfinite(number):
            parsed = datetime(1899, 12, 30) + timedelta(days=number)
            return parsed.date().isoformat(), True
    text = unicodedata.normalize("NFKC", str(value)).strip()
    candidates = (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%Y年%m月%d日",
        "%Y-%m-%d %H:%M:%S",
    )
    for pattern in candidates:
        try:
            return datetime.strptime(text, pattern).date().isoformat(), True
        except ValueError:
            continue
    return text, False


def _value_type(value: Any) -> str:
    if value is None or str(value).strip() == "":
        return "empty"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return "number"
    _, valid_date = _to_date(value)
    if valid_date:
        return "date"
    if _to_number(value) is not None:
        return "number"
    return "text"


def _untrusted_signals(values: Iterable[Any]) -> dict[str, int]:
    signals = {"formula_or_command": 0, "external_link": 0, "instruction_like": 0}
    for value in values:
        if not isinstance(value, str):
            continue
        text = unicodedata.normalize("NFKC", value).strip()
        if text.startswith(("=", "+", "@")):
            signals["formula_or_command"] += 1
        if re.search(r"(?i)\b(?:https?|ftp)://", text):
            signals["external_link"] += 1
        if INSTRUCTION_PATTERN.search(text):
            signals["instruction_like"] += 1
    return {key: count for key, count in signals.items() if count}


def _column_profiles(
    headers: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
    ledger: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """只输出未知/歧义列的元数据，不输出其原始值。"""

    profiles: list[dict[str, Any]] = []
    row_count = len(rows)
    for raw in headers:
        mapping = ledger.get(raw) or {}
        if mapping.get("status") == "mapped":
            continue
        values = [row.get(raw) for row in rows]
        non_empty = [value for value in values if value is not None and str(value).strip()]
        types = {_value_type(value) for value in non_empty}
        inferred_type = next(iter(types)) if len(types) == 1 else ("mixed" if types else "empty")
        profiles.append(
            {
                "raw": raw,
                "mapping_status": mapping.get("status", "unmapped"),
                "inferred_type": inferred_type,
                "non_empty_rate": (len(non_empty) / row_count) if row_count else 0.0,
                "risk_signals": _untrusted_signals(non_empty),
                "sensitive_name": _is_sensitive_header(raw),
            }
        )
    return profiles


def _is_unknown(value: Any) -> bool:
    return _normalize_header(value) in UNKNOWN_VALUES


def _infer_report_type(name: str, explicit: Any) -> tuple[str, bool]:
    if not _is_unknown(explicit):
        return str(explicit).strip(), True
    normalized = _normalize_header(name)
    signals = (
        ("全站", "full-site-unconfirmed"),
        ("视频", "video-unconfirmed"),
        ("内容", "content-unconfirmed"),
        ("万相台", "wanxiangtai-unconfirmed"),
        ("万象台", "wanxiangtai-unconfirmed"),
        ("标准", "standard-unconfirmed"),
    )
    for signal, label in signals:
        if signal in normalized:
            return label, False
    return "unknown", False


def _enum_value(value: Any) -> str:
    text = unicodedata.normalize("NFKC", "" if value is None else str(value))
    return text.strip().lower().replace("-", "_").replace(" ", "_")


def _normalize_attribution(
    dataset: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """区分报表记录、用户确认与冲突，避免把非空窗口冒充用户确认。"""

    window = str(dataset.get("attribution_window") or "unknown").strip()
    known_window = not _is_unknown(window)
    status_provided = "attribution_status" in dataset
    source_provided = "attribution_source" in dataset
    issues: list[dict[str, str]] = []

    if not status_provided and not source_provided:
        status = "reported" if known_window else "unknown"
        source = "legacy_field" if known_window else "unknown"
    else:
        status = _enum_value(dataset.get("attribution_status")) or "unknown"
        source = _enum_value(dataset.get("attribution_source")) or "unknown"
        conflict = (
            status not in ATTRIBUTION_STATUSES
            or source not in ATTRIBUTION_SOURCES
            or (status == "user_confirmed" and (source != "user" or not known_window))
            or (status == "reported" and not known_window)
            or (status == "unknown" and known_window)
            or (status == "conflict")
        )
        if conflict:
            status = "conflict"
            issues.append(
                {
                    "code": "ATTRIBUTION_PROVENANCE_CONFLICT",
                    "message": "归因窗口、确认状态与来源互相冲突，已按未确认处理。",
                }
            )

    return {
        "window": window,
        "status": status,
        "source": source,
        "confirmed": status == "user_confirmed",
        "language_allowed": known_window and status in {"reported", "user_confirmed"},
    }, issues


def _collect_headers(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    headers: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            text = str(key)
            if text not in seen:
                seen.add(text)
                headers.append(text)
    return headers


def _is_total_row(row: Mapping[str, Any]) -> bool:
    for field in ("date", "campaign_id", "campaign_name", "item_id", "item_name"):
        value = str(row.get(field, "")).strip()
        if value in TOTAL_LABELS:
            return True
    return False


def _normalize_dataset(
    dataset: Mapping[str, Any],
    index: int,
    include_raw: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    name = str(dataset.get("name") or f"dataset-{index}")
    dataset_id = _to_identifier(dataset.get("dataset_id")) or f"dataset-{index}"
    raw_rows = dataset.get("rows")
    if not isinstance(raw_rows, list):
        raise InputFormatError(f"{name}: rows 必须是数组")
    if any(not isinstance(row, Mapping) for row in raw_rows):
        raise InputFormatError(f"{name}: 每一行必须是对象")

    headers = _collect_headers(raw_rows)
    ledger = map_headers(headers)
    untrusted_signals = _untrusted_signals(
        value
        for source in ([name], headers, *(row.values() for row in raw_rows))
        for value in source
    )
    mapped_by_canonical: dict[str, list[str]] = defaultdict(list)
    for raw, item in ledger.items():
        canonical = item.get("canonical")
        if item["status"] == "mapped" and canonical:
            mapped_by_canonical[str(canonical)].append(raw)

    conflicts = {
        canonical: raw_fields
        for canonical, raw_fields in mapped_by_canonical.items()
        if len(raw_fields) > 1
    }
    for canonical, raw_fields in conflicts.items():
        for raw in raw_fields:
            ledger[raw] = {
                **ledger[raw],
                "canonical": None,
                "status": "ambiguous",
                "confidence": 0.0,
                "reason": f"多个字段同时映射到 {canonical}: {', '.join(raw_fields)}",
            }
        mapped_by_canonical.pop(canonical, None)
    allowed_raw_headers = {
        raw
        for raw_fields in mapped_by_canonical.values()
        for raw in raw_fields
    }

    details: list[dict[str, Any]] = []
    warnings: list[str] = []
    invalid_rows: list[dict[str, Any]] = []
    invalid_dates = 0
    total_rows = 0
    fingerprints: dict[str, int] = defaultdict(int)
    for row_number, raw_row in enumerate(raw_rows, start=1):
        raw_json = json.dumps(
            _json_safe(raw_row),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        fingerprints[raw_json] += 1
        detail: dict[str, Any] = {
            "source_dataset": name,
            "source_row": row_number,
        }
        if include_raw:
            detail["source_values"] = _mask_raw_row(raw_row, allowed_raw_headers)
        invalid_fields: list[str] = []
        for canonical, raw_fields in mapped_by_canonical.items():
            value = raw_row.get(raw_fields[0])
            if canonical in NUMERIC_FIELDS:
                number, validation_error = _parse_numeric_field(value, canonical)
                detail[canonical] = number
                if validation_error:
                    invalid_rows.append(
                        {
                            "source_row": row_number,
                            "field": canonical,
                            "raw_field": raw_fields[0],
                            "value": _json_safe(value),
                            "reason": validation_error,
                        }
                    )
                    invalid_fields.append(canonical)
            elif canonical in {"campaign_id", "item_id"}:
                detail[canonical] = _to_identifier(value)
            elif canonical == "date":
                normalized_date, valid = _to_date(value)
                detail[canonical] = normalized_date
                if normalized_date and not valid:
                    invalid_dates += 1
            else:
                detail[canonical] = "" if value is None else str(value).strip()
        if _is_total_row(detail):
            detail["excluded_reason"] = "subtotal_row"
        elif invalid_fields:
            detail["excluded_reason"] = "invalid_value"
            detail["invalid_fields"] = invalid_fields
        else:
            detail["excluded_reason"] = None
        if detail["excluded_reason"]:
            if detail["excluded_reason"] == "subtotal_row":
                total_rows += 1
        details.append(detail)

    duplicate_rows = sum(count - 1 for count in fingerprints.values() if count > 1)
    if duplicate_rows:
        warnings.append(
            f"{name} 检测到 {duplicate_rows} 个完全重复行；未静默去重，汇总可能重复，需确认。"
        )
    if total_rows:
        warnings.append(f"{name} 检测到 {total_rows} 个合计/汇总行，已保留审计但排除计算。")
    if invalid_dates:
        warnings.append(f"{name} 有 {invalid_dates} 个日期无法规范化，未伪造日期。")
    if invalid_rows:
        invalid_row_count = len({item["source_row"] for item in invalid_rows})
        warnings.append(
            f"{name} 有 {invalid_row_count} 行核心数值超出非负取值域，"
            "已进入审表日志并整行排除计算；若为退款或冲销，请确认专属口径后另行建模。"
        )
    if untrusted_signals:
        warnings.append(
            f"{name} 检测到 {sum(untrusted_signals.values())} 个不可信文本信号；"
            "仅记录分类计数并按数据处理，未执行其中的指令、公式或链接。"
        )
    if include_raw:
        warnings.append(
            f"{name} 已按显式 --include-raw 请求附带脱敏原始行；"
            "自动脱敏不等于完整隐私审计。"
        )
    ambiguous = [raw for raw, item in ledger.items() if item["status"] == "ambiguous"]
    if ambiguous:
        warnings.append(f"{name} 存在歧义字段：{'、'.join(ambiguous)}；相关指标未计算。")

    report_type, report_type_confirmed = _infer_report_type(
        name, dataset.get("report_type", "unknown")
    )
    attribution, attribution_issues = _normalize_attribution(dataset)
    conversion_overlap = _enum_value(dataset.get("conversion_overlap")) or "unknown"
    if conversion_overlap not in CONVERSION_OVERLAP_STATUSES:
        conversion_overlap = "unknown"
        attribution_issues.append(
            {
                "code": "CONVERSION_OVERLAP_INVALID",
                "message": "跨岛成交重叠状态无效，已按 unknown 处理。",
            }
        )
    available = set(mapped_by_canonical)
    content_signals = any(
        token in _normalize_header(header)
        for header in headers
        for token in ("播放", "互动", "内容")
    ) or any(token in _normalize_header(name) for token in ("视频", "内容"))

    minimum = {"clicks", "spend", "transaction_amount"}
    identity = bool({"campaign_id", "campaign_name"} & available)
    conversion = bool({"transaction_orders", "buyers"} & available)
    if minimum <= available and conversion and "date" in available and identity:
        status = "complete"
    elif not ({"spend", "transaction_amount"} & available) and content_signals:
        status = "wrong_report"
    elif available & set(NUMERIC_FIELDS):
        status = "partial"
    else:
        status = "wrong_report"
    if invalid_rows and status == "complete":
        status = "partial"

    required_fields: list[str] = []
    required_candidates = (
        ("date", "日期"),
        ("campaign_id", "计划 ID（或计划名称）"),
        ("clicks", "点击量"),
        ("spend", "花费"),
        ("transaction_amount", "总成交金额"),
    )
    for canonical, label in required_candidates:
        if canonical == "campaign_id":
            if not identity:
                required_fields.append(label)
        elif canonical not in available:
            required_fields.append(label)
    if not conversion:
        required_fields.append("总成交笔数或成交人数")

    inventory = {
        "dataset_id": dataset_id,
        "name": name,
        "rows": len(raw_rows),
        "headers": headers,
        "mapped_fields": sorted(available),
        "report_type": report_type,
        "report_type_confirmed": report_type_confirmed,
        "attribution_window": attribution["window"],
        "attribution_status": attribution["status"],
        "attribution_source": attribution["source"],
        "attribution_confirmed": attribution["confirmed"],
        "conversion_overlap": conversion_overlap,
        "status": status,
        "required_fields": required_fields,
        "duplicate_rows": duplicate_rows,
        "subtotal_rows": total_rows,
        "invalid_dates": invalid_dates,
        "invalid_rows": invalid_rows,
        "untrusted_signals": untrusted_signals,
        "column_profiles": _column_profiles(headers, raw_rows, ledger),
        "raw_included": include_raw,
    }
    return {
        "dataset_id": dataset_id,
        "name": name,
        "report_type": report_type,
        "report_type_confirmed": report_type_confirmed,
        "attribution_window": attribution["window"],
        "attribution_status": attribution["status"],
        "attribution_source": attribution["source"],
        "attribution_confirmed": attribution["confirmed"],
        "attributed_language_allowed": attribution["language_allowed"],
        "conversion_overlap": conversion_overlap,
        "validation_issues": attribution_issues,
        "status": status,
        "required_fields": required_fields,
        "mapping": [{"raw": raw, **item} for raw, item in ledger.items()],
        "details": details,
        "available_fields": available,
        "inventory": inventory,
    }, warnings


def _field_sum(rows: Sequence[Mapping[str, Any]], field: str) -> tuple[float | None, bool]:
    values = [row.get(field) for row in rows]
    if not rows or not values or any(value is None for value in values):
        return None, False
    return sum(float(value) for value in values), True


def _safe_ratio(
    name: str,
    numerator: float,
    denominator: float,
    metrics: dict[str, float | None],
    not_computable: dict[str, str],
) -> None:
    if denominator == 0:
        metrics[name] = None
        not_computable[name] = "分母为 0"
    else:
        metrics[name] = numerator / denominator


def _compute_aggregate(
    rows: Sequence[Mapping[str, Any]],
    gross_margin_rate: float | None,
    refund_amount_rate: float | None,
) -> tuple[dict[str, float], dict[str, float | None], dict[str, str]]:
    usable = [row for row in rows if not row.get("excluded_reason")]
    totals: dict[str, float] = {}
    complete: dict[str, bool] = {}
    for field in NUMERIC_FIELDS:
        total, is_complete = _field_sum(usable, field)
        complete[field] = is_complete
        if total is not None:
            totals[field] = total

    metrics: dict[str, float | None] = {}
    not_computable: dict[str, str] = {}
    formulas = (
        ("roi", "transaction_amount", "spend"),
        ("cpc", "spend", "clicks"),
        ("ctr", "clicks", "impressions"),
        ("order_cvr", "transaction_orders", "clicks"),
        ("order_aov", "transaction_amount", "transaction_orders"),
        ("buyer_cvr", "buyers", "clicks"),
        ("buyer_aov", "transaction_amount", "buyers"),
        ("transaction_value_per_click", "transaction_amount", "clicks"),
    )
    for metric, numerator_field, denominator_field in formulas:
        if complete[numerator_field] and complete[denominator_field]:
            _safe_ratio(
                metric,
                totals[numerator_field],
                totals[denominator_field],
                metrics,
                not_computable,
            )

    profit_ready = gross_margin_rate is not None and refund_amount_rate is not None
    if profit_ready and complete["transaction_amount"] and complete["clicks"]:
        value_per_click = totals["transaction_amount"]
        if totals["clicks"] == 0:
            metrics["break_even_ppc"] = None
            not_computable["break_even_ppc"] = "点击量为 0"
        else:
            value_per_click /= totals["clicks"]
            metrics["break_even_ppc"] = (
                value_per_click * (1 - refund_amount_rate) * gross_margin_rate
            )
    if profit_ready and complete["transaction_amount"] and complete["spend"]:
        metrics["promotion_contribution_profit"] = (
            totals["transaction_amount"]
            * (1 - refund_amount_rate)
            * gross_margin_rate
            - totals["spend"]
        )
    return totals, metrics, not_computable


def _campaign_identity_key(row: Mapping[str, Any]) -> str | None:
    campaign_id = str(row.get("campaign_id") or "").strip()
    if campaign_id:
        return f"id:{campaign_id}"
    campaign_name = str(row.get("campaign_name") or "").strip()
    if campaign_name:
        return f"name:{campaign_name}"
    return None


def _campaign_date_coverage(
    details: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """区分计划源文件缺日与异常行被隔离；缺失日期不会补零。"""

    identities: set[str] = set()
    source_dates: dict[str, set[str]] = defaultdict(set)
    usable_dates: dict[str, set[str]] = defaultdict(set)
    excluded_dates: dict[str, set[str]] = defaultdict(set)

    for row in details:
        key = _campaign_identity_key(row)
        if key is None:
            continue
        identities.add(key)
        normalized_date, valid = _to_date(row.get("date"))
        if not valid:
            continue
        source_dates[key].add(normalized_date)
        if row.get("excluded_reason"):
            excluded_dates[key].add(normalized_date)
        else:
            usable_dates[key].add(normalized_date)

    coverage: dict[str, dict[str, Any]] = {}
    for key in sorted(identities):
        observed = source_dates[key]
        if not observed:
            coverage[key] = {
                "basis": "campaign_observed_date_span",
                "start_date": None,
                "end_date": None,
                "source_date_count": 0,
                "usable_date_count": 0,
                "missing_source_dates": [],
                "excluded_dates": [],
                "fully_excluded_dates": [],
            }
            continue

        start_date = datetime.strptime(min(observed), "%Y-%m-%d").date()
        end_date = datetime.strptime(max(observed), "%Y-%m-%d").date()
        expected_dates: set[str] = set()
        current_date = start_date
        while current_date <= end_date:
            expected_dates.add(current_date.isoformat())
            current_date += timedelta(days=1)

        excluded = excluded_dates[key]
        usable = usable_dates[key]
        coverage[key] = {
            "basis": "campaign_observed_date_span",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "source_date_count": len(observed),
            "usable_date_count": len(usable),
            "missing_source_dates": sorted(expected_dates - observed),
            "excluded_dates": sorted(excluded),
            "fully_excluded_dates": sorted(excluded - usable),
        }
    return coverage


def _group_summaries(
    details: Sequence[Mapping[str, Any]],
    group_type: str,
    gross_margin_rate: float | None,
    refund_amount_rate: float | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    labels: dict[str, dict[str, str]] = {}
    warnings: list[str] = []
    for row in details:
        if row.get("excluded_reason"):
            continue
        if group_type == "date":
            date = str(row.get("date") or "")
            if not date:
                continue
            key = date
            labels[key] = {"date": date}
        elif group_type == "campaign":
            campaign_id = str(row.get("campaign_id") or "").strip()
            campaign_name = str(row.get("campaign_name") or "").strip()
            key = _campaign_identity_key(row)
            if key is None:
                key = f"row:{row.get('source_dataset')}:{row.get('source_row')}"
            labels[key] = {
                "campaign_id": campaign_id,
                "campaign_name": campaign_name,
                "identity_confidence": "high" if campaign_id else "low",
            }
            if not campaign_id and campaign_name:
                warnings.append(f"计划“{campaign_name}”缺少 ID，仅按名称临时分组。")
        elif group_type == "item_campaign":
            item_id = str(row.get("item_id") or "").strip()
            item_name = str(row.get("item_name") or "").strip()
            campaign_id = str(row.get("campaign_id") or "").strip()
            campaign_name = str(row.get("campaign_name") or "").strip()
            if not (item_id or item_name) or not (campaign_id or campaign_name):
                continue
            item_key = f"id:{item_id}" if item_id else f"name:{item_name}"
            campaign_key = (
                f"id:{campaign_id}" if campaign_id else f"name:{campaign_name}"
            )
            key = f"{item_key}|{campaign_key}"
            labels[key] = {
                "item_id": item_id,
                "item_name": item_name,
                "campaign_id": campaign_id,
                "campaign_name": campaign_name,
                "item_identity_confidence": "high" if item_id else "low",
                "campaign_identity_confidence": "high" if campaign_id else "low",
            }
        else:
            raise ValueError(f"未知分组类型：{group_type}")
        groups[key].append(row)

    summaries: list[dict[str, Any]] = []
    for key in sorted(groups):
        totals, metrics, not_computable = _compute_aggregate(
            groups[key], gross_margin_rate, refund_amount_rate
        )
        summaries.append(
            {
                **labels[key],
                "row_count": len(groups[key]),
                "totals": totals,
                "metrics": metrics,
                "not_computable": not_computable,
            }
        )
    return summaries, list(dict.fromkeys(warnings))


def _build_questions(
    request: Mapping[str, Any],
    gross_margin_rate: float | None,
    refund_amount_rate: float | None,
    financial_scope: str | None,
    datasets: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []

    def add(field: str, question: str, reason: str) -> None:
        if len(questions) < 5:
            questions.append({"field": field, "question": question, "reason": reason})

    if not str(request.get("goal") or "").strip():
        add(
            "business_goal",
            "你最想用这份数据做什么经营决策，最关心规模、效率、盈亏还是预算分配？",
            "目标决定诊断优先级，避免把所有指标平均用力。",
        )
    if gross_margin_rate is None:
        add(
            "gross_margin_rate",
            "商品毛利率是多少，是否仅按成交金额扣商品成本，适用于全店还是指定商品？",
            "缺少该口径时不能计算相关盈亏与保本数值。",
        )
    if refund_amount_rate is None:
        add(
            "refund_amount_rate",
            "对应周期的退款金额率是多少；若用全店统一值，是否允许套用全部日期和商品？",
            "退款金额率直接改变商品毛利口径贡献与保本线。",
        )
    if (
        gross_margin_rate is not None
        and refund_amount_rate is not None
        and financial_scope is None
    ):
        add(
            "scope",
            "这组商品毛利率和退款金额率是否为全店统一口径（store-wide）？",
            "费率适用范围未确认时不能计算推广贡献盈亏与保本 PPC。",
        )
    context_gaps = [
        str(dataset.get("name"))
        for dataset in datasets
        if not dataset.get("report_type_confirmed")
        or not dataset.get("attribution_confirmed")
    ]
    if context_gaps:
        add(
            "report_context",
            "请确认这些数据的报表来源、粒度和归因窗口："
            + "、".join(context_gaps[:5]),
            "未确认前必须分岛，不能合并成交或写因果结论。",
        )
    if not request.get("budget_constraints") and not request.get(
        "non_pause_constraints"
    ):
        add(
            "execution_constraints",
            "是否有预算上限、必须保留或不可暂停的计划？",
            "执行约束会改变预算调整和暂停建议。",
        )
    return questions


def _unsupported_requests(
    goal: str,
    available_fields: set[str],
    attribution_unknown: bool,
) -> list[str]:
    unsupported: list[str] = []
    normalized = _normalize_header(goal)
    if "关键词" in normalized and "keyword" not in available_fields:
        unsupported.append(
            "当前数据没有关键词维度，不能生成关键词名单、CPC 或降价比例；"
            "请补充关键词、点击量、花费、成交笔数和总成交金额。"
        )
    if any(token in normalized for token in ("行业标准", "行业阈值", "标准roi", "标准cpc")):
        unsupported.append(
            "未提供可核验的当期官方来源和适用范围，不能编造行业标准阈值；"
            "可改用用户目标、店铺历史或保本公式比较。"
        )
    if attribution_unknown and any(token in normalized for token in ("新增", "带来", "增量", "导致")):
        unsupported.append(
            "归因窗口未知，不能回答新增、增量或“广告带来”的因果问题；"
            "只能描述当前报表记录值。"
        )
    return unsupported


def _validation_issue(code: str, message: str, **context: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **context}


def _build_budget_checks(
    request: Mapping[str, Any],
    datasets: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """只在预算作用域和花费可加性明确时做确定性周期检查。"""

    raw_constraints = request.get("budget_constraints")
    if not isinstance(raw_constraints, list):
        return [], []
    dataset_by_id = {str(item.get("dataset_id")): item for item in datasets}
    checks: list[dict[str, Any]] = []
    all_issues: list[dict[str, Any]] = []

    for index, raw in enumerate(raw_constraints, start=1):
        if not isinstance(raw, Mapping):
            continue
        constraint_id = _to_identifier(raw.get("id")) or f"budget-{index}"
        amount_raw = raw.get("amount")
        amount = _to_number(amount_raw)
        period = _enum_value(raw.get("period"))
        scope_type = _enum_value(raw.get("scope_type"))
        source = _enum_value(raw.get("source"))
        hard_limit = raw.get("hard_limit") is True
        spend_additivity_confirmed = (
            raw.get("spend_additivity_confirmed") is True
        )
        raw_dataset_ids = raw.get("dataset_ids")
        dataset_ids = (
            [_to_identifier(item) for item in raw_dataset_ids]
            if isinstance(raw_dataset_ids, list)
            else []
        )
        dataset_ids = [item for item in dataset_ids if item]
        check: dict[str, Any] = {
            "constraint_id": constraint_id,
            "status": "not_computable",
            "amount": amount,
            "period": period or "unknown",
            "scope_type": scope_type or "unknown",
            "dataset_ids": dataset_ids,
            "source": source or "unknown",
            "hard_limit": hard_limit,
            "spend_additivity_confirmed": spend_additivity_confirmed,
            "periods": [],
            "issues": [],
        }

        scope_invalid = (
            amount is None
            or amount < 0
            or (isinstance(amount_raw, str) and amount_raw.strip().endswith("%"))
            or period != "daily"
            or scope_type not in {"dataset", "portfolio"}
            or source != "user"
            or (scope_type == "dataset" and not dataset_ids)
            or any(item not in dataset_by_id for item in dataset_ids)
            or (
                scope_type == "portfolio"
                and not spend_additivity_confirmed
            )
        )
        if scope_invalid:
            issue = _validation_issue(
                "BUDGET_SCOPE_UNCONFIRMED",
                "预算金额、周期、作用域或跨岛花费可加性未确认，不能计算超限。",
                constraint_id=constraint_id,
            )
            check["issues"].append(issue)
            all_issues.append(issue)
            checks.append(check)
            continue

        selected_ids = dataset_ids or list(dataset_by_id)
        grouped_spend: dict[str, float] = defaultdict(float)
        data_incomplete = False
        for dataset_id in selected_ids:
            dataset = dataset_by_id[dataset_id]
            inventory = dataset.get("inventory") or {}
            if inventory.get("duplicate_rows") or inventory.get("invalid_rows"):
                data_incomplete = True
            for row in dataset.get("details") or []:
                if row.get("excluded_reason"):
                    continue
                day = str(row.get("date") or "")
                spend = row.get("spend")
                if not day or spend is None:
                    data_incomplete = True
                    continue
                grouped_spend[day] += float(spend)

        if data_incomplete or not grouped_spend:
            issue = _validation_issue(
                "BUDGET_DATA_INCOMPLETE",
                "预算作用域存在重复、异常或缺日期/花费的行，不能给出单一超限结论。",
                constraint_id=constraint_id,
            )
            check["issues"].append(issue)
            all_issues.append(issue)
            checks.append(check)
            continue

        check["status"] = "complete"
        check["dataset_ids"] = selected_ids
        check["periods"] = [
            {
                "period": day,
                "observed_spend": grouped_spend[day],
                "limit": amount,
                "over_limit": grouped_spend[day] > float(amount),
            }
            for day in sorted(grouped_spend)
        ]
        checks.append(check)

    return checks, all_issues


def analyze_payload(
    payload: Mapping[str, Any],
    *,
    include_raw: bool = False,
    checkpoint_status: str | None = None,
    file_status: str = "not_created",
) -> dict[str, Any]:
    """审计并分析规范化报表 payload。"""

    if not isinstance(payload, Mapping):
        raise InputFormatError("顶层输入必须是对象")
    datasets_raw = payload.get("datasets")
    if not isinstance(datasets_raw, list):
        raise InputFormatError("datasets 必须是数组")
    request_raw = payload.get("request") or {}
    assumptions_raw = payload.get("assumptions") or {}
    if not isinstance(request_raw, Mapping) or not isinstance(assumptions_raw, Mapping):
        raise InputFormatError("request 和 assumptions 必须是对象")

    gross_margin_rate, margin_error = _to_rate(
        assumptions_raw.get("gross_margin_rate")
    )
    refund_amount_rate, refund_error = _to_rate(
        assumptions_raw.get("refund_amount_rate")
    )
    financial_scope, scope_error = _to_scope(assumptions_raw.get("scope"))
    warnings: list[str] = []
    if margin_error and assumptions_raw.get("gross_margin_rate") not in (None, ""):
        warnings.append(f"商品毛利率无效：{margin_error}。")
    if refund_error and assumptions_raw.get("refund_amount_rate") not in (None, ""):
        warnings.append(f"退款金额率无效：{refund_error}。")
    if (
        gross_margin_rate is not None
        and refund_amount_rate is not None
        and scope_error
    ):
        warnings.append(f"费率适用范围无效：{scope_error}；已关闭推广贡献盈亏与保本 PPC。")
    effective_gross_margin_rate = (
        gross_margin_rate if financial_scope == "store-wide" else None
    )
    effective_refund_amount_rate = (
        refund_amount_rate if financial_scope == "store-wide" else None
    )

    normalized_datasets: list[dict[str, Any]] = []
    validation_issues: list[dict[str, Any]] = []
    for index, dataset in enumerate(datasets_raw, start=1):
        if not isinstance(dataset, Mapping):
            raise InputFormatError(f"datasets[{index - 1}] 必须是对象")
        normalized, dataset_warnings = _normalize_dataset(
            dataset,
            index,
            include_raw=include_raw,
        )
        normalized_datasets.append(normalized)
        validation_issues.extend(normalized.get("validation_issues") or [])
        warnings.extend(dataset_warnings)

    islands: list[dict[str, Any]] = []
    all_available: set[str] = set()
    mapping_ledger: list[dict[str, Any]] = []
    required_fields: list[str] = []
    for index, dataset in enumerate(normalized_datasets, start=1):
        all_available.update(dataset["available_fields"])
        mapping_ledger.extend(
            {
                "dataset_id": dataset["dataset_id"],
                "dataset": dataset["name"],
                **entry,
            }
            for entry in dataset["mapping"]
        )
        required_fields.extend(dataset["required_fields"])
        totals, metrics, not_computable = _compute_aggregate(
            dataset["details"],
            effective_gross_margin_rate,
            effective_refund_amount_rate,
        )
        daily, daily_warnings = _group_summaries(
            dataset["details"],
            "date",
            effective_gross_margin_rate,
            effective_refund_amount_rate,
        )
        campaigns, campaign_warnings = _group_summaries(
            dataset["details"],
            "campaign",
            effective_gross_margin_rate,
            effective_refund_amount_rate,
        )
        campaign_date_coverage = _campaign_date_coverage(dataset["details"])
        for campaign in campaigns:
            identity_key = _campaign_identity_key(campaign)
            campaign["date_coverage"] = campaign_date_coverage.get(
                identity_key or "",
                {
                    "basis": "campaign_observed_date_span",
                    "start_date": None,
                    "end_date": None,
                    "source_date_count": 0,
                    "usable_date_count": 0,
                    "missing_source_dates": [],
                    "excluded_dates": [],
                    "fully_excluded_dates": [],
                },
            )
        item_campaigns, item_campaign_warnings = _group_summaries(
            dataset["details"],
            "item_campaign",
            effective_gross_margin_rate,
            effective_refund_amount_rate,
        )
        warnings.extend(daily_warnings)
        warnings.extend(campaign_warnings)
        warnings.extend(item_campaign_warnings)
        item_keys = {
            str(row.get("item_id") or row.get("item_name") or "")
            for row in dataset["details"]
            if row.get("item_id") or row.get("item_name")
        }
        date_keys = {
            str(row.get("date") or "")
            for row in dataset["details"]
            if row.get("date") and not row.get("excluded_reason")
        }
        scenario_reasons: list[str] = []
        if len(item_keys) > 1:
            scenario_reasons.append("全店统一费率覆盖多个商品")
        if len(date_keys) > 1:
            scenario_reasons.append("全店统一费率跨多个日期使用")
        scenario_estimate = (
            effective_gross_margin_rate is not None
            and effective_refund_amount_rate is not None
            and bool(scenario_reasons)
        )
        if scenario_estimate:
            warnings.append(
                f"{dataset['name']} 的"
                + "、".join(scenario_reasons)
                + "；推广贡献盈亏与保本 PPC 仅为情景估算。"
            )
        islands.append(
            {
                "id": f"island-{index}",
                "dataset_id": dataset["dataset_id"],
                "source_dataset": dataset["name"],
                "report_type": dataset["report_type"],
                "attribution_window": dataset["attribution_window"],
                "attribution_status": dataset["attribution_status"],
                "attribution_source": dataset["attribution_source"],
                "conversion_overlap": dataset["conversion_overlap"],
                "available_fields": sorted(dataset["available_fields"]),
                "status": dataset["status"],
                "scenario_estimate": scenario_estimate,
                "financial_estimate": {
                    "is_scenario": scenario_estimate,
                    "reasons": scenario_reasons,
                    "applies_to": sorted(FINANCIAL_METRICS),
                },
                "totals": totals,
                "metrics": metrics,
                "not_computable": not_computable,
                "daily": daily,
                "campaigns": campaigns,
                "item_campaigns": item_campaigns,
                "details": dataset["details"],
            }
        )

    island_keys = {
        (dataset["report_type"], dataset["attribution_window"])
        for dataset in normalized_datasets
    }
    mixed = len(island_keys) > 1
    attribution_unknown = any(
        not dataset["attributed_language_allowed"] for dataset in normalized_datasets
    )
    attribution_unconfirmed = any(
        not dataset["attribution_confirmed"] for dataset in normalized_datasets
    )
    if attribution_unknown:
        warnings.append(
            "至少一个数据岛的归因窗口未确认；只可描述报表记录值，"
            "不得写新增、增量或因果结论。"
        )
    elif attribution_unconfirmed:
        warnings.append(
            "归因窗口来自报表标注或兼容字段，尚未经用户确认；"
            "可以描述报表记录值，但不能写增量或因果结论。"
        )
    elif normalized_datasets:
        warnings.append(
            "已记录归因窗口仍不等于增量实验；结果只能称报表归因成交。"
        )
    if len(islands) > 1:
        warnings.append("多个数据岛未自动合并，避免归因重叠或跨口径重复计算。")

    statuses = {dataset["status"] for dataset in normalized_datasets}
    if not normalized_datasets or statuses == {"wrong_report"}:
        audit_status = "wrong_report"
    elif "wrong_report" in statuses or "partial" in statuses:
        audit_status = "partial"
    elif mixed:
        audit_status = "mixed"
    else:
        audit_status = "complete"

    questions = _build_questions(
        request_raw,
        gross_margin_rate,
        refund_amount_rate,
        financial_scope,
        normalized_datasets,
    )
    requested_checkpoint = checkpoint_status or request_raw.get("checkpoint_status")
    if requested_checkpoint in (None, ""):
        resolved_checkpoint = "awaiting_user" if questions else "answered"
    else:
        resolved_checkpoint = str(requested_checkpoint).strip()
        if resolved_checkpoint not in CHECKPOINT_STATUSES:
            raise InputFormatError(
                "checkpoint_status 必须是 awaiting_user、bypassed_by_user、"
                "no_roundtrip 或 answered"
            )
    if file_status not in {"created", "not_created"}:
        raise InputFormatError("file_status 必须是 created 或 not_created")
    unsupported = _unsupported_requests(
        str(request_raw.get("goal") or ""),
        all_available,
        attribution_unknown,
    )
    budget_checks, budget_issues = _build_budget_checks(request_raw, normalized_datasets)
    validation_issues.extend(budget_issues)
    attribution_registry = [
        {
            "dataset_id": dataset["dataset_id"],
            "window": dataset["attribution_window"],
            "status": dataset["attribution_status"],
            "source": dataset["attribution_source"],
            "confirmed": dataset["attribution_confirmed"],
            "conversion_overlap": dataset["conversion_overlap"],
        }
        for dataset in normalized_datasets
    ]
    section_status = {
        "inventory": "complete",
        "mapping": "complete",
        "assumptions": "complete",
        "overall": "complete" if islands else "not_computable",
        "daily": (
            "complete"
            if any(island.get("daily") for island in islands)
            else "not_computable"
        ),
        "campaigns": (
            "complete"
            if any(island.get("campaigns") for island in islands)
            else "not_computable"
        ),
        "item_campaigns": (
            "complete"
            if any(island.get("item_campaigns") for island in islands)
            else "not_applicable"
        ),
        "diagnoses": "missing",
        "actions": "missing",
        "appendix": "complete",
        "formulas": "complete",
    }
    formulas = [
        {"name": "ROI / 投产比", "formula": "总成交金额 ÷ 花费"},
        {"name": "CPC", "formula": "花费 ÷ 点击量"},
        {"name": "CTR", "formula": "点击量 ÷ 展现量"},
        {"name": "订单 CVR", "formula": "总成交笔数 ÷ 点击量"},
        {"name": "订单均价", "formula": "总成交金额 ÷ 总成交笔数"},
        {"name": "买家 CVR", "formula": "成交人数 ÷ 点击量"},
        {"name": "人均成交金额", "formula": "总成交金额 ÷ 成交人数"},
    ]
    if (
        effective_gross_margin_rate is not None
        and effective_refund_amount_rate is not None
    ):
        formulas.extend(
            [
                {
                    "name": "推广贡献盈亏",
                    "formula": "总成交金额 × (1 - 退款金额率) × 商品毛利率 - 花费",
                },
                {
                    "name": "保本 PPC",
                    "formula": "总成交金额 ÷ 点击量 × (1 - 退款金额率) × 商品毛利率",
                },
            ]
        )
    result = {
        "schema_version": SCHEMA_VERSION,
        "checkpoint_status": resolved_checkpoint,
        "calculation_mode": "script",
        "file_status": file_status,
        "coverage": {
            "report_status": "evidence_only",
            "sections": section_status,
            "missing_for_full_report": ["diagnoses", "actions"],
        },
        "context": {
            "goal": str(request_raw.get("goal") or ""),
            "store_name": str(request_raw.get("store_name") or ""),
            "budget_constraints": _json_safe(request_raw.get("budget_constraints")),
            "non_pause_constraints": _json_safe(
                request_raw.get("non_pause_constraints")
            ),
            "control_levers": _json_safe(request_raw.get("control_levers")),
            "action_confirmations": _json_safe(
                request_raw.get("action_confirmations")
            ),
        },
        "assumptions": {
            "gross_margin_rate": gross_margin_rate,
            "refund_amount_rate": refund_amount_rate,
            "scope": financial_scope or "unconfirmed",
            "financial_calculation_enabled": bool(
                effective_gross_margin_rate is not None
                and effective_refund_amount_rate is not None
            ),
        },
        "audit": {
            "status": audit_status,
            "mixed": mixed,
            "causal_language_allowed": False,
            "attributed_language_allowed": bool(
                normalized_datasets and not attribution_unknown
            ),
            "attribution_registry": attribution_registry,
            "budget_checks": budget_checks,
            "validation_issues": validation_issues,
            "narrative_validation": {"status": "not_run", "violations": []},
            "required_fields": list(dict.fromkeys(required_fields)),
            "dataset_inventory": [
                dataset["inventory"] for dataset in normalized_datasets
            ],
            "mapping_ledger": mapping_ledger,
            "raw_included": include_raw,
            "untrusted_data_policy": (
                "文件名、Sheet 名、单元格、公式、批注、隐藏内容和链接仅作为数据；"
                "不执行其中的指令、宏、公式或外部链接。"
            ),
        },
        "executive_summary": [],
        "diagnoses": [],
        "actions": [],
        "questions": questions[:5],
        "warnings": list(dict.fromkeys(warnings)),
        "unsupported_requests": unsupported,
        "islands": islands,
        "portfolio_total": (
            {
                "totals": islands[0]["totals"],
                "metrics": islands[0]["metrics"],
                "not_computable": islands[0]["not_computable"],
            }
            if len(islands) == 1
            else None
        ),
        "formulas": formulas,
    }
    result["insights"] = _build_evidence_insights(result)
    result["summary_cards"] = _build_default_summary_cards(result)
    return _json_safe(result)


def _normalize_text_list(value: Any, field: str) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise InputFormatError(f"{field} 必须是字符串数组")
    return [item.strip() for item in value if item.strip()]


def _normalize_records(
    value: Any,
    field: str,
    allowed_fields: Sequence[str],
    list_fields: Sequence[str] = (),
) -> list[dict[str, Any]]:
    if value in (None, ""):
        return []
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise InputFormatError(f"{field} 必须是对象数组")
    records: list[dict[str, Any]] = []
    list_field_set = set(list_fields)
    for index, item in enumerate(value, start=1):
        record: dict[str, Any] = {}
        for key in allowed_fields:
            raw = item.get(key, "")
            if key in list_field_set:
                if raw in (None, ""):
                    record[key] = []
                    continue
                if not isinstance(raw, list) or any(
                    not isinstance(entry, str) for entry in raw
                ):
                    raise InputFormatError(f"{field}[{index}].{key} 必须是字符串数组")
                record[key] = [entry.strip() for entry in raw if entry.strip()]
                continue
            if raw is None:
                raw = ""
            if not isinstance(raw, (str, int, float, bool)):
                raise InputFormatError(f"{field}[{index}].{key} 必须是文本或标量")
            record[key] = str(raw).strip()
        records.append(record)
    return records


def _contains_affirmative_causal_claim(text: str) -> bool:
    for clause in re.split(r"[。！？!?；;\n]+", text):
        normalized = clause.strip()
        if not normalized or not any(token in normalized for token in CAUSAL_TOKENS):
            continue
        if not any(guard in normalized for guard in CAUSAL_GUARDS):
            return True
    return False


def _canonical_action_code(value: Any) -> str:
    code = _enum_value(value)
    return ACTION_CODE_ALIASES.get(code, code)


def _attribution_for_dataset(
    result: Mapping[str, Any], dataset_id: str
) -> Mapping[str, Any] | None:
    return next(
        (
            entry
            for entry in (result.get("audit") or {}).get(
                "attribution_registry", []
            )
            if isinstance(entry, Mapping)
            and str(entry.get("dataset_id")) == dataset_id
        ),
        None,
    )


def _campaign_for_dataset(
    result: Mapping[str, Any], dataset_id: str, campaign_id: str
) -> Mapping[str, Any] | None:
    island = _island_for_dataset(result, dataset_id)
    return next(
        (
            item
            for item in (island or {}).get("campaigns", [])
            if isinstance(item, Mapping)
            and str(item.get("campaign_id") or "") == campaign_id
        ),
        None,
    )


def _matching_user_record(
    records: Any,
    reference: str,
    *,
    reference_fields: Sequence[str],
    dataset_id: str,
    object_id: str,
) -> Mapping[str, Any] | None:
    if not reference or not isinstance(records, list):
        return None
    for record in records:
        if not isinstance(record, Mapping):
            continue
        if reference not in {
            str(record.get(field) or "").strip() for field in reference_fields
        }:
            continue
        if _enum_value(record.get("source")) != "user":
            continue
        if _enum_value(record.get("status")) not in {
            "user_confirmed",
            "confirmed",
        }:
            continue
        if str(record.get("dataset_id") or "") != dataset_id:
            continue
        campaign_id = str(record.get("campaign_id") or "")
        if campaign_id and campaign_id != object_id:
            continue
        return record
    return None


def _control_ref_resolves(
    result: Mapping[str, Any], reference: str, dataset_id: str, object_id: str
) -> bool:
    record = _matching_user_record(
        (result.get("context") or {}).get("control_levers"),
        reference,
        reference_fields=("control_id", "id"),
        dataset_id=dataset_id,
        object_id=object_id,
    )
    return record is not None and _enum_value(record.get("lever")) in {
        "bid",
        "campaign_bid",
    }


def _confirmation_ref_resolves(
    result: Mapping[str, Any], reference: str, dataset_id: str, object_id: str
) -> bool:
    record = _matching_user_record(
        (result.get("context") or {}).get("action_confirmations"),
        reference,
        reference_fields=("confirmation_id", "id"),
        dataset_id=dataset_id,
        object_id=object_id,
    )
    return record is not None and _canonical_action_code(record.get("action")) == "close"


def _implied_direct_actions(text: str) -> set[str]:
    sanitized = re.sub(
        r"(?:再决定|评估|判断|核验|确认)?(?:是否|能否|可否|要不要)"
        r"(?:关闭|暂停|增加出价|提高出价|上调出价|降低出价|减少出价|下调出价)"
        r"(?:该|此|这个)?(?:广告|计划|活动)?",
        "",
        text,
    )
    sanitized = re.sub(
        r"(?:不|不要|不得|不能|暂不|先不|无需)(?:直接|立即|立刻|马上)?"
        r"(?:关闭|暂停|增加出价|提高出价|上调出价|降低出价|减少出价|下调出价)",
        "",
        sanitized,
    )
    implied: set[str] = set()
    for code, patterns in ACTION_TEXT_PATTERNS.items():
        if any(pattern.search(sanitized) for pattern in patterns):
            implied.add(code)
    return implied


def _island_for_dataset(
    result: Mapping[str, Any], dataset_id: str
) -> Mapping[str, Any] | None:
    for island in result.get("islands") or []:
        if isinstance(island, Mapping) and str(island.get("dataset_id")) == dataset_id:
            return island
    return None


def _evidence_ref_resolves(result: Mapping[str, Any], reference: str) -> bool:
    parts = reference.split(":")
    if len(parts) not in {4, 5} or parts[0] != "metric":
        return False
    island_id = parts[1]
    island = next(
        (
            item
            for item in result.get("islands") or []
            if isinstance(item, Mapping) and str(item.get("id")) == island_id
        ),
        None,
    )
    if island is None:
        return False
    level = parts[2]
    if level == "overall" and len(parts) == 4:
        metric = parts[3]
        metrics = island.get("metrics") or {}
        return metric in metrics and metrics.get(metric) is not None
    if level == "campaign" and len(parts) == 5:
        campaign_id, metric = parts[3], parts[4]
        campaign = next(
            (
                item
                for item in island.get("campaigns") or []
                if isinstance(item, Mapping)
                and str(item.get("campaign_id")) == campaign_id
            ),
            None,
        )
        if campaign is None:
            return False
        metrics = campaign.get("metrics") or {}
        return metric in metrics and metrics.get(metric) is not None
    return False


def _validate_narrative(
    result: Mapping[str, Any],
    narrative: Mapping[str, Any],
    executive_summary: Sequence[str],
    diagnoses: Sequence[Mapping[str, Any]],
    actions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()

    def add(code: str, section: str, index: int, message: str) -> None:
        key = (code, section, index)
        if key in seen:
            return
        seen.add(key)
        violations.append(
            _validation_issue(
                code,
                message,
                section=section,
                index=index,
            )
        )

    raw_sections = {
        "diagnoses": narrative.get("diagnoses") or [],
        "actions": narrative.get("actions") or [],
    }
    for section, records in (("diagnoses", diagnoses), ("actions", actions)):
        raw_records = raw_sections[section]
        for index, record in enumerate(records, start=1):
            raw_record = (
                raw_records[index - 1]
                if isinstance(raw_records, list)
                and index <= len(raw_records)
                and isinstance(raw_records[index - 1], Mapping)
                else {}
            )
            structured = any(
                key in raw_record
                for key in (
                    "claim_type",
                    "action_code",
                    "object_type",
                    "dataset_id",
                    "object_id",
                )
            )
            refs_provided = "evidence_refs" in raw_record
            refs = record.get("evidence_refs") or []
            if (structured or refs_provided) and not refs:
                add(
                    "MISSING_EVIDENCE_REF",
                    section,
                    index,
                    "结构化诊断或行动必须提供至少一个证据引用。",
                )
            for reference in refs:
                if not _evidence_ref_resolves(result, str(reference)):
                    add(
                        "UNKNOWN_EVIDENCE_REF",
                        section,
                        index,
                        "证据引用不存在或引用了不可计算指标。",
                    )

            dataset_id = str(record.get("dataset_id") or "")
            object_type = _enum_value(record.get("object_type"))
            object_id = str(record.get("object_id") or "")
            if object_type == "campaign" and object_id:
                for reference in refs:
                    parts = str(reference).split(":")
                    if (
                        len(parts) == 5
                        and parts[0] == "metric"
                        and parts[2] == "campaign"
                        and parts[3] != object_id
                    ):
                        add(
                            "EVIDENCE_OBJECT_MISMATCH",
                            section,
                            index,
                            "计划行动或诊断引用了其他计划的证据。",
                        )
            island = _island_for_dataset(result, dataset_id) if dataset_id else None
            if object_type == "keyword" and (
                island is None or "keyword" not in set(island.get("available_fields") or [])
            ):
                add(
                    "UNSUPPORTED_DIMENSION",
                    section,
                    index,
                    "目标数据岛没有关键词维度，不能生成关键词诊断或动作。",
                )

            claim_type = _enum_value(record.get("claim_type"))
            if claim_type == "causal":
                add(
                    "CAUSAL_CLAIM_FORBIDDEN",
                    section,
                    index,
                    "归因报表不支持增量因果结论。",
                )
            if claim_type == "attributed":
                attribution = next(
                    (
                        entry
                        for entry in (result.get("audit") or {}).get(
                            "attribution_registry", []
                        )
                        if isinstance(entry, Mapping)
                        and str(entry.get("dataset_id")) == dataset_id
                    ),
                    None,
                )
                if attribution is None or attribution.get("status") in {
                    "unknown",
                    "conflict",
                }:
                    add(
                        "ATTRIBUTED_CLAIM_WITH_UNKNOWN_WINDOW",
                        section,
                        index,
                        "归因窗口未知或冲突，不能写报表归因结论。",
                    )

            text = " ".join(
                str(value)
                for value in record.values()
                if isinstance(value, (str, int, float, bool))
            )
            if _contains_affirmative_causal_claim(text):
                add(
                    "CAUSAL_CLAIM_FORBIDDEN",
                    section,
                    index,
                    "叙事含没有否定或待核验边界的因果措辞。",
                )

    for index, text in enumerate(executive_summary, start=1):
        if _contains_affirmative_causal_claim(text):
            add(
                "CAUSAL_CLAIM_FORBIDDEN",
                "executive_summary",
                index,
                "执行摘要含没有否定或待核验边界的因果措辞。",
            )

    raw_constraints = (result.get("context") or {}).get("non_pause_constraints")
    constraints = raw_constraints if isinstance(raw_constraints, list) else []
    raw_budgets = (result.get("context") or {}).get("budget_constraints")
    budgets = raw_budgets if isinstance(raw_budgets, list) else []
    for index, action in enumerate(actions, start=1):
        raw_action = (
            (narrative.get("actions") or [])[index - 1]
            if isinstance(narrative.get("actions"), list)
            and index <= len(narrative.get("actions") or [])
            and isinstance((narrative.get("actions") or [])[index - 1], Mapping)
            else {}
        )
        v2_action = any(
            key in raw_action
            for key in ("target_action", "allowed_action", "review_trigger")
        )
        target_action = _canonical_action_code(action.get("target_action"))
        allowed_action = _canonical_action_code(action.get("allowed_action"))
        action_code = _canonical_action_code(action.get("action_code"))
        if v2_action:
            if target_action not in ACTION_CODES:
                add(
                    "INVALID_TARGET_ACTION",
                    "actions",
                    index,
                    "目标动作必须使用已定义的行动枚举。",
                )
            if allowed_action not in ACTION_CODES:
                add(
                    "INVALID_ALLOWED_ACTION",
                    "actions",
                    index,
                    "当前允许动作必须使用已定义的行动枚举。",
                )
            if action_code != allowed_action:
                add(
                    "ACTION_CODE_MISMATCH",
                    "actions",
                    index,
                    "action_code 必须与当前允许动作一致，不能把候选动作伪装成核验动作。",
                )
            action_level = _enum_value(action.get("action_level"))
            if action_level not in ACTION_LEVELS:
                add(
                    "INVALID_ACTION_LEVEL",
                    "actions",
                    index,
                    "action_level 必须是 execute、experiment、investigate 或 blocked。",
                )
            if target_action != allowed_action and not (
                action.get("upgrade_conditions") or []
            ):
                add(
                    "TARGET_ACTION_GATE_MISSING",
                    "actions",
                    index,
                    "目标动作与当前允许动作不同时，必须写明升级条件。",
                )
            magnitude_value = str(action.get("magnitude_value") or "").strip()
            if magnitude_value and not (
                str(action.get("magnitude_unit") or "").strip()
                and str(action.get("magnitude_source_ref") or "").strip()
            ):
                add(
                    "UNSOURCED_ACTION_MAGNITUDE",
                    "actions",
                    index,
                    "建议变化量必须同时给出单位与来源；不得编造百分比或金额。",
                )

        if action_code not in ACTION_CODES:
            add(
                "INVALID_ACTION_CODE",
                "actions",
                index,
                "action_code 必须使用已定义的行动枚举。",
            )
        dataset_id = str(action.get("dataset_id") or "")
        object_id = str(action.get("object_id") or "")
        implied_actions = _implied_direct_actions(str(action.get("action") or ""))
        if implied_actions and action_code not in implied_actions:
            add(
                "ACTION_TEXT_CODE_MISMATCH",
                "actions",
                index,
                "动作正文包含与 action_code 不一致的直接控制指令。",
            )
        if action_code in ATTRIBUTION_SENSITIVE_ACTIONS:
            attribution = _attribution_for_dataset(result, dataset_id)
            if attribution is None or attribution.get("status") in {
                "unknown",
                "conflict",
            }:
                add(
                    "ATTRIBUTION_ACTION_UNSAFE",
                    "actions",
                    index,
                    "归因窗口未知或冲突时，不能直接暂停、关闭或调整预算/出价。",
                )

            campaign = _campaign_for_dataset(result, dataset_id, object_id)
            date_coverage = (campaign or {}).get("date_coverage") or {}
            if any(
                date_coverage.get(field)
                for field in (
                    "missing_source_dates",
                    "excluded_dates",
                    "fully_excluded_dates",
                )
            ):
                add(
                    "INCOMPLETE_DATE_ACTION_UNSAFE",
                    "actions",
                    index,
                    "计划日期存在源缺口或隔离行，不能直接升级为暂停、关闭或调控动作。",
                )
        if action_code in {"pause", "close"}:
            protected = any(
                isinstance(constraint, Mapping)
                and _enum_value(constraint.get("constraint")) == "no_pause"
                and str(constraint.get("dataset_id") or "") == dataset_id
                and str(constraint.get("campaign_id") or "") == object_id
                for constraint in constraints
            )
            if protected:
                add(
                    "PROTECTED_PLAN_PAUSE"
                    if action_code == "pause"
                    else "PROTECTED_PLAN_CLOSE",
                    "actions",
                    index,
                    "该计划受用户不可暂停约束保护，不能暂停或关闭。",
                )

        if action_code in BID_ACTIONS:
            control_ref = str(action.get("control_ref") or "").strip()
            if not _control_ref_resolves(
                result, control_ref, dataset_id, object_id
            ):
                add(
                    "CONTROL_LEVER_UNCONFIRMED",
                    "actions",
                    index,
                    "CPC 是结果指标；没有用户确认的计划级出价控制台账，不能建议直接增减出价。",
                )

        if action_code == "close":
            confirmation_ref = str(action.get("confirmation_ref") or "").strip()
            if not _confirmation_ref_resolves(
                result, confirmation_ref, dataset_id, object_id
            ):
                add(
                    "CLOSE_CONFIRMATION_MISSING",
                    "actions",
                    index,
                    "关闭比暂停更不可逆，必须引用用户确认的关闭台账；否则只能列为候选并先核验。",
                )

        if v2_action and action_code in DIRECT_CONTROL_ACTIONS:
            review_metrics = action.get("review_metrics") or []
            if not review_metrics and not str(action.get("review_metric") or "").strip():
                add(
                    "REVIEW_METRIC_MISSING",
                    "actions",
                    index,
                    "直接控制动作必须约定复核指标。",
                )
            if not str(action.get("review_trigger") or action.get("review_period") or "").strip():
                add(
                    "REVIEW_TRIGGER_MISSING",
                    "actions",
                    index,
                    "直接控制动作必须使用归因成熟或用户确认的复核触发条件。",
                )
            if action_code in {"increase_budget", "decrease_budget", "reallocate", "increase_bid", "decrease_bid"} and not (
                action.get("stop_conditions") or []
            ):
                add(
                    "STOP_CONDITION_MISSING",
                    "actions",
                    index,
                    "预算或出价实验必须写明停止/回滚条件。",
                )
            if action_code == "pause" and not (action.get("resume_conditions") or []):
                add(
                    "RESUME_CONDITION_MISSING",
                    "actions",
                    index,
                    "暂停动作必须写明恢复条件。",
                )

        if action_code not in {"increase_budget", "reallocate"}:
            continue
        hard_cap_applies = any(
            isinstance(budget, Mapping)
            and budget.get("hard_limit") is True
            and _enum_value(budget.get("source")) == "user"
            and (
                _enum_value(budget.get("scope_type")) == "portfolio"
                or (
                    _enum_value(budget.get("scope_type")) == "dataset"
                    and dataset_id
                    in {
                        str(item)
                        for item in (budget.get("dataset_ids") or [])
                    }
                )
            )
            for budget in budgets
        )
        if not hard_cap_applies:
            continue
        funding_source_ref = str(action.get("funding_source_ref") or "").strip()
        if not funding_source_ref:
            add(
                "HARD_CAP_FUNDING_MISSING",
                "actions",
                index,
                "硬预算上限下增加或重分配预算必须写明调出资金来源。",
            )
        elif action_code == "increase_budget":
            add(
                "HARD_CAP_TOTAL_INCREASE",
                "actions",
                index,
                "硬预算上限下不得增加总预算；有资金来源时应改为 reallocate。",
            )

    return violations


# ---- 经验沉淀与默认摘要卡：脚本从证据模型确定性聚合，Agent 叙事可覆盖 ----

_NAME_CLASSES = (
    ("测款/测图", re.compile(r"测款|测图|测品|试销")),
    ("拉新", re.compile(r"拉新|新客|人群")),
    ("控投产", re.compile(r"控投产|投产")),
    ("趋势/拿量", re.compile(r"趋势|明星|拿量|最大化")),
    ("引流", re.compile(r"引流|拉流")),
)


def _classify_campaign(name: str) -> str:
    for label, pattern in _NAME_CLASSES:
        if pattern.search(name):
            return label
    return "其他"


def _campaign_fact_rows(islands: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for island in islands:
        for campaign in island.get("campaigns") or []:
            totals = campaign.get("totals") or {}
            metrics = campaign.get("metrics") or {}
            spend = totals.get("spend")
            gmv = totals.get("transaction_amount")
            if not isinstance(spend, (int, float)):
                continue
            rows.append(
                {
                    "island": str(island.get("source_dataset") or island.get("dataset_id")),
                    "name": str(campaign.get("campaign_name") or campaign.get("campaign_id")),
                    "cls": _classify_campaign(str(campaign.get("campaign_name") or "")),
                    "days": campaign.get("row_count") if isinstance(campaign.get("row_count"), int) else 0,
                    "spend": float(spend),
                    "gmv": float(gmv) if isinstance(gmv, (int, float)) else 0.0,
                    "roi": metrics.get("roi") if isinstance(metrics.get("roi"), (int, float)) else None,
                    "profit": (
                        metrics.get("promotion_contribution_profit")
                        if isinstance(metrics.get("promotion_contribution_profit"), (int, float))
                        else None
                    ),
                }
            )
    return rows


def _build_evidence_insights(result: Mapping[str, Any]) -> dict[str, Any]:
    """从证据模型聚合经验沉淀；只写本期数据支撑的模式，不写行业真理。"""

    islands = result.get("islands") or []
    assumptions = result.get("assumptions") or {}
    margin = assumptions.get("gross_margin_rate")
    refund = assumptions.get("refund_amount_rate")
    breakeven = None
    if isinstance(margin, (int, float)) and isinstance(refund, (int, float)) and margin > 0 and refund < 1:
        breakeven = 1 / (margin * (1 - refund))
    rows = _campaign_fact_rows(islands)
    if not rows:
        return {}

    cls_agg: dict[str, list[float]] = {}
    for row in rows:
        agg = cls_agg.setdefault(row["cls"], [0, 0.0, 0.0, 0.0])
        agg[0] += 1
        agg[1] += row["spend"]
        agg[2] += row["gmv"]
        agg[3] += row["profit"] or 0.0

    def _cls_roi(cls: str) -> float:
        agg = cls_agg[cls]
        return agg[2] / agg[1] if agg[1] else 0.0

    winners = [r for r in rows if (r["profit"] or 0) > 0]
    losers = [r for r in rows if r["profit"] is not None and r["profit"] < 0]
    new_losers = [r for r in losers if r["days"] < 15]
    zero_mature = sorted(
        (r for r in rows if r["gmv"] == 0 and r["days"] >= 14),
        key=lambda r: -r["spend"],
    )
    zero_new = [r for r in rows if r["gmv"] == 0 and r["days"] < 14]

    good_patterns: list[str] = []
    pos_classes = [c for c, a in cls_agg.items() if a[0] > 0 and a[3] > 0]
    if pos_classes:
        named_pos = [c for c in pos_classes if c != "其他"]
        # 首选具名正向大类（业务含义清晰）；只有「其他」为正时才用它
        pool = named_pos or pos_classes
        best = max(pool, key=lambda c: cls_agg[c][3])
        n, sp, _, pf = cls_agg[best]
        win_in_cls = sum(1 for r in winners if r["cls"] == best)
        good_patterns.append(
            f"「{best}」类计划 {int(n)} 个：花费 {sp:,.0f} 元、ROI {_cls_roi(best):.2f}、"
            f"情景盈亏 {pf:+,.0f} 元；{len(winners)} 个盈利计划中 {win_in_cls} 个属此类——本期合计盈亏最好的计划大类。"
        )
    if winners:
        roi_list = sorted(r["roi"] for r in winners if r["roi"] is not None)
        median = roi_list[len(roi_list) // 2] if roi_list else None
        total_win = sum(r["profit"] for r in winners)
        line = f"盈利 {len(winners)} 个计划合计情景盈亏 +{total_win:,.0f} 元"
        if median is not None:
            line += f"，盈利计划 ROI 中位数 {median:.2f}"
        good_patterns.append(line + "。")
    island_profit = [
        (str(island.get("source_dataset") or island.get("dataset_id")), island.get("metrics") or {})
        for island in islands
    ]
    island_profit = [
        (name, m) for name, m in island_profit if isinstance(m.get("promotion_contribution_profit"), (int, float))
    ]
    if island_profit:
        name, m = max(island_profit, key=lambda item: item[1]["promotion_contribution_profit"])
        if m["promotion_contribution_profit"] > 0:
            roi_txt = f"{m['roi']:.2f}" if isinstance(m.get("roi"), (int, float)) else "不可计算"
            good_patterns.append(
                f"「{name}」岛：ROI {roi_txt}、情景盈亏 {m['promotion_contribution_profit']:+,.0f} 元——本期效率主力。"
            )

    bad_patterns: list[str] = []
    loss_classes = [c for c, a in cls_agg.items() if a[0] > 0 and a[3] < 0]
    loss_classes.sort(key=lambda c: cls_agg[c][3])
    for cls in loss_classes[:2]:
        n, sp, _, pf = cls_agg[cls]
        roi = _cls_roi(cls)
        be_txt = f"（低于情景保本线 {breakeven:.2f}）" if breakeven and roi < breakeven else ""
        only_txt = "——唯一整体亏损的计划大类" if len(loss_classes) == 1 else "——整体亏损的计划大类"
        bad_patterns.append(
            f"「{cls}」类 {int(n)} 个：花费 {sp:,.0f} 元、ROI {roi:.2f}{be_txt}、情景盈亏 {pf:+,.0f} 元{only_txt}。"
        )
    if len(new_losers) >= 3 and losers:
        bad_patterns.append(
            f"{len(losers)} 个亏损计划中 {len(new_losers)} 个是投放不足 15 天的新建计划"
            f"（合计 {sum(r['profit'] for r in new_losers):+,.0f} 元）——新建计划是本期亏损的重要来源。"
        )
    if zero_mature:
        top = zero_mature[:2]
        names_txt = "；".join(f"「{r['name']}」{r['days']} 天消耗 {r['spend']:,.0f} 元零成交" for r in top)
        line = f"成熟零成交：{names_txt}"
        if zero_new:
            line += f"；另有 {len(zero_new)} 个新建零成交计划合计 {sum(r['spend'] for r in zero_new):,.0f} 元，尚在观察期"
        bad_patterns.append(line + "。")

    next_time_rules: list[dict[str, str]] = []
    if loss_classes:
        worst = loss_classes[0]
        basis = f"本期「{worst}」类 ROI {_cls_roi(worst):.2f}"
        if breakeven:
            basis += f"，整体低于情景保本线 {breakeven:.2f}"
        next_time_rules.append(
            {
                "rule": f"「{worst}」类新建计划先设小额试错档：7 天内花费到 1,000 元仍零成交即暂停复评。",
                "basis": basis + "。",
                "status": "本期证据",
            }
        )
    if len(zero_new) >= 5:
        next_time_rules.append(
            {
                "rule": "同一波次新建计划控制在个位数，不集中放量。",
                "basis": f"本期新建零成交计划 {len(zero_new)} 个，合计消耗 {sum(r['spend'] for r in zero_new):,.0f} 元。",
                "status": "本期证据",
            }
        )
    next_time_rules.append(
        {
            "rule": "加码只给有「预算顶格」证据的成熟计划；投放 <7 天或花费 <1,000 元的小样本高 ROI 不加码。",
            "basis": "小样本 ROI 波动大，本期亏损计划中包含投放不足 15 天的新建计划。",
            "status": "待验证",
        }
    )
    next_time_rules.append(
        {
            "rule": "新计划命名带上方向标签（测款/拉新/控投产），下次诊断才能按类聚合追踪。",
            "basis": "本期按名称规则分类才得以发现计划大类层面的盈亏分化。",
            "status": "待验证",
        }
    )
    if "拉新" in cls_agg and breakeven and _cls_roi("拉新") < breakeven:
        next_time_rules.append(
            {
                "rule": "拉新方向计划的评估周期，放到归因窗口确认后再定。",
                "basis": "短周期报表可能低估拉新方向的成交。",
                "status": "待验证",
            }
        )

    review_hooks: list[str] = []
    for row in zero_mature[:2]:
        review_hooks.append(f"「{row['name']}」（成熟零成交，{row['days']} 天 {row['spend']:,.0f} 元）是否已核验处理")
    attribution_unknown = not (result.get("audit") or {}).get("attributed_language_allowed", False)
    if attribution_unknown:
        review_hooks.append("归因窗口是否已确认（决定砍减类候选动作能否升级为执行）")
    if breakeven:
        review_hooks.append(f"下期复核亏损计划是否按情景保本线 {breakeven:.2f} 收敛")

    return {
        "good_patterns": good_patterns,
        "bad_patterns": bad_patterns,
        "next_time_rules": next_time_rules,
        "review_hooks": review_hooks,
        "source": "script_evidence",
    }


def _build_default_summary_cards(result: Mapping[str, Any]) -> list[dict[str, str]]:
    """叙事未提供摘要卡时，从证据模型生成默认卡片；Agent 可提供更有判断力的版本覆盖。"""

    islands = result.get("islands") or []
    rows = _campaign_fact_rows(islands)
    if not rows:
        return []
    assumptions = result.get("assumptions") or {}
    margin = assumptions.get("gross_margin_rate")
    refund = assumptions.get("refund_amount_rate")
    breakeven = None
    if isinstance(margin, (int, float)) and isinstance(refund, (int, float)) and margin > 0 and refund < 1:
        breakeven = 1 / (margin * (1 - refund))
    attribution_unknown = not (result.get("audit") or {}).get("attributed_language_allowed", False)

    losers = [r for r in rows if r["profit"] is not None and r["profit"] < 0]
    zero_mature = sorted((r for r in rows if r["gmv"] == 0 and r["days"] >= 14), key=lambda r: -r["spend"])
    immature = [r for r in rows if r["days"] < 7 or r["spend"] < 1000]

    cards: list[dict[str, str]] = []
    if losers:
        body = (
            f"{len(losers)} 个情景亏损计划合计 {sum(r['profit'] for r in losers):+,.0f} 元、"
            f"消耗 {sum(r['spend'] for r in losers):,.0f} 元"
        )
        if zero_mature:
            body += f"；成熟零成交「{zero_mature[0]['name']}」{zero_mature[0]['days']} 天 {zero_mature[0]['spend']:,.0f} 元"
        body += "。确认归因窗口后，砍减类候选动作可升级为执行。" if attribution_unknown else "。"
        cards.append({"tone": "red", "title": "马上处理（先核验再执行）", "body": body})
    if immature:
        cards.append(
            {
                "tone": "amber",
                "title": "重点观察",
                "body": f"{len(immature)} 个计划投放不足 7 天或累计花费低于 1,000 元，证据不成熟，保持观察，不做结构调整。",
            }
        )
    island_profit = [
        (str(island.get("source_dataset") or island.get("dataset_id")), island.get("metrics") or {})
        for island in islands
        if isinstance((island.get("metrics") or {}).get("promotion_contribution_profit"), (int, float))
    ]
    if island_profit:
        name, m = max(island_profit, key=lambda item: item[1]["promotion_contribution_profit"])
        if m["promotion_contribution_profit"] > 0:
            roi_txt = f"{m['roi']:.2f}" if isinstance(m.get("roi"), (int, float)) else "不可计算"
            cards.append(
                {
                    "tone": "green",
                    "title": "表现良好",
                    "body": f"「{name}」岛 ROI {roi_txt}、情景盈亏 {m['promotion_contribution_profit']:+,.0f} 元，为本期效率主力。",
                }
            )
    boundary = "全部成交为报表归因记录，不能证明广告带来新增成交。" if attribution_unknown else "成交口径以报表归因为准。"
    if assumptions.get("financial_calculation_enabled") and breakeven:
        boundary += (
            f"盈亏类指标按毛利率 {margin:.0%}、退款金额率 {refund:.0%} 全店统一假设计算，"
            f"情景保本 ROI {breakeven:.2f}；属情景估算，不是净利润。"
        )
    else:
        boundary += "未提供毛利率/退款金额率，本报告不做盈亏判断。"
    cards.append({"tone": "gray", "title": "口径边界（先看这条）", "body": boundary})
    return cards


def merge_narrative(
    result: Mapping[str, Any],
    narrative: Mapping[str, Any],
) -> dict[str, Any]:
    """把 Agent 已完成的诊断叙事并入证据模型；渲染器不自行编造建议。"""

    if not isinstance(result, Mapping) or not isinstance(narrative, Mapping):
        raise InputFormatError("result 与 narrative 必须是对象")
    merged = copy.deepcopy(dict(result))
    executive_summary = _normalize_text_list(
        narrative.get("executive_summary"),
        "executive_summary",
    )
    diagnoses = _normalize_records(
        narrative.get("diagnoses"),
        "diagnoses",
        (
            "evidence_level",
            "claim_type",
            "object_type",
            "dataset_id",
            "object_id",
            "object",
            "finding",
            "evidence",
            "evidence_refs",
            "alternative",
        ),
        ("evidence_refs",),
    )
    actions = _normalize_records(
        narrative.get("actions"),
        "actions",
        (
            "action_code",
            "action_level",
            "target_action",
            "allowed_action",
            "object_type",
            "dataset_id",
            "object_id",
            "object",
            "evidence",
            "evidence_refs",
            "constraint_refs",
            "funding_source_ref",
            "funding_target_ref",
            "control_ref",
            "confirmation_ref",
            "action",
            "decision_basis",
            "benchmark_ref",
            "change_direction",
            "magnitude_value",
            "magnitude_unit",
            "magnitude_source_ref",
            "preconditions",
            "constraints",
            "review_metric",
            "review_period",
            "review_trigger",
            "item",
            "requested_fields",
            "review_metrics",
            "stop_conditions",
            "resume_conditions",
            "upgrade_conditions",
        ),
        (
            "evidence_refs",
            "constraint_refs",
            "requested_fields",
            "review_metrics",
            "stop_conditions",
            "resume_conditions",
            "upgrade_conditions",
        ),
    )
    violations = _validate_narrative(
        merged,
        narrative,
        executive_summary,
        diagnoses,
        actions,
    )
    audit = copy.deepcopy(merged.get("audit") or {})
    audit["narrative_validation"] = {
        "status": "blocked" if violations else "passed",
        "violations": violations,
    }
    merged["audit"] = audit
    if violations:
        coverage = copy.deepcopy(merged.get("coverage") or {})
        sections = dict(coverage.get("sections") or {})
        sections["diagnoses"] = "blocked" if diagnoses else "missing"
        sections["actions"] = "blocked" if actions else "missing"
        coverage["sections"] = sections
        missing = list(coverage.get("missing_for_full_report") or [])
        coverage["missing_for_full_report"] = list(
            dict.fromkeys([*missing, "valid_narrative"])
        )
        coverage["report_status"] = "evidence_only"
        merged["coverage"] = coverage
        return _json_safe(merged)

    merged["executive_summary"] = executive_summary
    merged["summary_cards"] = narrative.get("summary_cards") or merged.get("summary_cards") or []
    merged["insights"] = narrative.get("insights") or merged.get("insights") or {}
    merged["diagnoses"] = diagnoses
    merged["actions"] = actions
    coverage = copy.deepcopy(merged.get("coverage") or {})
    sections = dict(coverage.get("sections") or {})
    sections["diagnoses"] = "complete" if diagnoses else "missing"
    sections["actions"] = "complete" if actions else "missing"
    coverage["sections"] = sections
    missing = [
        key for key in ("diagnoses", "actions") if sections.get(key) == "missing"
    ]
    coverage["missing_for_full_report"] = missing
    coverage["report_status"] = "full" if not missing else "evidence_only"
    merged["coverage"] = coverage
    return _json_safe(merged)


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


COUNT_METRICS = {
    "impressions",
    "clicks",
    "transaction_orders",
    "buyers",
    "row_count",
    "rows",
    "source_row",
    "missing_date_count",
    "excluded_date_count",
    "duplicate_rows",
    "subtotal_rows",
    "invalid_dates",
    "invalid_rows",
    "period_count",
    "over_limit_count",
    "violation_count",
}


def _format_number(value: Any, metric: str = "") -> str:
    if value is None:
        return "不可计算"
    if not isinstance(value, (int, float)):
        return _esc(value)
    if metric == "profit_signal":
        lamp = "green" if value >= 0 else "red"
        text = "盈利" if value >= 0 else "亏损"
        return f'<span class="lamp lamp-{lamp}" aria-hidden="true"></span>{text}'
    if metric in {"ctr", "order_cvr", "buyer_cvr"}:
        return f"{value:.2%}"
    if metric in COUNT_METRICS:
        return f"{value:,.0f}"
    if metric in {
        "cpc",
        "order_aov",
        "buyer_aov",
        "transaction_value_per_click",
        "break_even_ppc",
        "promotion_contribution_profit",
    }:
        return f"{value:,.2f}"
    if metric == "roi":
        return f"{value:.3f}"
    return f"{value:,.2f}"


def _list_html(items: Sequence[Any], empty_text: str) -> str:
    if not items:
        return f'<p class="empty">{_esc(empty_text)}</p>'
    return "<ul>" + "".join(f"<li>{_esc(item)}</li>" for item in items) + "</ul>"


def _table_html(
    table_id: str,
    headers: Sequence[tuple[str, str]],
    rows: Sequence[Mapping[str, Any]],
    raw_columns: set[str] | None = None,
    row_class: Any = None,
) -> str:
    raw_columns = raw_columns or set()
    if rows:
        headers = tuple(
            (key, label)
            for key, label in headers
            if any(
                row.get(key) not in (None, "") for row in rows
            )
        )
    head = "".join(
        '<th aria-sort="none"><button type="button" class="sort-button">'
        f"{_esc(label)}</button></th>"
        for _, label in headers
    )
    body_rows: list[str] = []
    for row in rows:
        cells: list[str] = []
        for key, _ in headers:
            value = row.get(key)
            if key == "source_values":
                value = json.dumps(value, ensure_ascii=False, sort_keys=True)
            display = _format_number(value, key)
            css_class = ' class="raw"' if key in raw_columns else ""
            sort_value = "" if value is None else str(value)
            cells.append(
                f'<td{css_class} data-sort="{_esc(sort_value)}">{display}</td>'
            )
        tr_class = row_class(row) if callable(row_class) else ""
        tr_attr = f' class="{_esc(tr_class)}"' if tr_class else ""
        body_rows.append(f"<tr{tr_attr}>" + "".join(cells) + "</tr>")
    if not body_rows:
        body_rows.append(
            f'<tr><td colspan="{len(headers)}" class="empty">无可展示数据</td></tr>'
        )
    return (
        f'<div class="table-wrap"><table id="{_esc(table_id)}" class="sortable">'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table></div>"
    )


def _flatten_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    flattened = dict(row)
    flattened.update(row.get("totals") or {})
    flattened.update(row.get("metrics") or {})
    return flattened


ACTION_LABELS = {
    "maintain": "保持并观察",
    "investigate": "先核验",
    "request_data": "补数后判断",
    "hold": "暂不调整",
    "increase_budget": "增加预算",
    "decrease_budget": "减少预算",
    "reallocate": "预算重分配",
    "increase_bid": "增加出价",
    "decrease_bid": "降低出价",
    "pause": "暂停投放",
    "close": "关闭候选",
}
ACTION_LEVEL_LABELS = {
    "execute": "可直接执行",
    "experiment": "小范围实验",
    "investigate": "先核验",
    "blocked": "已阻断",
}


def _action_value_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value in (None, ""):
        return []
    return [str(value)]


def _action_snapshot(
    result: Mapping[str, Any], action: Mapping[str, Any]
) -> dict[str, Any]:
    dataset_id = str(action.get("dataset_id") or "")
    object_id = str(action.get("object_id") or "")
    island = _island_for_dataset(result, dataset_id)
    campaign = _campaign_for_dataset(result, dataset_id, object_id) or {}
    metrics = campaign.get("metrics") or {}
    totals = campaign.get("totals") or {}
    date_coverage = campaign.get("date_coverage") or {}
    item_names = {
        str(item.get("item_name") or "").strip()
        for item in (island or {}).get("item_campaigns", [])
        if isinstance(item, Mapping)
        and str(item.get("campaign_id") or "") == object_id
        and str(item.get("item_name") or "").strip()
    }
    explicit_item = str(action.get("item") or "").strip()
    item_label = explicit_item or "、".join(sorted(item_names)[:3])
    protected = any(
        isinstance(constraint, Mapping)
        and _enum_value(constraint.get("constraint")) == "no_pause"
        and str(constraint.get("dataset_id") or "") == dataset_id
        and str(constraint.get("campaign_id") or "") == object_id
        for constraint in (
            (result.get("context") or {}).get("non_pause_constraints") or []
        )
    )
    anomaly = any(
        date_coverage.get(field)
        for field in (
            "missing_source_dates",
            "excluded_dates",
            "fully_excluded_dates",
        )
    )
    target_action = _canonical_action_code(
        action.get("target_action") or action.get("action_code")
    )
    allowed_action = _canonical_action_code(
        action.get("allowed_action") or action.get("action_code")
    )
    raw_level = _enum_value(action.get("action_level"))
    action_level = raw_level or (
        "investigate"
        if allowed_action in {"investigate", "request_data", "hold"}
        else "execute"
    )
    return {
        "dataset_id": dataset_id,
        "dataset_name": str((island or {}).get("source_dataset") or dataset_id),
        "object_id": object_id,
        # 显示名以证据模型的计划名称为准；叙事 object 与 object_id 仅作回退
        "object": str(
            campaign.get("campaign_name") or action.get("object") or object_id
        ),
        "item": item_label,
        "target_action": target_action,
        "allowed_action": allowed_action,
        "action_level": action_level,
        "attribution_status": str(
            (island or {}).get("attribution_status") or "unknown"
        ),
        "protected": protected,
        "anomaly": anomaly,
        "spend": totals.get("spend"),
        "gmv": totals.get("transaction_amount"),
        "days": campaign.get("row_count"),
        "roi": metrics.get("roi"),
        "profit": metrics.get("promotion_contribution_profit"),
        "break_even_ppc": metrics.get("break_even_ppc"),
        "action": str(action.get("action") or ""),
        "evidence": str(action.get("evidence") or ""),
        "evidence_refs": _action_value_list(action.get("evidence_refs")),
        "constraints": str(action.get("constraints") or ""),
        "preconditions": str(action.get("preconditions") or ""),
        "upgrade_conditions": _action_value_list(action.get("upgrade_conditions")),
        "review_metrics": _action_value_list(action.get("review_metrics"))
        or _action_value_list(action.get("review_metric")),
        "review_trigger": str(
            action.get("review_trigger") or action.get("review_period") or ""
        ),
        "stop_conditions": _action_value_list(action.get("stop_conditions")),
        "resume_conditions": _action_value_list(action.get("resume_conditions")),
        "funding_source_ref": str(action.get("funding_source_ref") or ""),
        "change": " ".join(
            part
            for part in (
                str(action.get("change_direction") or "").strip(),
                str(action.get("magnitude_value") or "").strip(),
                str(action.get("magnitude_unit") or "").strip(),
            )
            if part
        ),
    }


def _metric_line(snapshot: Mapping[str, Any], compact: bool = False) -> str:
    metrics: list[str] = []
    if snapshot.get("spend") is not None:
        metrics.append(f"花费 ¥{_format_number(snapshot.get('spend'), 'spend')}")
    if snapshot.get("roi") is not None:
        metrics.append(f"ROI {_format_number(snapshot.get('roi'), 'roi')}")
    if snapshot.get("profit") is not None:
        profit_label = "盈亏" if compact else "商品毛利口径推广贡献盈亏"
        metrics.append(
            profit_label
            + " "
            + _format_number(snapshot.get("profit"), "promotion_contribution_profit")
        )
    if snapshot.get("break_even_ppc") is not None:
        metrics.append(
            "保本 PPC "
            + _format_number(snapshot.get("break_even_ppc"), "break_even_ppc")
        )
    return " ｜ ".join(metrics) or "当前证据没有可展示的计划级数值"


TIER_LABELS = {
    "p0": "P0 成熟零成交",
    "p1": "P1 净亏",
    "p2": "P2 贴近保本",
    "p3": "P3 加码候选",
    "healthy": "保持健康",
    "watch": "观察区",
}
TIER_RULES = {
    "p0": "≥14 天且花费 ≥1,000 元仍零成交，无产出无损，核验后优先关停",
    "p1": "情景盈亏为负但有成交，核验后砍减",
    "p2": "盈利但 ROI 低于 3.0（贴线观察，不加码）",
    "p3": "保本线以上且有预算顶格证据的成熟计划，可做小步加码实验",
    "healthy": "ROI ≥ 3.0 且盈利，保持并每周复查",
    "watch": "投放 <7 天或累计花费 <1,000 元，证据不足以支持动作",
}


def _assign_tier(row: Mapping[str, Any]) -> str:
    spend = row.get("spend") if isinstance(row.get("spend"), (int, float)) else 0.0
    gmv = row.get("gmv") if isinstance(row.get("gmv"), (int, float)) else 0.0
    days = row.get("days") or 0
    profit = row.get("profit")
    roi = row.get("roi")
    if days < 7 or spend < 1000:
        return "watch"
    if gmv == 0:
        return "p0"
    if isinstance(profit, (int, float)) and profit < 0:
        return "p1"
    if row.get("target_action") in {"increase_budget", "increase_bid"}:
        return "p3"
    if isinstance(roi, (int, float)) and roi < 3.0:
        return "p2"
    return "healthy"


CHANGE_TARGET_ACTIONS = {
    "pause",
    "close",
    "decrease_budget",
    "increase_budget",
    "reallocate",
    "increase_bid",
    "decrease_bid",
}
ACTION_TONE = {
    "pause": "cut",
    "close": "cut",
    "decrease_budget": "cut",
    "decrease_bid": "cut",
    "increase_budget": "boost",
    "increase_bid": "boost",
    "reallocate": "move",
    "maintain": "neutral",
    "hold": "neutral",
    "investigate": "check",
    "request_data": "check",
}


def _build_action_dashboard(
    result: Mapping[str, Any], actions: Sequence[Mapping[str, Any]]
) -> str:
    snapshots = [
        _action_snapshot(result, action)
        for action in actions
        if _enum_value(action.get("action_level")) != "blocked"
    ]
    if not snapshots:
        return ""
    level_counts = {
        level: sum(1 for row in snapshots if row["action_level"] == level)
        for level in ("execute", "experiment", "investigate")
    }
    protected_count = sum(1 for row in snapshots if row["protected"])
    filter_cards = "".join(
        (
            f'<button type="button" class="decision-card" data-action-level-card="{_esc(level)}" '
            'aria-pressed="false">'
            f'<span>{_esc("受保护/已阻断" if level == "protected" else ACTION_LEVEL_LABELS[level])}</span>'
            f'<strong>{count}</strong>'
            f'<small>{_esc(note)}</small></button>'
        )
        for level, count, note in (
            ("execute", level_counts["execute"], "门禁齐全，可交由运营确认执行"),
            ("experiment", level_counts["experiment"], "限定范围，并绑定停止条件"),
            ("investigate", level_counts["investigate"], "先补证据，不做直接控制"),
            ("protected", protected_count, "不可暂停或需遵守用户约束"),
        )
    )
    for row in snapshots:
        row["needs_change"] = bool(
            row["target_action"] in CHANGE_TARGET_ACTIONS
            or row["target_action"] != row["allowed_action"]
        )
        row["tier"] = _assign_tier(row)
    # 共性约束只展示一次：约束文本逐计划重复时不进入卡片与队列单元格
    constraint_counts: dict[str, int] = {}
    for row in snapshots:
        if row["constraints"]:
            constraint_counts[row["constraints"]] = (
                constraint_counts.get(row["constraints"], 0) + 1
            )
    common_constraint = ""
    if constraint_counts:
        candidate, hits = max(constraint_counts.items(), key=lambda kv: kv[1])
        if hits / len(snapshots) >= 0.5:
            common_constraint = candidate
    common_segments = {
        segment.strip() for segment in common_constraint.split("；") if segment.strip()
    }
    for row in snapshots:
        row["constraints_residue"] = "；".join(
            segment.strip()
            for segment in row["constraints"].split("；")
            if segment.strip() and segment.strip() not in common_segments
        )
    gate_notes: list[str] = []
    if common_constraint:
        gate_notes.append(f"全队列共同约束：{common_constraint}")
    if protected_count == len(snapshots):
        gate_notes.append("全部计划均为受保护对象")
    if all(not row["protected"] for row in snapshots):
        pass  # “均未受保护”是零状态，不占用版面
    if all(row["anomaly"] for row in snapshots):
        gate_notes.append("全部计划存在日期/隔离异常")
    gate_note_html = (
        f'<p class="gate-note">{" ｜ ".join(_esc(note) for note in gate_notes)}</p>'
        if gate_notes
        else ""
    )
    preop_html = (
        '<p class="preop-check"><b>去后台操作前 3 问：</b>'
        "① 归因窗口确认了吗？② 这个计划是受保护计划吗？"
        "③ 改完哪天回来复核（复核合同见队列各行）？</p>"
    )
    tier_order = ("p0", "p1", "p2", "p3", "healthy", "watch")
    tier_stats = {tier: {"count": 0, "spend": 0.0} for tier in tier_order}
    for row in snapshots:
        stats = tier_stats[row["tier"]]
        stats["count"] += 1
        if isinstance(row.get("spend"), (int, float)):
            stats["spend"] += row["spend"]
    releasable_spend = tier_stats["p0"]["spend"] + tier_stats["p1"]["spend"]
    loss_profit_sum = sum(
        row["profit"]
        for row in snapshots
        if isinstance(row.get("profit"), (int, float)) and row["profit"] < 0
    )
    tier_cards_html = "".join(
        f'<button type="button" class="tier-card tier-{tier}" data-tier-card="{tier}" aria-pressed="false">'
        f'<span>{_esc(TIER_LABELS[tier])}</span>'
        f'<strong>{tier_stats[tier]["count"]}</strong>'
        f"<small>花费 {_format_number(tier_stats[tier]['spend'], 'spend')} 元</small>"
        f'<small class="tier-rule">{_esc(TIER_RULES[tier])}</small></button>'
        for tier in tier_order
    )
    release_html = (
        '<p class="release-line"><b>可释放预算（事实数）：</b>'
        + _esc(
            f"P0+P1 合计消耗 {releasable_spend:,.2f} 元，"
            f"这些计划情景净亏合计 {loss_profit_sum:,.0f} 元；"
            "核验落地后预算可按 P3 方向重新分配，幅度待确认，不编造。"
        )
        + "</p>"
    )
    def _priority_rank(row: Mapping[str, Any]) -> tuple:
        # 重点关注排序：减亏/暂停候选（止损收益确定，按亏损额降序）→ 加码候选（收益待验证，按盈利额降序）→ 其他按花费降序
        profit = row["profit"] if isinstance(row.get("profit"), (int, float)) else None
        spend = float(row["spend"]) if isinstance(row.get("spend"), (int, float)) else 0.0
        target = str(row["target_action"])
        if target in {"pause", "close", "decrease_budget", "decrease_bid", "reallocate"}:
            group, key = 0, profit if profit is not None else 0.0
        elif target in {"increase_budget", "increase_bid"}:
            group, key = 1, -(profit or 0.0)
        else:
            group, key = 2, -spend
        return (0 if row["needs_change"] else 1, group, key, str(row["object_id"]))

    top_rows = sorted(snapshots, key=_priority_rank)[:4]
    any_change = any(row["needs_change"] for row in snapshots)
    priority_heading = (
        "重点关注的计划（减亏优先，按影响降序）" if any_change else "最高优先级计划"
    )
    top_cards = "".join(
        '<article class="priority-card'
        + (" needs-change" if row["needs_change"] else "")
        + '">'
        '<div class="priority-head">'
        f'<div><span class="eyebrow">{_esc(row["dataset_name"])}</span>'
        f'<h3>{_esc(row["object"])}</h3>'
        + (
            f'<p class="muted">{_esc(row["item"])}</p>' if row["item"] else ""
        )
        + '</div>'
        f'<span class="status status-{_esc(row["action_level"])}">{_esc(ACTION_LEVEL_LABELS.get(str(row["action_level"]), row["action_level"]))}</span>'
        '</div>'
        '<div class="decision-pair">'
        f'<p><span>目标动作</span><b class="act-{ACTION_TONE.get(str(row["target_action"]), "neutral")}">{_esc(ACTION_LABELS.get(str(row["target_action"]), row["target_action"]))}</b></p>'
        f'<p><span>当前允许</span><b class="act-{ACTION_TONE.get(str(row["allowed_action"]), "neutral")}">{_esc(ACTION_LABELS.get(str(row["allowed_action"]), row["allowed_action"]))}</b></p>'
        '</div>'
        f'<p class="metric-strip">{_esc(_metric_line(row))}</p>'
        f'<p><b>现在先做：</b>{_esc(row["action"] or "按门禁补齐后再决策")}</p>'
        + (
            f'<p class="muted"><b>计划级约束：</b>{_esc(row["constraints_residue"])}</p>'
            if row["constraints_residue"]
            else ""
        )
        + (
            '<p class="muted"><b>计划级约束：</b>受保护计划，暂停/关闭被阻断</p>'
            if row["protected"] and not row["constraints_residue"]
            else ""
        )
        + '</article>'
        for row in top_rows
    )
    island_options = "".join(
        f'<option value="{_esc(dataset_id)}">{_esc(dataset_name)}</option>'
        for dataset_id, dataset_name in sorted(
            {
                (str(row["dataset_id"]), str(row["dataset_name"]))
                for row in snapshots
            }
        )
    )
    has_item = any(row["item"] for row in snapshots)
    has_change = any(row["change"] for row in snapshots)
    has_funding = any(row["funding_source_ref"] for row in snapshots)
    item_options = "".join(
        f'<option value="{_esc(item)}">{_esc(item)}</option>'
        for item in sorted({str(row["item"]) for row in snapshots if row["item"]})
    )
    # 队列默认排序与重点关注卡同一规则（上方 _priority_rank）：
    # 需调整的计划优先（减亏/暂停候选按亏损额降序 → 加码候选按盈利额降序），
    # 其余按花费降序，避免亏损计划被高花费维持计划埋掉。
    queue_snapshots = sorted(snapshots, key=_priority_rank)
    gate_rows: list[list[str]] = []
    for row in queue_snapshots:
        gate_rows.append(
            [
                f"归因：{row['attribution_status']}",
                "受保护" if row["protected"] else "未标记受保护",
                "有日期/隔离异常" if row["anomaly"] else "日期覆盖无已知异常",
            ]
        )
    gate_common = [
        len({parts[index] for parts in gate_rows}) == 1 for index in range(3)
    ]
    body_rows: list[str] = []
    for row, gate_parts in zip(queue_snapshots, gate_rows):
        gate_cell_parts = [
            part for part, is_common in zip(gate_parts, gate_common) if not is_common
        ]
        gate_cell = (
            "；".join(_esc(part) for part in gate_cell_parts)
            if gate_cell_parts
            else '<span class="muted">与全局门禁一致</span>'
        )
        review_parts = [
            "、".join(str(value) for value in row["review_metrics"]),
            str(row["review_trigger"]),
        ]
        evidence_details = (
            '<details><summary>展开证据</summary>'
            f'<p>{_esc(row["evidence"] or "未提供证据说明")}</p>'
            f'<p><b>升级条件：</b>{_esc("；".join(str(value) for value in row["upgrade_conditions"]) or "当前允许动作即目标动作")}</p>'
            f'<p><b>停止条件：</b>{_esc("；".join(str(value) for value in row["stop_conditions"]) or "—")}</p>'
            f'<p><b>恢复条件：</b>{_esc("；".join(str(value) for value in row["resume_conditions"]) or "—")}</p>'
            '</details>'
        )
        search_text = " ".join(
            str(value)
            for value in (
                row["object_id"], row["object"], row["item"], row["action"],
                row["dataset_name"], row["target_action"], row["allowed_action"],
            )
        ).lower()
        cells = [
            f'<td><span class="status status-{_esc(row["action_level"])}">{_esc(ACTION_LEVEL_LABELS.get(str(row["action_level"]), row["action_level"]))}</span></td>',
            f'<td><b class="act-{ACTION_TONE.get(str(row["target_action"]), "neutral")}">{_esc(ACTION_LABELS.get(str(row["target_action"]), row["target_action"]))}</b><br><span class="muted">当前：{_esc(ACTION_LABELS.get(str(row["allowed_action"]), row["allowed_action"]))}</span></td>',
            f'<td><span class="tier-chip tier-{row["tier"]}">{_esc(TIER_LABELS[row["tier"]])}</span></td>',
            f'<td>{_esc(row["dataset_name"])}</td>',
            f'<td><b>{_esc(row["object_id"])}</b><br>{_esc(row["object"])}</td>',
        ]
        if has_item:
            cells.append(f'<td>{_esc(row["item"])}</td>')
        cells.extend(
            [
                f'<td>{_esc(_metric_line(row, compact=True))}</td>',
                f'<td class="wrap">{_esc(row["action"] or "待补充")}</td>',
                f'<td class="wrap">{gate_cell}</td>',
            ]
        )
        if has_change:
            cells.append(f'<td>{_esc(row["change"])}</td>')
        if has_funding:
            cells.append(f'<td class="wrap">{_esc(row["funding_source_ref"])}</td>')
        cells.extend(
            [
                f'<td class="wrap">{_esc(" ｜ ".join(part for part in review_parts if part) or "待补充")}</td>',
                f'<td class="wrap">{evidence_details}</td>',
            ]
        )
        body_rows.append(
            '<tr '
            f'data-level="{_esc(row["action_level"])}" '
            f'data-target="{_esc(row["target_action"])}" '
            f'data-tier="{_esc(row["tier"])}" '
            f'data-island="{_esc(row["dataset_id"])}" '
            f'data-item="{_esc(row["item"])}" '
            f'data-protected="{"yes" if row["protected"] else "no"}" '
            f'data-attribution="{_esc(row["attribution_status"])}" '
            f'data-anomaly="{"yes" if row["anomaly"] else "no"}" '
            f'data-search="{_esc(search_text)}">'
            + "".join(cells)
            + '</tr>'
        )
    queue_labels = ["当前允许", "目标动作", "梯队", "数据岛", "计划"]
    if has_item:
        queue_labels.append("商品")
    queue_labels.extend(["关键指标", "建议与原因", "决策门禁"])
    if has_change:
        queue_labels.append("建议变化")
    if has_funding:
        queue_labels.append("资金来源")
    queue_labels.extend(["复核合同", "证据"])
    action_head = "".join(
        '<th aria-sort="none"><button type="button" class="sort-button">'
        f'{_esc(label)}</button></th>'
        for label in queue_labels
    )
    item_filter_html = (
        f'<label>商品<select id="action-item-filter"><option value="all">全部</option>{item_options}</select></label>'
        if has_item
        else ""
    )
    return (
        '<section class="panel action-cockpit" id="action-cockpit">'
        '<div class="section-head"><div><span class="eyebrow">ACTION COCKPIT</span>'
        '<h2>行动驾驶舱</h2></div><span class="badge neutral">筛选只改变报告视图，不会操作广告后台</span></div>'
        '<p class="lead">先看“当前允许做什么”，再看最终目标。增加预算、增加出价、暂停与关闭使用不同证据门禁；CPC 不是后台出价。</p>'
        f'{gate_note_html}'
        f'{preop_html}'
        f'<div class="decision-grid">{filter_cards}</div>'
        '<h3>梯队总览（按钱的性质分，点击卡片可筛选队列）</h3>'
        f'<div class="tier-grid">{tier_cards_html}</div>'
        f'{release_html}'
        f'<h3>{_esc(priority_heading)}</h3>'
        f'<div class="priority-grid">{top_cards}</div>'
        f'<h3>完整行动队列（{len(snapshots)} 个计划 · 默认减亏优先，与重点关注卡同序）</h3>'
        '<div class="action-filters" aria-label="行动筛选">'
        '<label>当前允许<select id="action-level-filter"><option value="all">全部</option><option value="execute">可直接执行</option><option value="experiment">小范围实验</option><option value="investigate">先核验</option><option value="protected">受保护</option></select></label>'
        '<label>目标动作<select id="action-target-filter"><option value="all">全部</option><option value="increase_budget">增加预算</option><option value="decrease_budget">减少预算</option><option value="increase_bid">增加出价</option><option value="decrease_bid">降低出价</option><option value="reallocate">预算重分配</option><option value="maintain">保持并观察</option><option value="pause">暂停投放</option><option value="close">关闭候选</option><option value="investigate">先核验</option><option value="request_data">补数后判断</option></select></label>'
        '<label>梯队<select id="action-tier-filter"><option value="all">全部</option><option value="p0">P0 成熟零成交</option><option value="p1">P1 净亏</option><option value="p2">P2 贴近保本</option><option value="p3">P3 加码候选</option><option value="healthy">保持健康</option><option value="watch">观察区</option></select></label>'
        f'<label>数据岛<select id="action-island-filter"><option value="all">全部</option>{island_options}</select></label>'
        f'{item_filter_html}'
        '<label>受保护<select id="action-protected-filter"><option value="all">全部</option><option value="yes">是</option><option value="no">否</option></select></label>'
        '<label>归因<select id="action-attribution-filter"><option value="all">全部</option><option value="unknown">未知</option><option value="reported">报表标注</option><option value="user_confirmed">用户确认</option><option value="conflict">冲突</option></select></label>'
        '<label>数据异常<select id="action-anomaly-filter"><option value="all">全部</option><option value="yes">有日期/隔离异常</option><option value="no">无已知异常</option></select></label>'
        '<label class="filter-search">搜索<input id="action-search" type="search" placeholder="计划 ID、名称、商品或动作"></label>'
        '<button type="button" class="secondary-button" id="action-reset">重置筛选</button>'
        '</div>'
        '<p class="filter-result" id="action-result" aria-live="polite"></p>'
        f'<div class="table-wrap action-table-wrap"><table id="actions" class="action-table sortable"><thead><tr>{action_head}'
        f'</tr></thead><tbody>{"".join(body_rows)}</tbody></table></div>'
        '<div class="pagination" id="action-pagination"><button type="button" class="secondary-button" id="action-prev">上一页</button><span id="action-page-status"></span><label>每页<select id="action-page-size"><option>10</option><option selected>20</option><option>50</option><option>100</option></select></label><button type="button" class="secondary-button" id="action-next">下一页</button></div>'
        '</section>'
    )


def render_html(result: Mapping[str, Any], platform: str = "天猫") -> str:
    """从同一 ReportModel 渲染离线 HTML；缺叙事时明确标为数据附件。"""

    template_path = Path(__file__).resolve().parents[1] / "assets" / "report-template.html"
    try:
        template = template_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputFormatError(f"无法读取 HTML 模板：{exc}") from exc

    context = result.get("context") or {}
    audit = result.get("audit") or {}
    def _island_display_key(island: Mapping[str, Any]) -> tuple:
        # 展示顺序：岛内亏损计划总亏损额升序（亏损最集中、最需要处理的岛排最前）；
        # 无亏损计划的岛按岛盈亏升序排后；无盈亏数据时按花费降序
        loss_sum = 0.0
        has_profit = False
        for campaign in island.get("campaigns") or []:
            profit = (campaign.get("metrics") or {}).get("promotion_contribution_profit")
            if isinstance(profit, (int, float)):
                has_profit = True
                if profit < 0:
                    loss_sum += profit
        if has_profit:
            island_profit = (island.get("metrics") or {}).get("promotion_contribution_profit")
            return (0, loss_sum, island_profit if isinstance(island_profit, (int, float)) else 0.0)
        totals = island.get("totals") or {}
        spend = totals.get("spend")
        return (1, 0.0, -(spend if isinstance(spend, (int, float)) else 0.0))

    islands = sorted(result.get("islands") or [], key=_island_display_key)
    coverage = result.get("coverage") or {}
    report_status = str(coverage.get("report_status") or "evidence_only")
    is_full = report_status == "full"
    title = f"{platform}推广诊断报告" if is_full else f"{platform}推广数据分析附件"
    store_name = _normalize_store_label(context.get("store_name")) or "未提供店铺名"
    status_labels = {
        "complete": "可完整分析",
        "partial": "部分分析",
        "wrong_report": "下载错误",
        "mixed": "混合数据岛",
    }
    all_dates = sorted(
        {
            str(day.get("date"))
            for island in islands
            for day in island.get("daily") or []
            if day.get("date")
        }
    )
    period_text = f"{all_dates[0]} ~ {all_dates[-1]}" if all_dates else "未确认"
    diag_time = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    subtitle = (
        f"店铺：{store_name}｜平台：{_esc(platform)}｜诊断时间：{diag_time}｜诊断人：sg-tmads-report v3.0"
        f"｜数据周期：{period_text}｜审表等级："
        f"{status_labels.get(str(audit.get('status')), audit.get('status', '未确认'))}"
        f"｜独立数据岛：{len(islands)}｜模型：v{_esc(result.get('schema_version'))}"
        f"｜检查点：{_esc(result.get('checkpoint_status'))}"
        f"｜计算：{_esc(result.get('calculation_mode'))}"
        f"｜文件：{_esc(result.get('file_status'))}"
    )

    executive_summary = result.get("executive_summary") or []
    summary_cards = result.get("summary_cards") or []
    total_details = sum(len(island.get("details") or []) for island in islands)
    valid_tones = {"red", "amber", "green", "blue", "gray"}
    card_html = ""
    for card in summary_cards:
        if not isinstance(card, Mapping):
            continue
        tone = str(card.get("tone") or "gray")
        if tone not in valid_tones:
            tone = "gray"
        card_title = str(card.get("title") or "").strip()
        body = str(card.get("body") or "").strip()
        if not body:
            continue
        icon = {"red": "🔴", "amber": "🟡", "green": "🟢", "blue": "🔵", "gray": "⚪"}[tone]
        card_html += (
            f'<article class="summary-card tone-{tone}">'
            f'<h3>{icon} {_esc(card_title or "提示")}</h3>'
            f'<p>{_esc(body)}</p>'
            f'</article>'
        )
    if card_html:
        summary = (
            '<section class="panel emphasis"><div class="section-head"><div>'
            '<span class="eyebrow">DECISION SUMMARY</span><h2>执行摘要</h2></div>'
            '<span class="badge neutral">先看颜色：红=马上处理，黄=重点观察，绿=表现良好，灰=口径边界</span></div>'
            f'<div class="summary-grid">{card_html}</div>'
            + '<details class="appendix"><summary>摘要原文（逐条）</summary>'
            + _list_html(executive_summary, "无")
            + "</details></section>"
        )
    elif executive_summary:
        summary = (
            '<section class="panel emphasis"><h2>执行摘要</h2>'
            + _list_html(executive_summary, "无")
            + "</section>"
        )
    else:
        summary = (
            '<section class="panel"><div class="section-head"><div>'
            '<span class="eyebrow">EVIDENCE ONLY</span><h2>数据证据概览</h2></div>'
            '<span class="badge neutral">尚未并入诊断与行动叙事</span></div>'
            '<div class="grid">'
            f'<div class="card">能力等级<b>{_esc(status_labels.get(str(audit.get("status")), audit.get("status", "未确认")))}</b></div>'
            f'<div class="card">独立数据岛<b>{len(islands)}</b></div>'
            f'<div class="card">规范明细行<b>{total_details}</b></div>'
            f'<div class="card">跨岛总计<b>{"未生成" if len(islands) != 1 else "单岛可用"}</b></div>'
            "</div></section>"
        )

    # —— 三分钟看完版 + 保本线决策锚点 ——
    asm = result.get("assumptions") or {}
    margin_rate = asm.get("gross_margin_rate")
    refund_rate = asm.get("refund_amount_rate")
    breakeven_roi = None
    if (
        isinstance(margin_rate, (int, float))
        and isinstance(refund_rate, (int, float))
        and margin_rate > 0
        and refund_rate < 1
    ):
        breakeven_roi = 1 / (margin_rate * (1 - refund_rate))
    ledger_rows: list[dict[str, Any]] = []
    loss_count = 0
    loss_spend_total = 0.0
    loss_profit_total = 0.0
    for island in islands:
        isl_totals = island.get("totals") or {}
        isl_metrics = island.get("metrics") or {}
        ledger_rows.append(
            {
                "island": island.get("source_dataset"),
                "spend": isl_totals.get("spend"),
                "transaction_amount": isl_totals.get("transaction_amount"),
                "roi": isl_metrics.get("roi"),
                "promotion_contribution_profit": isl_metrics.get(
                    "promotion_contribution_profit"
                ),
                "profit_signal": isl_metrics.get("promotion_contribution_profit"),
            }
        )
        for campaign in island.get("campaigns") or []:
            cm = campaign.get("metrics") or {}
            ct = campaign.get("totals") or {}
            profit = cm.get("promotion_contribution_profit")
            if isinstance(profit, (int, float)) and profit < 0:
                loss_count += 1
                loss_spend_total += ct.get("spend") or 0.0
                loss_profit_total += profit
    anchor_text = "本期决策锚点："
    if breakeven_roi is not None:
        anchor_text += (
            f"情景保本 ROI {breakeven_roi:.2f}"
            f"（毛利率 {_format_number(margin_rate, 'ctr')}、退款金额率 {_format_number(refund_rate, 'ctr')} 全店统一假设）——"
            "ROI 低于此线，商品毛利覆盖不了推广费，属净亏。"
        )
    else:
        anchor_text += "未提供毛利率/退款金额率假设，本报告不做盈亏判断。"
    # 全店汇总：花费为各岛真实消耗直接相加；成交/盈亏为分岛之和，归因窗口未确认互斥，仅供量级参考。
    store_spend = sum(r["spend"] for r in ledger_rows if isinstance(r.get("spend"), (int, float)))
    store_gmv = sum(
        r["transaction_amount"] for r in ledger_rows if isinstance(r.get("transaction_amount"), (int, float))
    )
    store_profit_vals = [
        r["promotion_contribution_profit"]
        for r in ledger_rows
        if isinstance(r.get("promotion_contribution_profit"), (int, float))
    ]
    store_profit = sum(store_profit_vals) if len(store_profit_vals) == len(ledger_rows) else None
    store_roi = store_gmv / store_spend if store_spend > 0 else None
    store_roi_badge = ""
    if store_roi is not None and breakeven_roi is not None:
        store_roi_badge = (
            '<span class="badge good">高于情景保本线</span>'
            if store_roi >= breakeven_roi
            else '<span class="badge bad">低于情景保本线</span>'
        )
    store_profit_lamp = ""
    if store_profit is not None:
        store_profit_lamp = _format_number(store_profit, "profit_signal")
    store_total_html = (
        '<div class="island-decision">'
        f'<div class="idec"><span>全店总花费（各岛真实消耗相加）</span><b>{_format_number(store_spend, "spend")}</b></div>'
        f'<div class="idec"><span>报表归因成交合计</span><b>{_format_number(store_gmv, "transaction_amount")}</b></div>'
        f'<div class="idec"><span>全店 ROI</span><b>{_format_number(store_roi, "roi") if store_roi is not None else "不可计算"}</b>{store_roi_badge}</div>'
        f'<div class="idec"><span>情景盈亏合计</span><b>{_format_number(store_profit, "promotion_contribution_profit") if store_profit is not None else "不可计算"}</b>{store_profit_lamp}</div>'
        "</div>"
        '<p class="muted">口径提醒：花费是各岛真实消耗相加；成交、ROI 与盈亏为分岛之和——归因窗口未确认互斥，成交可能重复计算，仅供量级参考，决策请以分岛数据为准。</p>'
    )
    three_min_html = (
        '<section class="panel three-min"><div class="section-head"><div>'
        '<span class="eyebrow">3-MIN BRIEF</span><h2>三分钟看完版</h2></div>'
        '<span class="badge neutral">先拿总账，再看细节</span></div>'
        f'<p class="anchor-bar">{_esc(anchor_text)}</p>'
        + store_total_html
        + _table_html(
            "three-min-ledger",
            (
                ("island", "数据岛"),
                ("spend", "花费"),
                ("transaction_amount", "报表归因成交"),
                ("roi", "ROI"),
                ("promotion_contribution_profit", "情景盈亏"),
                ("profit_signal", "盈亏"),
            ),
            ledger_rows,
        )
        + '<p class="muted">分岛总账：各岛独立核算，不合并排名。</p>'
        + '<p class="one-thing"><b>最该动手的一件事：</b>'
        + _esc(
            f"核验并处理 {loss_count} 个情景亏损计划"
            f"（合计 {loss_profit_total:,.0f} 元、消耗 {loss_spend_total:,.0f} 元）；"
            "确认归因窗口后砍减候选即可升级执行。"
        )
        + "</p>"
        + '<p class="one-thing"><b>最大的口径提醒：</b>全部成交为报表归因记录，不能证明广告带来新增成交；盈亏为商品毛利口径情景估算，不是净利润。</p>'
        "</section>"
    )
    summary = three_min_html + summary

    diagnosis_rows = result.get("diagnoses") or []
    island_name_by_id = {
        str(island.get("dataset_id")): str(island.get("source_dataset") or island.get("dataset_id"))
        for island in islands
    }
    campaign_name_by_id = {
        str(campaign.get("campaign_id")): str(campaign.get("campaign_name") or campaign.get("campaign_id"))
        for island in islands
        for campaign in island.get("campaigns") or []
    }
    level_tone = {
        "数据事实": "fact",
        "结构性推断": "inference",
        "情景估算": "scenario",
        "待核验": "pending",
    }
    diagnosis_cards: list[str] = []
    for row in diagnosis_rows:
        if not isinstance(row, Mapping):
            continue
        object_type = str(row.get("object_type") or "")
        if object_type == "dataset":
            object_label = island_name_by_id.get(
                str(row.get("dataset_id")), str(row.get("dataset_id") or "")
            )
        elif object_type == "campaign":
            object_label = campaign_name_by_id.get(
                str(row.get("object_id")), str(row.get("object") or row.get("object_id") or "")
            )
        else:
            object_label = "全组合 / 跨岛"
        level = str(row.get("evidence_level") or "未标注")
        tone = level_tone.get(level, "pending")
        diagnosis_cards.append(
            '<article class="diag-card">'
            '<div class="diag-head">'
            f'<span class="diag-level diag-{tone}">{_esc(level)}</span>'
            f'<span class="diag-object">{_esc(object_label)}</span>'
            '</div>'
            f'<p class="diag-finding">{_esc(str(row.get("finding") or ""))}</p>'
            + (
                f'<p class="muted diag-alt">替代解释/边界：{_esc(str(row.get("alternative")))}</p>'
                if row.get("alternative")
                else ""
            )
            + '</article>'
        )
    diagnosis_html = (
        '<section class="panel"><div class="section-head"><div>'
        '<span class="eyebrow">DIAGNOSIS</span><h2>诊断结论</h2></div>'
        '<span class="badge neutral">绿=数据事实 ｜ 黄=结构性推断 ｜ 蓝=情景估算 ｜ 灰=待核验</span></div>'
        f'<div class="diag-grid">{"".join(diagnosis_cards)}</div>'
        + "</section>"
        if diagnosis_cards
        else ""
    )
    action_rows = result.get("actions") or []
    action_html = _build_action_dashboard(result, action_rows)
    island_leads: dict[str, str] = {}
    for row in diagnosis_rows:
        if isinstance(row, Mapping) and str(row.get("object_type")) == "dataset":
            island_leads.setdefault(
                str(row.get("dataset_id")), str(row.get("finding") or "")
            )

    section_labels = {
        "inventory": "数据盘点",
        "mapping": "字段映射",
        "assumptions": "口径假设",
        "overall": "整体指标",
        "daily": "每日趋势",
        "campaigns": "计划汇总",
        "item_campaigns": "商品×计划",
        "diagnoses": "诊断结论",
        "actions": "行动清单",
        "appendix": "计划×日期附录",
        "formulas": "公式与边界",
    }
    coverage_status_labels = {
        "complete": "完整",
        "missing": "缺失",
        "partial": "部分可用",
        "not_applicable": "当前数据不适用",
    }
    coverage_rows = [
        {
            "section": section_labels.get(key, key),
            "status": coverage_status_labels.get(str(value), value),
        }
        for key, value in (coverage.get("sections") or {}).items()
    ]
    def _audit_token(value: Any) -> str:
        text = str(value or "").strip()
        lowered = text.lower()
        if lowered in {"", "unknown", "none", "未确认"} or "unconfirmed" in lowered:
            return "未确认"
        return text

    inventory_rows: list[dict[str, Any]] = []
    for item in audit.get("dataset_inventory") or []:
        inventory_rows.append(
            {
                "name": item.get("name"),
                "rows": item.get("rows"),
                "status": status_labels.get(str(item.get("status")), item.get("status")),
                "report_type": _audit_token(item.get("report_type")),
                "attribution_window": _audit_token(item.get("attribution_window")),
                "attribution_status": _audit_token(item.get("attribution_status")),
                "attribution_source": _audit_token(item.get("attribution_source")),
                "conversion_overlap": _audit_token(item.get("conversion_overlap")),
                "duplicate_rows": item.get("duplicate_rows"),
                "subtotal_rows": item.get("subtotal_rows"),
                "invalid_dates": item.get("invalid_dates"),
                "invalid_rows": len(item.get("invalid_rows") or []),
            }
        )
    attribution_rows = [
        {
            "dataset_id": item.get("dataset_id"),
            "window": _audit_token(item.get("window")),
            "status": _audit_token(item.get("status")),
            "source": _audit_token(item.get("source")),
            "conversion_overlap": _audit_token(item.get("conversion_overlap")),
        }
        for item in audit.get("attribution_registry") or []
    ]
    budget_rows: list[dict[str, Any]] = []
    for item in audit.get("budget_checks") or []:
        periods = item.get("periods") or []
        budget_rows.append(
            {
                "constraint_id": item.get("constraint_id"),
                "status": item.get("status"),
                "amount": item.get("amount"),
                "scope_type": item.get("scope_type"),
                "dataset_ids": ", ".join(str(value) for value in item.get("dataset_ids") or []),
                "hard_limit": item.get("hard_limit"),
                "period_count": len(periods),
                "over_limit_count": sum(
                    1
                    for period in periods
                    if isinstance(period, Mapping) and period.get("over_limit")
                ),
                "issue_codes": ", ".join(
                    str(issue.get("code"))
                    for issue in item.get("issues") or []
                    if isinstance(issue, Mapping)
                ),
            }
        )
    narrative_validation = audit.get("narrative_validation") or {}
    narrative_validation_rows = [
        {
            "status": narrative_validation.get("status"),
            "violation_count": len(narrative_validation.get("violations") or []),
            "codes": ", ".join(
                str(item.get("code"))
                for item in narrative_validation.get("violations") or []
                if isinstance(item, Mapping)
            ),
        }
    ]
    mapping_rows = [
        {
            "dataset": item.get("dataset"),
            "raw": item.get("raw"),
            "canonical": item.get("canonical") or "",
            "status": item.get("status"),
            "confidence": item.get("confidence"),
            "reason": item.get("reason"),
        }
        for item in audit.get("mapping_ledger") or []
    ]
    assumptions = result.get("assumptions") or {}
    assumptions_html = (
        '<div class="grid compact">'
        f'<div class="card">商品毛利率<b>{_format_number(assumptions.get("gross_margin_rate"), "ctr")}</b></div>'
        f'<div class="card">退款金额率<b>{_format_number(assumptions.get("refund_amount_rate"), "ctr")}</b></div>'
        f'<div class="card">适用范围<b>{_esc(assumptions.get("scope") or "未确认")}</b></div>'
        "</div>"
    )
    warnings = result.get("warnings") or []
    required = audit.get("required_fields") or []
    unsupported = result.get("unsupported_requests") or []
    def _audit_block(title: str, status_line: str, inner_html: str) -> str:
        return (
            f'<details class="audit-block"><summary>{_esc(title)}'
            f'<span class="audit-status">{_esc(status_line)}</span></summary>'
            f'<div class="audit-body">{inner_html}</div></details>'
        )

    coverage_complete = sum(1 for row in coverage_rows if row["status"] == "完整")
    inventory_complete = sum(1 for row in inventory_rows if row["status"] == "可完整分析")
    attribution_unknown = sum(
        1 for row in attribution_rows if str(row.get("status")) == "unknown"
    )
    mapping_mapped = sum(1 for row in mapping_rows if row["canonical"])
    narrative_status = str(narrative_validation.get("status") or "未运行")
    audit_html = (
        '<section class="panel"><div class="section-head"><div>'
        '<span class="eyebrow">AUDIT LEDGERS</span><h2>审表与口径台账</h2></div>'
        '<span class="badge neutral">默认折叠，展开可核对证据链</span></div>'
        "<h3>口径与假设</h3>"
        + assumptions_html
        + "<h3>审表警告</h3>"
        + _list_html(warnings, "无")
        + (
            "<h3>不可计算/补数字段</h3>" + _list_html(required, "")
            if required
            else ""
        )
        + (
            "<h3>不支持的请求</h3>" + _list_html(unsupported, "")
            if unsupported
            else ""
        )
        + _audit_block(
            "报告覆盖状态",
            f"{coverage_complete}/{len(coverage_rows)} 章节就绪",
            _table_html(
                "coverage",
                (("section", "章节"), ("status", "状态")),
                coverage_rows,
            ),
        )
        + _audit_block(
            "文件与数据盘点",
            f"{len(inventory_rows)} 个数据集 · {inventory_complete} 个可完整分析",
            _table_html(
                "inventory",
                (
                    ("name", "数据集/Sheet"),
                    ("rows", "行数"),
                    ("status", "能力"),
                    ("report_type", "推广类型"),
                    ("attribution_window", "归因窗口"),
                    ("attribution_status", "归因状态"),
                    ("attribution_source", "归因来源"),
                    ("conversion_overlap", "成交重叠"),
                    ("duplicate_rows", "重复行"),
                    ("subtotal_rows", "合计行"),
                    ("invalid_dates", "异常日期"),
                    ("invalid_rows", "异常数值"),
                ),
                inventory_rows,
            ),
        )
        + _audit_block(
            "归因来源台账",
            (
                f"{attribution_unknown}/{len(attribution_rows)} 岛归因窗口未确认"
                if attribution_rows
                else "无记录"
            ),
            _table_html(
                "attribution-registry",
                (
                    ("dataset_id", "数据岛 ID"),
                    ("window", "窗口"),
                    ("status", "状态"),
                    ("source", "来源"),
                    ("conversion_overlap", "成交重叠"),
                ),
                attribution_rows,
            ),
        )
        + _audit_block(
            "预算约束检查",
            (
                f"{len(budget_rows)} 条约束记录"
                if budget_rows
                else "未登记预算上限或不可暂停对象"
            ),
            (
                _table_html(
                    "budget-checks",
                    (
                        ("constraint_id", "约束 ID"),
                        ("status", "状态"),
                        ("amount", "金额"),
                        ("scope_type", "范围"),
                        ("dataset_ids", "数据岛"),
                        ("hard_limit", "硬上限"),
                        ("period_count", "检查周期"),
                        ("over_limit_count", "超限周期"),
                        ("issue_codes", "问题码"),
                    ),
                    budget_rows,
                )
                if budget_rows
                else '<p class="empty">本轮未登记预算约束；涉及预算的动作均以“待确认”处理。</p>'
            ),
        )
        + _audit_block(
            "叙事安全门禁",
            f"{narrative_status} · 阻断 0 条"
            if narrative_status == "passed"
            else narrative_status,
            _table_html(
                "narrative-validation",
                (
                    ("status", "状态"),
                    ("violation_count", "阻断数"),
                    ("codes", "问题码"),
                ),
                narrative_validation_rows,
            ),
        )
        + _audit_block(
            "字段映射台账",
            f"{mapping_mapped}/{len(mapping_rows)} 字段已映射",
            _table_html(
                "mapping",
                (
                    ("dataset", "数据集"),
                    ("raw", "原字段"),
                    ("canonical", "标准字段"),
                    ("status", "状态"),
                    ("confidence", "可信度"),
                    ("reason", "理由"),
                ),
                mapping_rows,
            ),
        )
        + "</section>"
    )

    question_items = [
        f"{question.get('question', '')}（原因：{question.get('reason', '')}）"
        for question in result.get("questions") or []
    ]
    questions_html = (
        '<section class="panel"><h2>检查点追问记录</h2>'
        f'<details class="audit-block"><summary>本轮追问 {len(question_items)} 条'
        f'<span class="audit-status">检查点状态：{_esc(str(result.get("checkpoint_status") or "未记录"))}</span></summary>'
        f'<div class="audit-body">{_list_html(question_items, "无")}</div></details>'
        + "</section>"
        if question_items
        else ""
    )

    campaign_headers_core = (
        ("campaign_id", "计划 ID"),
        ("campaign_name", "计划名称"),
        ("spend", "花费"),
        ("transaction_amount", "总成交金额"),
        ("roi", "ROI"),
        ("cpc", "CPC"),
        ("order_cvr", "订单 CVR"),
        ("buyer_cvr", "买家 CVR"),
    )
    campaign_headers_dates = (
        ("date_start", "开始日期"),
        ("date_end", "结束日期"),
        ("missing_date_count", "日期缺口"),
        ("excluded_date_count", "隔离日期"),
    )
    daily_headers_base = (
        ("date", "日期"),
        ("impressions", "展现量"),
        ("clicks", "点击量"),
        ("spend", "花费"),
        ("transaction_amount", "总成交金额"),
        ("roi", "ROI"),
        ("cpc", "CPC"),
        ("order_cvr", "订单 CVR"),
    )
    item_campaign_headers = (
        ("item_id", "商品 ID"),
        ("item_name", "商品名称"),
        ("campaign_id", "计划 ID"),
        ("campaign_name", "计划名称"),
        ("row_count", "明细行"),
        ("spend", "花费"),
        ("transaction_amount", "总成交金额"),
        ("roi", "ROI"),
        ("promotion_contribution_profit", "推广贡献盈亏"),
    )
    detail_headers_base = (
        ("source_dataset", "来源"),
        ("source_row", "原行号"),
        ("date", "日期"),
        ("campaign_id", "计划 ID"),
        ("campaign_name", "计划名称"),
        ("impressions", "展现量"),
        ("clicks", "点击量"),
        ("spend", "花费"),
        ("transaction_orders", "成交笔数"),
        ("buyers", "成交人数"),
        ("transaction_amount", "总成交金额"),
        ("excluded_reason", "排除原因"),
    )

    island_sections: list[str] = []
    island_tabs: list[str] = []
    for index, island in enumerate(islands, start=1):
        metrics = island.get("metrics") or {}
        totals = island.get("totals") or {}
        financial = island.get("financial_estimate") or {}
        spend_v = totals.get("spend")
        gmv_v = totals.get("transaction_amount")
        roi_v = metrics.get("roi")
        profit_v = metrics.get("promotion_contribution_profit")
        roi_badge = ""
        if isinstance(roi_v, (int, float)) and breakeven_roi is not None:
            roi_badge = (
                f'<span class="badge {"good" if roi_v >= breakeven_roi else "bad"}">'
                f'{"高于" if roi_v >= breakeven_roi else "低于"}保本线 {breakeven_roi:.2f}</span>'
            )
        profit_lamp = (
            _format_number(profit_v, "profit_signal") if profit_v is not None else ""
        )
        decision_strip = (
            '<div class="island-decision">'
            f'<div class="idec"><span>花费</span><b>{_format_number(spend_v, "spend")}</b></div>'
            f'<div class="idec"><span>报表归因成交</span><b>{_format_number(gmv_v, "transaction_amount")}</b></div>'
            f'<div class="idec"><span>ROI</span><b>{_format_number(roi_v, "roi")}</b>{roi_badge}</div>'
            f'<div class="idec"><span>情景盈亏</span><b>{_format_number(profit_v, "promotion_contribution_profit")}</b>{profit_lamp}</div>'
            '</div>'
        )
        slim_parts: list[str] = []
        for key, value in totals.items():
            if key in ("spend", "transaction_amount"):
                continue
            slim_parts.append(f"{FIELD_LABELS.get(key, key)} {_format_number(value, key)}")
        for key, value in metrics.items():
            if key in ("roi", "promotion_contribution_profit"):
                continue
            scenario_mark = (
                "（情景估算）"
                if key in FINANCIAL_METRICS and financial.get("is_scenario")
                else ""
            )
            slim_parts.append(
                f"{METRIC_LABELS.get(key, key)}{scenario_mark} {_format_number(value, key)}"
            )
        slim_strip = (
            f'<p class="slim-strip">{" ｜ ".join(_esc(part) for part in slim_parts)}</p>'
            if slim_parts
            else '<p class="empty">当前字段不足，未生成效率指标</p>'
        )
        campaign_rows: list[dict[str, Any]] = []
        for row in island.get("campaigns") or []:
            flattened = _flatten_summary(row)
            date_coverage = row.get("date_coverage") or {}
            flattened.update(
                {
                    "date_start": date_coverage.get("start_date"),
                    "date_end": date_coverage.get("end_date"),
                    "missing_date_count": len(
                        date_coverage.get("missing_source_dates") or []
                    ),
                    "excluded_date_count": len(
                        date_coverage.get("excluded_dates") or []
                    ),
                }
            )
            campaign_rows.append(flattened)
        has_campaign_profit = "promotion_contribution_profit" in metrics
        if has_campaign_profit:
            for row in campaign_rows:
                row["profit_signal"] = row.get("promotion_contribution_profit")
        campaign_rows.sort(
            key=lambda row: (
                -(float(row["spend"]) if isinstance(row.get("spend"), (int, float)) else -1),
                str(row.get("campaign_id")),
            )
        )
        campaign_headers = campaign_headers_core
        if has_campaign_profit:
            campaign_headers = campaign_headers + (
                ("promotion_contribution_profit", "推广贡献盈亏"),
                ("profit_signal", "盈亏"),
            )
        campaign_headers = campaign_headers + campaign_headers_dates
        campaign_row_class = (
            (
                lambda row: "row-loss"
                if isinstance(row.get("promotion_contribution_profit"), (int, float))
                and row["promotion_contribution_profit"] < 0
                else ""
            )
            if has_campaign_profit
            else None
        )
        daily_rows = [_flatten_summary(row) for row in island.get("daily") or []]
        has_daily_profit = bool(daily_rows) and all(
            row.get("promotion_contribution_profit") is not None
            for row in daily_rows
        )
        daily_headers = daily_headers_base
        if has_daily_profit:
            for row in daily_rows:
                row["profit_signal"] = row.get("promotion_contribution_profit")
            daily_headers = daily_headers_base + (
                ("promotion_contribution_profit", "当日推广贡献盈亏"),
                ("profit_signal", "当日盈亏"),
            )
        item_campaign_rows = [
            _flatten_summary(row) for row in island.get("item_campaigns") or []
        ]
        details = island.get("details") or []
        detail_headers = detail_headers_base
        raw_columns: set[str] = set()
        if any("source_values" in row for row in details):
            detail_headers = detail_headers + (("source_values", "脱敏原始行"),)
            raw_columns.add("source_values")
        island_id = f"island-{index}"
        island_tabs.append(
            f'<button type="button" role="tab" id="{island_id}-tab" '
            f'aria-controls="{island_id}-panel" aria-selected="{"true" if index == 1 else "false"}" '
            f'tabindex="{0 if index == 1 else -1}" data-island-tab="{island_id}">'
            f'{_esc(island.get("source_dataset"))}</button>'
        )
        not_computable_items = [
            f"{METRIC_LABELS.get(key, key)}：{reason}"
            for key, reason in (island.get("not_computable") or {}).items()
        ]
        item_campaign_html = (
            _table_html(
                f"{island_id}-item-campaigns",
                item_campaign_headers,
                item_campaign_rows,
            )
            if item_campaign_rows
            else '<p class="empty">当前数据没有同时可用的商品与计划身份，本章节不适用。</p>'
        )
        island_status_known: list[str] = []
        island_status_unknown: list[str] = []
        for label, value in (
            ("推广类型", island.get("report_type")),
            ("归因窗口", island.get("attribution_window")),
            ("归因状态", island.get("attribution_status")),
            ("归因来源", island.get("attribution_source")),
        ):
            text = str(value or "").strip()
            lowered = text.lower()
            if (
                lowered in {"", "unknown", "none", "未确认"}
                or "unconfirmed" in lowered
            ):
                island_status_unknown.append(label)
            else:
                island_status_known.append(f"{label}：{text}")
        if island_status_unknown:
            island_status_known.append("未确认：" + "、".join(island_status_unknown))
        island_status_line = " ｜ ".join(island_status_known)
        section = (
            f'<section class="panel island-panel" id="{island_id}-panel" data-island-panel="{island_id}"><div class="section-head"><div><span class="eyebrow">'
            f"DATA ISLAND {index}</span><h2>{_esc(island.get('source_dataset'))}</h2></div>"
            f'<span class="badge neutral">{_esc(status_labels.get(str(island.get("status")), island.get("status")))}</span></div>'
            f'<p class="muted">{_esc(island_status_line)}</p>'
            + (
                f'<p class="island-lead">{_esc(island_leads.get(str(island.get("dataset_id")), ""))}</p>'
                if island_leads.get(str(island.get("dataset_id")))
                else ""
            )
            + decision_strip
            + slim_strip
            + (
                "<h3>不可计算项</h3>" + _list_html(not_computable_items, "无")
                if not_computable_items
                else ""
            )
            + "<h3>计划周期汇总（默认按花费降序，亏损行红底）</h3>"
            f'<div class="toolbar"><input data-filter-target="{island_id}-campaigns" '
            'placeholder="筛选计划 ID 或名称"></div>'
            + _table_html(
                f"{island_id}-campaigns",
                campaign_headers,
                campaign_rows,
                row_class=campaign_row_class,
            )
            + "<h3>每日趋势</h3>"
            + _table_html(f"{island_id}-daily", daily_headers, daily_rows)
            + (
                '<p class="muted">当日盈亏为商品毛利口径情景估算（全店统一费率假设），'
                "单日波动不构成决策依据；计划调整以周期汇总为准。</p>"
                if has_daily_profit
                else ""
            )
            + "<h3>商品 × 计划组合</h3>"
            + item_campaign_html
            + '<details class="appendix"><summary>计划 × 日期完整附录'
            f"（{len(details)} 行）</summary>"
            f'<div class="toolbar"><input data-filter-target="{island_id}-details" '
            'placeholder="筛选任意明细文本"></div>'
            + _table_html(
                f"{island_id}-details",
                detail_headers,
                details,
                raw_columns,
            )
            + "</details></section>"
        )
        island_sections.append(section)

    insights = result.get("insights") or {}
    good_patterns = [str(item) for item in insights.get("good_patterns") or []]
    bad_patterns = [str(item) for item in insights.get("bad_patterns") or []]
    next_rules = [
        rule for rule in insights.get("next_time_rules") or [] if isinstance(rule, Mapping)
    ]
    review_hooks = [str(item) for item in insights.get("review_hooks") or []]
    closing_html = ""
    if good_patterns or bad_patterns or next_rules:
        rules_html = "".join(
            "<li>"
            f'<span class="badge {"good" if str(rule.get("status")) == "本期证据" else "neutral"}">'
            f'{_esc(str(rule.get("status") or "待验证"))}</span> '
            f'{_esc(str(rule.get("rule") or ""))}'
            + (
                f'<br><span class="muted">依据：{_esc(str(rule.get("basis")))}</span>'
                if rule.get("basis")
                else ""
            )
            + "</li>"
            for rule in next_rules
        )
        closing_html = (
            '<section class="panel closing"><div class="section-head"><div>'
            '<span class="eyebrow">LESSONS & NEXT LOOP</span><h2>经验沉淀与正循环</h2></div>'
            '<span class="badge neutral">从本期数据里长出来的可复用经验</span></div>'
            '<div class="lessons-grid">'
            '<div class="lessons-col lessons-good"><h3>✅ 表现好的计划有什么共同点</h3>'
            + _list_html(good_patterns, "本期未提炼出稳定的正向模式")
            + '</div>'
            '<div class="lessons-col lessons-bad"><h3>⚠️ 出问题的地方有什么共同点</h3>'
            + _list_html(bad_patterns, "本期未提炼出稳定的问题模式")
            + "</div></div>"
            f"<h3>下次再建计划，注意这 {len(next_rules)} 条</h3>"
            f'<ol class="rules-list">{rules_html}</ol>'
            "<h3>下期对答案（本期埋的钩子）</h3>"
            + _list_html(
                [f"{hook}" for hook in review_hooks],
                "本期没有留下对账钩子",
            )
            + '<p class="muted">下次报送同口径报表时，先核对以上钩子，再看新数据——'
            "口径与证据链见上方「审表与口径台账」。</p></section>"
        )
    elif action_rows:
        closing_counts: dict[str, int] = {}
        for action in action_rows:
            code = _canonical_action_code(
                action.get("target_action") or action.get("action_code")
            )
            closing_counts[code] = closing_counts.get(code, 0) + 1
        change_total = sum(
            closing_counts.get(code, 0) for code in CHANGE_TARGET_ACTIONS
        )
        maintain_total = closing_counts.get("maintain", 0)
        watch_total = closing_counts.get("investigate", 0) + closing_counts.get(
            "request_data", 0
        )
        change_parts = "、".join(
            f"{ACTION_LABELS.get(code, code)} {closing_counts[code]} 个"
            for code in (
                "pause",
                "close",
                "decrease_budget",
                "reallocate",
                "increase_budget",
                "increase_bid",
                "decrease_bid",
            )
            if closing_counts.get(code)
        )
        margin_text = _format_number(
            assumptions.get("gross_margin_rate"), "ctr"
        )
        refund_text = _format_number(
            assumptions.get("refund_amount_rate"), "ctr"
        )
        closing_cards = ""
        if change_total:
            closing_cards += (
                '<article class="summary-card tone-red"><h3>🔴 需要变化</h3>'
                f'<p>{change_total} 个计划列为变化候选：{change_parts}。'
                "归因窗口确认前，这些目标动作保持「先核验」，不升级为执行。</p></article>"
            )
        if maintain_total:
            closing_cards += (
                '<article class="summary-card tone-green"><h3>🟢 保持观察</h3>'
                f'<p>{maintain_total} 个计划保持并观察，按复核合同每周复查；'
                "连续 7 天 ROI 低于情景保本线时降级重审。</p></article>"
            )
        if watch_total:
            closing_cards += (
                '<article class="summary-card tone-amber"><h3>🟡 证据不足</h3>'
                f'<p>{watch_total} 个计划数据不足或需补数，继续观察，不做结构调整。</p></article>'
            )
        closing_cards += (
            '<article class="summary-card tone-gray"><h3>⚪ 口径边界</h3>'
            f"<p>全部成交为报表归因记录，归因窗口未确认；盈亏与保本线为情景估算"
            f"（毛利率 {margin_text}、退款金额率 {refund_text} 全店统一假设），不是净利润。</p></article>"
            '<article class="summary-card tone-blue"><h3>🔵 下次报送</h3>'
            "<p>下次报送同一口径报表时可与本期基线对比变化；确认归因窗口与成交口径后，"
            "砍减类候选动作即可按升级条件转为执行。</p></article>"
        )
        closing_html = (
            '<section class="panel closing"><div class="section-head"><div>'
            '<span class="eyebrow">WRAP UP</span><h2>收尾总结</h2></div>'
            '<span class="badge neutral">与卷首执行摘要呼应：总-分-总</span></div>'
            f'<div class="summary-grid">{closing_cards}</div>'
            '<p class="muted">回到 <a href="#action-cockpit">行动驾驶舱</a> '
            "处理变化候选计划；口径与证据链见上方「审表与口径台账」。</p></section>"
        )

    formula_html = (
        '<section class="panel"><h2>公式与边界</h2>'
        + _table_html(
            "formulas",
            (("name", "指标"), ("formula", "公式")),
            result.get("formulas") or [],
        )
        + "<p class=\"muted\">所有比率使用总分子÷总分母；商品毛利率仅扣商品成本。"
        "归因数据不等于增量因果。</p></section>"
    )
    footer = (
        "生成时间："
        + _esc(datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"))
        + "｜单文件离线报告｜Skill地址："
        + '<a href="https://github.com/sgskills/aibp" target="_blank" rel="noopener">github.com/sgskills/aibp</a>'
    )
    replacements = {
        "{{TITLE}}": _esc(title),
        "{{SUBTITLE}}": _esc(subtitle),
        "{{SUMMARY}}": summary,
        "{{DIAGNOSIS}}": diagnosis_html,
        "{{ACTIONS}}": action_html,
        "{{AUDIT}}": audit_html,
        "{{QUESTIONS}}": questions_html,
        "{{ISLANDS}}": (
            '<section class="island-explorer" id="island-analysis">'
            '<div class="section-shell"><div class="section-title"><span class="section-number">3</span><div><span class="eyebrow">DATA ISLANDS</span><h2>分岛分析</h2></div></div>'
            '<p class="muted">不同推广类型或归因窗口未确认可比前，标签页只切换视图，不做跨岛相加或排名。</p>'
            f'<div class="island-tabs" role="tablist" aria-label="数据岛">{"".join(island_tabs)}</div></div>'
            f'{"".join(island_sections)}</section>'
        )
        if island_sections
        else '<section class="panel"><p class="empty">没有可分析的数据岛</p></section>',
        "{{FORMULAS}}": formula_html,
        "{{CLOSING}}": closing_html,
        "{{FOOTER}}": footer,
    }
    for token, value in replacements.items():
        template = template.replace(token, value)
    # 出厂自检：首屏标题必须是报告标题；不得残留占位符。自检不过宁可不出文件。
    leftovers = re.findall(r"\{\{[A-Z_]{2,}\}\}", template)
    if leftovers:
        raise InputFormatError(f"HTML 渲染自检失败：存在未替换的占位符 {sorted(set(leftovers))}")
    if f"<h1>{_esc(title)}</h1>" not in template:
        raise InputFormatError("HTML 渲染自检失败：首屏标题与报告标题不一致")
    return template


def _normalize_store_label(name: Any) -> str:
    """归一化店铺名：去空白；去掉结尾冗余的「店铺」，以及 ASCII 名末尾的「店」，
    避免模板补「店铺」后出现「K3 店店铺」式重复；保留「旗舰店/专卖店」等中文店名结尾。"""
    store = re.sub(r"\s+", "", str(name or ""))
    store = re.sub(r"店铺+$", "", store)
    store = re.sub(r"(?<=[A-Za-z0-9])店+$", "", store)
    return store


def _normalize_platform_label(name: Any) -> str:
    """归一化平台名：去空白与文件名非法字符，最长 12 字，为空回退「天猫」。"""
    platform = re.sub(r"\s+", "", str(name or ""))
    platform = re.sub(r'[\\/:*?"<>|\r\n]+', "", platform)
    return platform[:12] or "天猫"


def _canonical_html_filename(result: Mapping[str, Any], platform: str = "天猫") -> str:
    """规范文件名：《XX店铺XX平台推广诊断报告-YYMMDD》。"""
    context = result.get("context") or {}
    store = _normalize_store_label(context.get("store_name")) or "未命名店铺"
    store = re.sub(r'[\\/:*?"<>|\r\n]+', "", store)
    coverage = result.get("coverage") or {}
    kind = (
        "推广诊断报告"
        if str(coverage.get("report_status") or "") == "full"
        else "推广数据分析附件"
    )
    date_stamp = datetime.now(timezone.utc).astimezone().strftime("%y%m%d")
    return f"{store}店铺{platform}{kind}-{date_stamp}.html"


def _read_text_with_fallback(path: Path) -> str:
    errors: list[str] = []
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")
        except OSError as exc:
            raise InputFormatError(f"无法读取输入文件：{exc}") from exc
    raise InputFormatError("无法识别文本编码；" + "；".join(errors))


def _load_input(
    path: Path,
    dataset_name: str,
    report_type: str,
    attribution_window: str,
) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            payload = json.loads(_read_text_with_fallback(path))
        except json.JSONDecodeError as exc:
            raise InputFormatError(f"JSON 格式错误：{exc}") from exc
        if not isinstance(payload, dict):
            raise InputFormatError("JSON 顶层必须是对象")
        return payload
    if suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        reader = csv.reader(io.StringIO(_read_text_with_fallback(path)), delimiter=delimiter)
        parsed_rows = list(reader)
        if not parsed_rows:
            raise InputFormatError("CSV/TSV 为空，无法识别表头")
        headers = [str(value) for value in parsed_rows[0]]
        positions: dict[str, list[int]] = defaultdict(list)
        for position, header in enumerate(headers, start=1):
            positions[_normalize_header(header)].append(position)
        duplicates = {
            normalized: indexes
            for normalized, indexes in positions.items()
            if len(indexes) > 1
        }
        if duplicates:
            parts: list[str] = []
            for normalized, indexes in duplicates.items():
                raw_labels = [headers[index - 1] for index in indexes]
                label = " / ".join(dict.fromkeys(raw_labels)) or "(空表头)"
                parts.append(f"{label}（列 {', '.join(map(str, indexes))}）")
            raise InputFormatError(
                "检测到重复表头，已停止该数据岛计算，不能静默选择其中一列："
                + "；".join(parts)
            )
        rows: list[dict[str, Any]] = []
        for row_number, values in enumerate(parsed_rows[1:], start=2):
            if len(values) != len(headers):
                raise InputFormatError(
                    f"第 {row_number} 行列数为 {len(values)}，"
                    f"与表头 {len(headers)} 列不一致"
                )
            rows.append(dict(zip(headers, values)))
        return {
            "datasets": [
                {
                    "name": dataset_name or path.stem,
                    "report_type": report_type,
                    "attribution_window": attribution_window,
                    "rows": rows,
                }
            ]
        }
    if suffix in {".xlsx", ".xls"}:
        raise InputFormatError(
            "标准库脚本不直接读取 XLSX/XLS；请由当前表格工具转成规范 JSON，"
            "或另存为 CSV/TSV 后重试。"
        )
    raise InputFormatError("仅支持 JSON、CSV、TSV；其他格式请先转换或粘贴表格。")


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(_read_text_with_fallback(path))
    except json.JSONDecodeError as exc:
        raise InputFormatError(f"{label} JSON 格式错误：{exc}") from exc
    if not isinstance(value, dict):
        raise InputFormatError(f"{label} JSON 顶层必须是对象")
    return value


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _validate_output_paths(
    input_paths: Sequence[Path],
    output_paths: Sequence[Path],
    *,
    force: bool,
) -> None:
    resolved_inputs = {_resolved(path) for path in input_paths}
    resolved_outputs = [_resolved(path) for path in output_paths]
    if len(set(resolved_outputs)) != len(resolved_outputs):
        raise InputFormatError("JSON 与 HTML 输出路径不得相同")
    for path in resolved_outputs:
        if path in resolved_inputs:
            raise InputFormatError("输入文件与输出文件不得使用同一路径，--force 也不能绕过")
        if path.exists() and not force:
            raise InputFormatError(f"输出文件已存在，默认拒绝覆盖：{path}；确认后使用 --force")
        if path.exists() and path.is_dir():
            raise InputFormatError(f"输出路径是目录，不能写入文件：{path}")


def _write_text(path: Path, content: str, *, force: bool = False) -> None:
    """在同一目录写临时文件并原子替换，失败时不留下半写文件。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        raise InputFormatError(f"输出文件已存在，默认拒绝覆盖：{path}")
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists() and not force:
            raise InputFormatError(f"输出文件已存在，默认拒绝覆盖：{path}")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="审计并分析天猫推广规范长表")
    parser.add_argument("--input", required=True, type=Path, help="JSON、CSV 或 TSV")
    parser.add_argument("--json-output", type=Path, help="分析结果 JSON")
    parser.add_argument("--html-output", type=Path, help="离线 HTML 报告")
    parser.add_argument(
        "--narrative-input",
        type=Path,
        help="Agent 已完成的执行摘要、诊断和行动 JSON；用于生成完整报告",
    )
    parser.add_argument(
        "--include-raw",
        action="store_true",
        help="显式附带经过脱敏的原始行；默认不输出未知列原始值",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="允许原子替换已存在的输出文件；不能绕过输入/输出路径冲突",
    )
    parser.add_argument("--dataset-name", default="", help="CSV/TSV 数据岛名称")
    parser.add_argument("--store-name", default="", help="店铺名；用于副标题与规范文件名")
    parser.add_argument(
        "--platform",
        default="天猫",
        help="平台名（如 天猫/抖音/京东）；用于报告标题、副标题与规范文件名，默认 天猫",
    )
    parser.add_argument("--report-type", default="unknown", help="CSV/TSV 报表类型")
    parser.add_argument(
        "--attribution-window", default="unknown", help="CSV/TSV 归因窗口"
    )
    parser.add_argument(
        "--checkpoint-status",
        choices=sorted(CHECKPOINT_STATUSES),
        help=(
            "追问检查点状态；省略时按是否仍有高价值问题推断为 "
            "awaiting_user 或 answered"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        protected_inputs = [args.input]
        if args.narrative_input:
            protected_inputs.append(args.narrative_input)
        requested_outputs = [
            path for path in (args.json_output, args.html_output) if path is not None
        ]
        _validate_output_paths(
            protected_inputs,
            requested_outputs,
            force=args.force,
        )
        payload = _load_input(
            args.input,
            args.dataset_name,
            args.report_type,
            args.attribution_window,
        )
        result = analyze_payload(
            payload,
            include_raw=args.include_raw,
            checkpoint_status=args.checkpoint_status,
            file_status="created" if requested_outputs else "not_created",
        )
        if args.narrative_input:
            narrative = _load_json_object(args.narrative_input, "narrative")
            result = merge_narrative(result, narrative)
        if args.store_name:
            context = result.setdefault("context", {})
            if isinstance(context, dict):
                context["store_name"] = args.store_name
        json_text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        platform = _normalize_platform_label(args.platform)
        html_text = render_html(result, platform=platform) if args.html_output else None
        if args.json_output:
            _write_text(args.json_output, json_text, force=args.force)
        if args.html_output and html_text is not None:
            html_path = args.html_output
            canonical = _canonical_html_filename(result, platform=platform)
            if html_path.name != canonical:
                html_path = html_path.parent / canonical
                if html_path != args.html_output:
                    sys.stderr.write(f"提示：HTML 文件名已按规范命名为 {canonical}\n")
                    _validate_output_paths(protected_inputs, [html_path], force=args.force)
            _write_text(html_path, html_text, force=args.force)
        if not args.json_output and not args.html_output:
            sys.stdout.write(json_text + "\n")
        return 0
    except (InputFormatError, OSError, TypeError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 2


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
