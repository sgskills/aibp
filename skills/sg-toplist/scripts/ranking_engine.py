#!/usr/bin/env python3
"""把已审计排名转为结构、变化信号和可验证机会假设。"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date, timedelta
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from audit_input import RankingInputError, audit_dataset, load_inputs_isolated, normalize_payload
from entity_matcher import match_periods


POLLUTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("transaction_only_link", re.compile(r"专拍|专属.{0,4}链接|福利.{0,4}链接|拍这里|补差价|补邮费|运费补拍|定金|尾款")),
    ("non_product_listing", re.compile(r"测试链接|勿拍|仅供测试|赠品链接")),
)

WRONG_CATEGORY_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("平板电脑", ("平板", "电脑", "数码")),
    ("笔记本电脑", ("电脑", "数码")),
    ("智能手机", ("手机", "数码")),
    ("路由器", ("路由器", "网络设备", "数码")),
    ("蓝牙耳机", ("耳机", "数码")),
)

TITLE_ATTRIBUTE_TERMS = (
    "陶瓷",
    "玻璃",
    "不锈钢",
    "木质",
    "家用",
    "新婚",
    "乔迁",
    "礼盒",
    "微波炉",
    "洗碗机",
    "日式",
    "中式",
    "欧式",
    "高颜值",
)


def _series_key(period: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return tuple(str(period.get(key) or "未声明") for key in ("platform", "scope", "category", "ranking_metric"))


def _period_sort_key(period: Mapping[str, Any]) -> tuple[str, str, int]:
    return (
        str(period.get("start_date") or "9999-12-31"),
        str(period.get("period") or ""),
        int(period.get("input_order") or 0),
    )


def _row_position(row: Mapping[str, Any]) -> dict[str, Any]:
    source = row.get("_source") if isinstance(row.get("_source"), Mapping) else {}
    return {"file": source.get("file"), "sheet": source.get("sheet"), "island_id": source.get("island_id"), "series_id": source.get("series_id"), "row": source.get("row"), "rank": row.get("rank")}


def _island_position(period: Mapping[str, Any]) -> dict[str, Any]:
    rows = period.get("rows", [])
    ids = Counter(str(row.get("product_id") or "") for row in rows)
    return {"file": period.get("source_file"), "sheet": period.get("sheet"),
            "island_id": period.get("island_id"), "period": period.get("period"),
            "top_n": period.get("top_n"), "denominator": len(rows),
            "valid_unique_id_count": sum(bool(pid) and count == 1 for pid, count in ids.items()),
            "excluded_id_rows": sum(count for pid, count in ids.items() if not pid or count > 1),
            "filter": "该岛全部原始排名行；不跨岛相加", "aggregation": "count(rows)"}


def _metric_coverage(rows: Sequence[Mapping[str, Any]], metric: str) -> int:
    return sum(row.get(f"{metric}_raw") not in (None, "") for row in rows)


def _interval_summary(rows: Sequence[Mapping[str, Any]], metric: str) -> dict[str, Any] | None:
    intervals = [row.get(f"{metric}_interval") for row in rows if row.get(f"{metric}_interval")]
    if not intervals:
        return None
    lower_values = [float(item["lower"]) for item in intervals if item.get("lower") is not None]
    upper_values = [float(item["upper"]) for item in intervals if item.get("upper") is not None]
    midpoints = [float(item["estimated_midpoint"]) for item in intervals if item.get("estimated_midpoint") is not None]
    ordered_midpoints = sorted(midpoints)
    midpoint = median(ordered_midpoints) if ordered_midpoints else None
    return {
        "coverage": len(intervals),
        "observed_lower_min": min(lower_values) if lower_values else None,
        "observed_upper_max": max(upper_values) if upper_values else None,
        "estimated_midpoint_median": midpoint,
        "midpoint_is_estimate": any(bool(item.get("midpoint_is_estimate")) for item in intervals),
        "not_sales_share_or_gmv": True,
    }


def _top_counter(rows: Sequence[Mapping[str, Any]], field: str, limit: int = 10) -> list[dict[str, Any]]:
    counter = Counter(str(row.get(field) or "").strip() for row in rows if str(row.get(field) or "").strip())
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


def _keyword_counter(rows: Sequence[Mapping[str, Any]], limit: int = 15) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in rows:
        for token in re.split(r"[,，、;/；|\s]+", str(row.get("keywords") or "")):
            token = token.strip()
            if token:
                counter[token] += 1
    return [
        {
            "attribute": token,
            "count": count,
            "evidence_label": "商品关键词显式字段",
            "not_consumer_demand": True,
        }
        for token, count in counter.most_common(limit)
    ]


def _title_attribute_counter(rows: Sequence[Mapping[str, Any]], limit: int = 15) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in rows:
        title = str(row.get("title") or "")
        for term in TITLE_ATTRIBUTE_TERMS:
            if term in title:
                counter[term] += 1
    return [
        {
            "attribute": term,
            "count": count,
            "evidence_label": "标题显式提及",
            "not_consumer_demand": True,
        }
        for term, count in counter.most_common(limit)
    ]


def _structure(periods: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    summaries: list[dict[str, Any]] = []
    for period in sorted(periods, key=_period_sort_key):
        rows = list(period.get("rows") or [])
        ranks = [int(row["rank"]) for row in rows if isinstance(row.get("rank"), int)]
        summaries.append(
            {
                "island_id": period.get("island_id"),
                "period": period.get("period"),
                "platform": period.get("platform"),
                "scope": period.get("scope"),
                "category": period.get("category"),
                "ranking_metric": period.get("ranking_metric"),
                "top_n": period.get("top_n"),
                "row_count": len(rows),
                "data_position_and_definition": _island_position(period),
                "rank_min": min(ranks) if ranks else None,
                "rank_max": max(ranks) if ranks else None,
                "shop_type_distribution": _top_counter(rows, "shop_type"),
                "top_shops": _top_counter(rows, "shop"),
                "top_brands": _top_counter(rows, "brand"),
                "title_explicit_attributes": _title_attribute_counter(rows),
                "keyword_explicit_attributes": _keyword_counter(rows),
                "price_analysis": _interval_summary(rows, "price"),
                "field_coverage": {
                    metric: _metric_coverage(rows, metric)
                    for metric in ("buyers", "visitors", "payment_amount", "price", "cost")
                },
            }
        )
    return {"periods": summaries, "period_count": len({str(period.get("period")) for period in periods})}


def _pollution_reason(row: Mapping[str, Any], dominant_category: str) -> str | None:
    title = str(row.get("title") or "")
    for code, pattern in POLLUTION_PATTERNS:
        if pattern.search(title):
            return code
    for marker, allowed_category_tokens in WRONG_CATEGORY_MARKERS:
        if marker in title and not any(token in dominant_category for token in allowed_category_tokens):
            return "likely_wrong_category"
    return None


def _detect_pollution(periods: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for period in periods:
        rows = list(period.get("rows") or [])
        category_counter = Counter(str(row.get("category") or period.get("category") or "") for row in rows)
        dominant_category = category_counter.most_common(1)[0][0] if category_counter else str(period.get("category") or "")
        for row in rows:
            reason = _pollution_reason(row, dominant_category)
            if reason is None:
                continue
            evidence.append(
                {
                    "island_id": period.get("island_id"),
                    "series_id": period.get("series_id"),
                    "period": period.get("period"),
                    "product_id": row.get("product_id"),
                    "rank": row.get("rank"),
                    "title": row.get("title"),
                    "reason": reason,
                    "position": _row_position(row),
                }
            )
    return evidence


def _clean_periods(periods: Sequence[Mapping[str, Any]], evidence: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    blocked_positions = {
        (
            str(item.get("island_id")),
            str(item.get("product_id")),
            item.get("position", {}).get("row"),
        )
        for item in evidence
    }
    cleaned: list[dict[str, Any]] = []
    for period in periods:
        period_copy = {key: value for key, value in period.items() if key != "rows"}
        period_copy["rows"] = [
            row
            for row in period.get("rows", [])
            if (
                str(period.get("island_id")),
                str(row.get("product_id")),
                (row.get("_source") or {}).get("row") if isinstance(row.get("_source"), Mapping) else None,
            )
            not in blocked_positions
        ]
        cleaned.append(period_copy)
    return cleaned


def _filter_trajectories_for_sensitivity(
    trajectories: Mapping[str, Any], pollution_ids: set[tuple[str, str]]
) -> dict[str, Any]:
    """从已验证的原始共同K轨迹中过滤污染ID，避免清洗后排名缺口伪造新阻断。"""
    filtered: dict[str, Any] = {}
    single_id_lists = (
        "matched",
        "entries",
        "exits",
        "reentries",
        "platform_new_listed",
        "reuse_suspects",
        "keyword_changes",
        "excluded_ambiguous_ids",
    )
    for key in single_id_lists:
        filtered[key] = [
            item for item in trajectories.get(key, []) if (_record_series(item), str(item.get("product_id"))) not in pollution_ids
        ]
    filtered["title_alias_candidates"] = [
        item
        for item in trajectories.get("title_alias_candidates", [])
        if (_record_series(item), str(item.get("before_product_id"))) not in pollution_ids
        and (_record_series(item), str(item.get("after_product_id"))) not in pollution_ids
    ]
    filtered["per_comparison"] = list(trajectories.get("per_comparison", []))
    filtered["summary"] = {
        "matched_count": len(filtered["matched"]),
        "safe_matched_count": sum(bool(item.get("safe_for_trajectory")) for item in filtered["matched"]),
        "entry_count": len(filtered["entries"]),
        "exit_count": len(filtered["exits"]),
        "reentry_count": len(filtered["reentries"]),
        "platform_new_listed_count": len(filtered["platform_new_listed"]),
        "reuse_suspect_count": len(filtered["reuse_suspects"]),
        "title_alias_candidate_count": len(filtered["title_alias_candidates"]),
        "keyword_change_count": len(filtered["keyword_changes"]),
        "excluded_ambiguous_id_count": len(filtered["excluded_ambiguous_ids"]),
    }
    return filtered


def _record_series(record: Mapping[str, Any]) -> str:
    return str(record.get("series_id") or record.get("before_position", {}).get("series_id") or record.get("position", {}).get("series_id") or "")


def _attach_interval_observations(
    periods: Sequence[Mapping[str, Any]], trajectories: Mapping[str, Any]
) -> None:
    """把已计算区间变化连接回两端原始区间，供交付层直接展示。"""
    rows_by_island_and_id = {
        (str(period.get("island_id")), str(row.get("product_id"))): row
        for period in periods
        for row in period.get("rows", [])
        if row.get("product_id") not in (None, "")
    }
    for record in trajectories.get("matched", []):
        before_row = rows_by_island_and_id.get(
            (str(record.get("before_island")), str(record.get("product_id")))
        )
        after_row = rows_by_island_and_id.get(
            (str(record.get("after_island")), str(record.get("product_id")))
        )
        observations: dict[str, Any] = {}
        if before_row is not None and after_row is not None:
            for metric, change in record.get("interval_changes", {}).items():
                before = before_row.get(f"{metric}_interval")
                after = after_row.get(f"{metric}_interval")
                if before and after:
                    observations[metric] = {
                        "before": before,
                        "after": after,
                        "change": change,
                    }
        record["interval_observations"] = observations


def _polluted_record(record: Mapping[str, Any], sensitivity: Mapping[str, Any]) -> bool:
    return (_record_series(record), str(record.get("product_id"))) in {
        (str(item.get("series_id")), str(item.get("product_id"))) for item in sensitivity.get("evidence_first", [])
    }


def _sensitivity(periods: Sequence[Mapping[str, Any]], all_trajectories: Mapping[str, Any]) -> dict[str, Any]:
    evidence = _detect_pollution(periods)
    cleaned_periods = _clean_periods(periods, evidence)
    pollution_id_set = {str(item.get("product_id")) for item in evidence if item.get("product_id")}
    pollution_keys = {(str(item.get("series_id")), str(item.get("product_id"))) for item in evidence if item.get("product_id")}
    cleaned_trajectories = (
        _filter_trajectories_for_sensitivity(all_trajectories, pollution_keys) if evidence else dict(all_trajectories)
    )
    all_rows = sum(len(period.get("rows", [])) for period in periods)
    cleaned_rows = sum(len(period.get("rows", [])) for period in cleaned_periods)
    difference = {
        "row_count": cleaned_rows - all_rows,
        "matched_count": cleaned_trajectories["summary"]["matched_count"]
        - all_trajectories["summary"]["matched_count"],
        "entry_count": cleaned_trajectories["summary"]["entry_count"]
        - all_trajectories["summary"]["entry_count"],
        "exit_count": cleaned_trajectories["summary"]["exit_count"]
        - all_trajectories["summary"]["exit_count"],
    }
    pollution_ids = sorted(pollution_id_set)
    return {
        "aggregation_scope": "文件处理计数，不代表共同市场；业务比较按各可比序列分别解释",
        "per_island": [{"position": _island_position(period), "all_row_count": len(period.get("rows", [])), "cleaned_row_count": len(cleaned.get("rows", []))} for period, cleaned in zip(periods, cleaned_periods)],
        "evidence_first": evidence,
        "pollution_product_ids": pollution_ids,
        "opportunity_product_ids_filtered": pollution_ids,
        "removed_silently": False,
        "cleaning_used_for_sensitivity_only": True,
        "all_data": {
            "row_count": all_rows,
            "matched_count": all_trajectories["summary"]["matched_count"],
            "entry_count": all_trajectories["summary"]["entry_count"],
            "exit_count": all_trajectories["summary"]["exit_count"],
        },
        "cleaned_view": {
            "row_count": cleaned_rows,
            "matched_count": cleaned_trajectories["summary"]["matched_count"],
            "entry_count": cleaned_trajectories["summary"]["entry_count"],
            "exit_count": cleaned_trajectories["summary"]["exit_count"],
        },
        "difference": difference,
        "sensitivity_flip": any(value != 0 for key, value in difference.items() if key != "row_count"),
        "confidence_adjustment": "有污染证据，机会置信度最多为低" if evidence else "无规则命中污染证据",
    }


def _is_consecutive_non_overlapping(periods: Sequence[Mapping[str, Any]]) -> bool:
    ordered = sorted(periods, key=_period_sort_key)
    if len(ordered) < 4:
        return False
    try:
        parsed_periods = [
            (date.fromisoformat(str(period["start_date"])), date.fromisoformat(str(period["end_date"])))
            for period in ordered
        ]
        pairs = [
            (date.fromisoformat(str(before["end_date"])), date.fromisoformat(str(after["start_date"])))
            for before, after in zip(ordered, ordered[1:])
        ]
    except (KeyError, TypeError, ValueError):
        return False
    lengths = {(end - start).days + 1 for start, end in parsed_periods if start <= end}
    return (
        len(lengths) == 1
        and len(parsed_periods) == len(ordered)
        and all(before_end < after_start and after_start - before_end == timedelta(days=1) for before_end, after_start in pairs)
    )


def _strong_trend_candidates(
    periods: Sequence[Mapping[str, Any]], trajectories: Mapping[str, Any], audit: Mapping[str, Any]
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for period in periods:
        grouped[_series_key(period)].append(period)
    reuse_keys = {
        (str(item.get("product_id")), str(item.get("before_period")), str(item.get("after_period")))
        for item in trajectories.get("reuse_suspects", [])
    }
    candidates: list[dict[str, Any]] = []
    comparable_pairs = {
        (str(item.get("before_island")), str(item.get("after_island")))
        for item in audit.get("comparisons", [])
        if item.get("comparable")
    }
    for series, group in grouped.items():
        ordered = sorted(group, key=_period_sort_key)
        if len(ordered) < 4 or not _is_consecutive_non_overlapping(ordered):
            continue
        if any(
            (str(before.get("island_id")), str(after.get("island_id"))) not in comparable_pairs
            for before, after in zip(ordered, ordered[1:])
        ):
            continue
        common_k = min(int(period.get("top_n") or 0) for period in ordered)
        if common_k <= 0:
            continue
        row_maps = [
            {
                product_id: matching_rows[0]
                for product_id, matching_rows in (
                    (
                        product_id,
                        [
                            row
                            for row in period.get("rows", [])
                            if str(row.get("product_id") or "") == product_id
                            and isinstance(row.get("rank"), int)
                            and int(row["rank"]) <= common_k
                        ],
                    )
                    for product_id in {
                        str(row.get("product_id"))
                        for row in period.get("rows", [])
                        if row.get("product_id") and isinstance(row.get("rank"), int) and int(row["rank"]) <= common_k
                    }
                )
                if len(matching_rows) == 1
            }
            for period in ordered
        ]
        common_ids = set.intersection(*(set(row_map) for row_map in row_maps)) if row_maps else set()
        for product_id in sorted(common_ids):
            rows = [row_map[product_id] for row_map in row_maps]
            if any(_pollution_reason(row, str(period.get("category") or "")) for row, period in zip(rows, ordered)):
                continue
            if any(
                (product_id, str(before.get("period")), str(after.get("period"))) in reuse_keys
                for before, after in zip(ordered, ordered[1:])
            ):
                continue
            rank_deltas = [int(before["rank"]) - int(after["rank"]) for before, after in zip(rows, rows[1:])]
            if all(delta >= 0 for delta in rank_deltas) and any(delta > 0 for delta in rank_deltas):
                rank_direction = "up"
                expected_metric_direction = "increase"
            elif all(delta <= 0 for delta in rank_deltas) and any(delta < 0 for delta in rank_deltas):
                rank_direction = "down"
                expected_metric_direction = "decrease"
            else:
                continue
            supporting_metrics: list[str] = []
            for metric in ("buyers", "visitors", "payment_amount"):
                changes = []
                for before, after in zip(rows, rows[1:]):
                    before_interval = before.get(f"{metric}_interval")
                    after_interval = after.get(f"{metric}_interval")
                    if not before_interval or not after_interval:
                        changes = []
                        break
                    before_lower, before_upper = before_interval.get("lower"), before_interval.get("upper")
                    after_lower, after_upper = after_interval.get("lower"), after_interval.get("upper")
                    if None in {before_lower, before_upper, after_lower, after_upper}:
                        changes = []
                        break
                    if float(after_lower) > float(before_upper):
                        changes.append("increase")
                    elif float(after_upper) < float(before_lower):
                        changes.append("decrease")
                    else:
                        changes.append("overlap_or_uncertain")
                if changes and all(direction == expected_metric_direction for direction in changes):
                    supporting_metrics.append(metric)
            if len(supporting_metrics) >= 2:
                candidates.append(
                    {
                        "product_id": product_id,
                        "series_id": " | ".join(series),
                        "period_count": len(ordered),
                        "common_k": common_k,
                        "rank_direction": rank_direction,
                        "supporting_observed_metrics": supporting_metrics,
                        "classification": "较强趋势（仍非因果证据）",
                    }
                )
    return candidates


def _temporality(
    periods: Sequence[Mapping[str, Any]], audit: Mapping[str, Any], trajectories: Mapping[str, Any]
) -> dict[str, Any]:
    unique_periods = len({str(period.get("period")) for period in periods})
    comparable = [comparison for comparison in audit.get("comparisons", []) if comparison.get("comparable")]
    grouped: Counter[str] = Counter(str(period.get("series_id")) for period in periods)
    max_series_periods = max(grouped.values(), default=0)
    strong_candidates = _strong_trend_candidates(periods, trajectories, audit)
    if unique_periods <= 1:
        level = "snapshot"
        label = "单期快照/线索"
    elif not comparable:
        level = "incomparable_multi_period"
        label = "多期输入但口径不可比，不能形成纵向变化信号"
    elif strong_candidates:
        level = "strong_trend"
        label = "较强趋势（四个以上连续可比不重叠周期，且两个观测指标同向）"
    elif max_series_periods == 2:
        level = "short_signal"
        label = "短期变化信号"
    else:
        level = "trend_candidate"
        label = "趋势候选（未满足较强趋势门槛）"
    different_lengths = any(not item.get("same_period_length", True) for item in comparable)
    if different_lengths:
        label += "；异长周期，仅序数对照；趋势候选待补同长周期"
    return {
        "period_count": unique_periods,
        "max_comparable_series_periods": max_series_periods,
        "level": level,
        "label": label,
        "strong_trend": bool(strong_candidates),
        "strong_trend_candidates": strong_candidates,
        "causality_proven": False,
        "different_period_lengths": different_lengths,
    }


def _capability_gaps(periods: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    rows = [row for period in periods for row in period.get("rows", [])]
    gaps: list[dict[str, str]] = []
    rules = (
        ("price", "NO_PRICE", "缺少价格，不能做价格带分析"),
        ("payment_amount", "NO_PAYMENT_AMOUNT", "缺少支付金额，不能推算GMV或销售额"),
        ("cost", "NO_COST", "缺少成本，不能判断利润"),
    )
    for metric, code, message in rules:
        if not rows or not any(row.get(f"{metric}_raw") not in (None, "") for row in rows):
            gaps.append({"code": code, "message": message})
    if rows and any(
        row.get(f"{metric}_interval")
        and row[f"{metric}_interval"].get("midpoint_is_estimate")
        for row in rows
        for metric in ("buyers", "visitors", "payment_amount", "price")
    ):
        gaps.append({"code": "INTERVAL_ONLY", "message": "买家/访客等为区间，只能做上下界运算；中点仅为估算"})
    return gaps


def _own_positioning(
    periods: Sequence[Mapping[str, Any]],
    own_store: str | Sequence[str] | None,
    own_product_ids: Sequence[str] | None,
    ranking_trajectories: Mapping[str, Any],
) -> dict[str, Any]:
    if isinstance(own_store, str):
        stores = [own_store]
    else:
        stores = list(own_store or [])
    def normalise_store(value: Any) -> str:
        return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or "")).strip().lower())

    store_tokens = [normalise_store(store) for store in stores if store and store.strip()]
    own_ids = {str(product_id) for product_id in (own_product_ids or [])}
    matches: list[dict[str, Any]] = []
    store_name_candidates: list[dict[str, Any]] = []
    missing_windows: list[dict[str, Any]] = []
    reuse_ids = {str(item.get("product_id")) for item in ranking_trajectories.get("reuse_suspects", [])}
    reuse_keys = {(_record_series(item), str(item.get("product_id"))) for item in ranking_trajectories.get("reuse_suspects", [])}
    for period in periods:
        period_match_count = 0
        id_counts = Counter(str(row.get("product_id") or "") for row in period.get("rows", []))
        for row in period.get("rows", []):
            shop = normalise_store(row.get("shop"))
            product_id = str(row.get("product_id") or "")
            reused_here = (str(period.get("series_id")), product_id) in reuse_keys
            exact_store_match = bool(store_tokens and shop in store_tokens)
            if store_tokens and not exact_store_match and any(token in shop or shop in token for token in store_tokens if shop):
                store_name_candidates.append(
                    {
                        "shop": row.get("shop"),
                        "product_id": product_id,
                        "island_id": period.get("island_id"),
                        "classification": "近似店名候选，不自动认定为自有商品",
                    }
                )
            if exact_store_match or product_id in own_ids:
                period_match_count += 1
                matches.append(
                    {
                        "product_id": product_id,
                        "title": row.get("title"),
                        "shop": row.get("shop"),
                        "island_id": period.get("island_id"),
                        "period": period.get("period"),
                        "rank": row.get("rank"),
                        "buyers_interval": row.get("buyers_interval"),
                        "visitors_interval": row.get("visitors_interval"),
                        "price_interval": row.get("price_interval"),
                        "safe_for_positioning": bool(product_id) and id_counts[product_id] == 1 and not reused_here,
                        "identity_limitation": "缺失或重复ID，不能作为可靠商品定位" if not product_id or id_counts[product_id] > 1 else None,
                        "reuse_limitation": "疑似链接复用，阻断同一商品轨迹" if reused_here else None,
                        "position": _row_position(row),
                    }
                )
        if (store_tokens or own_ids) and period_match_count == 0:
            missing_windows.append(
                {
                    "period": period.get("period"),
                    "island_id": period.get("island_id"),
                    "top_n": period.get("top_n"),
                    "classification": "未出现在所给Top-N窗口；不等于下架或销量为零",
                }
            )
    safe_matches = [item for item in matches if item["safe_for_positioning"]]
    by_product: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in matches:
        by_product[str(item["product_id"])].append(
            {
                "period": item["period"],
                "island_id": item["island_id"],
                "rank": item["rank"],
                "buyers_interval": item["buyers_interval"],
                "visitors_interval": item["visitors_interval"],
                "price_interval": item["price_interval"],
                "safe_for_positioning": item["safe_for_positioning"],
            }
        )
    provided = bool(store_tokens or own_ids)
    if not provided:
        limitation = "未提供用户店铺或商品ID，不能定位自有商品"
    elif not matches:
        limitation = "用户指定商品或店铺未出现在所给Top-N窗口；不能据此声称下架或销量为零"
    elif reuse_ids & {str(item["product_id"]) for item in matches}:
        limitation = "自有商品命中疑似链接复用，阻断同一商品轨迹与放量建议"
    elif missing_windows:
        limitation = "用户指定商品或店铺在部分周期未出现在所给Top-N窗口；不能据此声称下架、销量为零或建议放量"
    else:
        limitation = "排名定位仅限所给Top-N窗口，不构成放量、库存或利润依据"
    return {
        "provided": provided,
        "store_terms": stores,
        "product_ids": sorted(own_ids),
        "matches": matches,
        "match_count": len(matches),
        "safe_match_count": len(safe_matches),
        "blocked_reuse_ids": sorted(reuse_ids & {str(item["product_id"]) for item in matches}),
        "store_name_candidates": store_name_candidates,
        "rank_interval_trajectories": dict(by_product),
        "missing_windows": missing_windows,
        "not_in_given_top_n_window": bool(missing_windows),
        "limitation": limitation,
    }


def _facts(
    periods: Sequence[Mapping[str, Any]],
    structure: Mapping[str, Any],
    trajectories: Mapping[str, Any],
    sensitivity: Mapping[str, Any],
    temporality: Mapping[str, Any],
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    if structure.get("periods"):
        period_parts = [
            f"{item['period']} {item['row_count']}行/Top-{item['top_n']}"
            for item in structure["periods"]
        ]
        facts.append(
            {
                "code": "LIST_STRUCTURE",
                "observation": "；".join(period_parts),
                "data_position_and_definition": [_island_position(period) for period in periods],
                "limitation": "行数与排名不代表销量或市场份额",
            }
        )
    if sensitivity.get("evidence_first"):
        facts.append(
            {
                "code": "POLLUTION_SENSITIVITY",
                "observation": f"发现 {len(sensitivity['evidence_first'])} 条错类或专拍链接证据，已保留全量并另做清洗敏感性对照",
                "data_position_and_definition": [item["position"] for item in sensitivity["evidence_first"]],
                "limitation": "规则命中是污染候选，需要人工复核；污染商品ID已从机会与动作base中排除",
            }
        )
    comparable = [item for item in trajectories.get("per_comparison", []) if not item.get("skipped")]
    if comparable:
        item = comparable[-1]
        facts.append(
            {
                "code": "WINDOW_CHURN",
                "observation": (
                    f"{item['before_period']}→{item['after_period']} 在共同Top-{item['common_k']}内："
                    f"共同ID {item['matched_count']}，进入 {item['entry_count']}，退出 {item['exit_count']}，"
                    f"Top20重合 {item['top20_overlap_count']}"
                ),
                "data_position_and_definition": {"before": item["before_position"], "after": item["after_position"], "common_k": item["common_k"], "formula": "shared=before_ids & after_ids; entry=after_ids-before_ids; exit=before_ids-after_ids", "same_period_length": item.get("same_period_length")},
                "limitation": "退出只表示退出所给Top-N窗口；不等于下架或销量为零",
            }
        )
    pollution_ids = set(sensitivity.get("pollution_product_ids", []))
    safe_moves = [
        record
        for record in trajectories.get("matched", [])
        if record.get("safe_for_trajectory") and not _polluted_record(record, sensitivity)
    ]
    if safe_moves:
        top_moves = sorted(safe_moves, key=lambda item: abs(int(item["rank_delta"])), reverse=True)[:3]
        facts.append(
            {
                "code": "RANK_MOVES",
                "observation": [
                    {"product_id": item["product_id"], "rank_delta": item["rank_delta"], "direction": item["direction"]}
                    for item in top_moves
                ],
                "data_position_and_definition": [{"before": item["before_position"], "after": item["after_position"], "formula": "rank_delta=前期排名-本期排名，正数为上升"} for item in top_moves],
                "limitation": "名次差不能线性解释销量差，也不能证明变化原因",
            }
        )
    facts.append(
        {
            "code": "TEMPORALITY",
            "observation": temporality["label"],
            "data_position_and_definition": {"islands": [_island_position(period) for period in periods], "formula": "按可比序列分别计数，不把多岛视为同一市场", "period_count": temporality["period_count"]},
            "limitation": "排名始终不能单独证明原因",
        }
    )
    return facts


def _chain(
    code: str,
    confidence: str,
    observation: Any,
    position: Any,
    pattern: str,
    explanation: str,
    alternative: str,
    hypothesis: str,
    action: str,
    metrics: Sequence[str],
    cycle: str,
    stop: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "confidence": confidence,
        "observation_fact": observation,
        "data_position_and_definition": position,
        "change_pattern": pattern,
        "possible_explanation": explanation,
        "alternative_explanation_or_limitation": alternative,
        "opportunity_hypothesis": hypothesis,
        "action": action,
        "validation": {"metrics": list(metrics), "cycle": cycle, "stop_condition": stop},
        "is_hypothesis_not_decision": True,
    }


def _opportunities(
    periods: Sequence[Mapping[str, Any]],
    trajectories: Mapping[str, Any],
    temporality: Mapping[str, Any],
    structure: Mapping[str, Any],
    audit: Mapping[str, Any],
    sensitivity: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if audit.get("status") == "blocking":
        return [
            _chain(
                "REPAIR_DATA_FIRST",
                "低",
                audit.get("conclusion"),
                [issue.get("evidence") for issue in audit.get("issues", []) if issue.get("severity") == "error"],
                "输入结构阻断比较",
                "修复主键、排名或周期口径后才可能形成可靠信号",
                "当前可见差异也可能完全由脏数据造成",
                "先修复数据契约能降低后续打品误判",
                "按审计证据修正输入并重跑，不扩库存、不重投资源、不正式立项",
                ("阻断错误数", "重复ID/排名数", "可比较岛数量"),
                "本次数据修复后立即复核",
                "仍有阻断错误或无法确认口径时停止业务判断",
            )
        ]

    pollution_ids = set(sensitivity.get("pollution_product_ids", []))
    confidence = (
        "低"
        if pollution_ids or temporality.get("different_period_lengths") or temporality["level"] in {"snapshot", "incomparable_multi_period"}
        else "中"
    )
    opportunities: list[dict[str, Any]] = []
    comparable = [item for item in trajectories.get("per_comparison", []) if not item.get("skipped")]
    reuse_keys = {
        (str(item.get("series_id")), str(item.get("product_id")))
        for item in trajectories.get("reuse_suspects", [])
        if item.get("product_id") not in (None, "")
    }
    entry_item: Mapping[str, Any] | None = None
    eligible_entries: list[dict[str, Any]] = []
    for item in reversed(comparable):
        candidates = [
            entry
            for entry in trajectories.get("entries", [])
            if entry.get("before_island") == item.get("before_island")
            and entry.get("after_island") == item.get("after_island")
            and not _polluted_record(entry, sensitivity)
            and (_record_series(entry), str(entry.get("product_id"))) not in reuse_keys
        ]
        if candidates:
            entry_item = item
            eligible_entries = candidates
            break
    if entry_item is not None:
        candidate_objects = [
            {
                "product_id": entry.get("product_id"),
                "rank": entry.get("rank"),
                "classification": entry.get("classification"),
                "position": entry.get("position"),
            }
            for entry in eligible_entries[:5]
        ]
        opportunity = _chain(
                "COMMON_WINDOW_ENTRY_TEST",
                confidence,
                {
                    "safe_entry_count": len(eligible_entries),
                    "candidate_product_ids": [item["product_id"] for item in candidate_objects],
                    "exit_count": entry_item["exit_count"],
                },
                {"before": entry_item["before_position"], "after": entry_item["after_position"], "candidate_positions": [item["position"] for item in candidate_objects], "common_k": entry_item["common_k"], "formula": "entry=after_ids-before_ids; exit=before_ids-after_ids", "same_period_length": entry_item.get("same_period_length")},
                temporality["label"],
                "部分商品方向可能正在获得短期可见度",
                "也可能是活动、供给波动、榜单算法或Top-N截断造成",
                "从进入窗口商品中抽取少量方向做样品/卖点验证，可能发现可测试机会",
                "仅建立候选清单并补充价格、评价、供应链证据，不直接扩库存或立项",
                ("后续共同Top-K留存", "连续周期排名方向", "样品反馈"),
                "至少2个后续连续可比周期",
                "候选退出共同窗口、方向反转或补充证据不支持时停止",
            )
        opportunity["candidate_objects"] = candidate_objects
        opportunities.append(opportunity)
    safe_up = [
        record
        for record in trajectories.get("matched", [])
        if record.get("safe_for_trajectory")
        and not _polluted_record(record, sensitivity)
        and int(record.get("rank_delta") or 0) > 0
    ]
    if safe_up:
        top = max(safe_up, key=lambda item: int(item["rank_delta"]))
        opportunities.append(
            _chain(
                "RISING_LINK_ATTRIBUTE_TEST",
                confidence,
                {"product_id": top["product_id"], "rank_delta": top["rank_delta"]},
                {"before": top["before_position"], "after": top["after_position"]},
                temporality["label"],
                "该链接的标题显式属性或商品呈现可能值得进一步验证",
                "名次变化也可能来自活动、库存、流量或平台机制，且商品ID不代表SKU；污染ID已排除",
                "围绕该链接的显式属性做对照素材/概念测试，可能验证一个研发或主推方向",
                "建立单变量对照，不复制商品、不假定消费者需求",
                ("后续排名方向", "概念点击/选择率", "定性反馈"),
                "1个概念测试周期并观察2个榜单周期",
                "对照无提升、链接疑似复用或后续排名反转时停止",
            )
        )
    first_attributes = next(
        (item.get("title_explicit_attributes", []) for item in reversed(structure.get("periods", [])) if item.get("title_explicit_attributes")),
        [],
    )
    attribute_period = next((item for item in reversed(structure.get("periods", [])) if item.get("title_explicit_attributes")), None)
    attribute_source = {"source": "商品标题显式提及", "position": attribute_period["data_position_and_definition"] if attribute_period else None}
    if not first_attributes:
        first_attributes = next(
            (
                item.get("keyword_explicit_attributes", [])
                for item in reversed(structure.get("periods", []))
                if item.get("keyword_explicit_attributes")
            ),
            [],
        )
        attribute_period = next((item for item in reversed(structure.get("periods", [])) if item.get("keyword_explicit_attributes")), None)
        attribute_source = {"source": "商品关键词显式字段（非标题、非需求）", "position": attribute_period["data_position_and_definition"] if attribute_period else None}
    if first_attributes:
        attributes = [item["attribute"] for item in first_attributes[:3]]
        opportunities.append(
            _chain(
                "EXPLICIT_ATTRIBUTE_TEST",
                "低",
                {"title_explicit_mentions": attributes},
                attribute_source,
                "横截面显式字段集中",
                "这些属性可能是商家常用表达",
                "标题词不等于消费者需求，也可能只是SEO惯例",
                "把高频显式属性作为访谈/素材A-B的待证假设，而不是需求结论",
                "选择1个属性做小样或内容对照，完整产品定义转交sg-product",
                ("概念选择率", "反馈中自发表达占比", "对照差异"),
                "1个小样或内容测试周期",
                "用户反馈不自发提及或对照无差异时停止",
            )
        )
    if not opportunities:
        opportunities.append(
            _chain(
                "SNAPSHOT_STRUCTURE_TEST",
                "低",
                temporality["label"],
                [_island_position(period) for period in periods],
                "仅横截面结构",
                "头部店铺或显式属性可能提供候选方向",
                "单期快照不能证明纵向趋势、需求或因果",
                "先补齐下一连续周期并预注册待观察指标",
                "记录候选，不扩库存、不重投资源、不正式立项",
                ("下一周期Top-K留存", "店铺结构变化", "显式属性变化"),
                "至少1个后续连续可比周期",
                "口径不一致或候选未复现时停止",
            )
        )
    return opportunities[:3]


def _action_from_base(base: Mapping[str, Any], domain: str) -> dict[str, Any]:
    action_text = {
        "product_selection": "把证据对应方向放入小规模打品候选池，先补利润与供应链门槛，不扩库存。",
        "product_development": "只做一个可逆的小样/概念验证；完整产品定义与研发方案转交sg-product。",
        "main_promotion": "仅做内容与卖点的小流量验证；ROI、CPC和出价诊断转交sg-tmads-report。",
    }[domain]
    copied = dict(base)
    copied["domain"] = domain
    copied["action"] = action_text
    copied["validation"] = dict(base["validation"])
    if domain == "main_promotion":
        copied["validation"]["metrics"] = ["素材点击/互动差异", "落地页行为", "后续榜单方向"]
        durations = sorted({item["duration_days"] for item in copied["validation"].get("cycle_basis", []) if item.get("duration_days")})
        window_note = f"输入统计窗口天数={durations}（不等于更新频率）；" if durations else "输入更新频率未知；"
        copied["validation"]["cycle"] = window_note + "按已确认榜单更新频率观察后续可比周期；测试时长和样本门槛须结合用户机制预登记，未知时先确认后启动"
        copied["validation"]["stop_condition"] = "素材对照无差异、口径失效或需进入投放优化时停止并让位"
    return copied


def _max_limitation(periods: Sequence[Mapping[str, Any]], temporality: Mapping[str, Any], gaps: Sequence[Mapping[str, Any]]) -> str:
    scopes = {str(period.get("scope")) for period in periods}
    shop_types = {str(row.get("shop_type")) for period in periods for row in period.get("rows", []) if row.get("shop_type")}
    if "全网" in scopes and {"天猫", "淘宝"}.issubset(shop_types):
        return "样本范围为全网且同时含天猫/淘宝，不能冒充纯天猫样本；排名也不能证明销量、份额或原因。"
    if temporality["level"] == "snapshot":
        return "只有单期快照，只能报告结构线索，不能声称纵向趋势或变化原因。"
    if temporality["level"] == "incomparable_multi_period":
        return "多期口径不可比，禁止跨岛合并为变化或趋势。"
    if any(gap.get("code") == "NO_PAYMENT_AMOUNT" for gap in gaps):
        return "缺少支付金额且排名为序数，不能推算GMV、销量份额或利润。"
    return "榜单排名是Top-N序数观察，不能单独证明需求、销量规模或因果。"


def _count_forbidden_keys(value: Any, forbidden: set[str]) -> int:
    if isinstance(value, Mapping):
        return sum(key in forbidden for key in value) + sum(_count_forbidden_keys(item, forbidden) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return sum(_count_forbidden_keys(item, forbidden) for item in value)
    return 0


def _advice_text(result: Mapping[str, Any]) -> str:
    return json.dumps(
        {"facts": result.get("facts", []), "opportunities": result.get("opportunities", []), "actions": result.get("actions", {})},
        ensure_ascii=False,
        default=str,
    )


def _unnegated_phrase_count(text: str, phrases: Sequence[str]) -> int:
    count = 0
    for phrase in phrases:
        for match in re.finditer(re.escape(phrase), text):
            prefix = text[max(0, match.start() - 6) : match.start()]
            if not any(negation in prefix for negation in ("不", "不得", "不能", "禁止", "避免", "停止", "拒绝")):
                count += 1
    return count


def validate_result_guards(result: Mapping[str, Any]) -> dict[str, int]:
    """从实际输出结构重算六类严重错误，供 runner 独立断言。"""
    trajectories = result.get("trajectories", {})
    island_series = {
        str(item.get("island_id")): str(item.get("series_id"))
        for item in result.get("comparability", {}).get("islands", [])
    }
    cross_island_matches = sum(
        bool(item.get("before_island"))
        and bool(item.get("after_island"))
        and island_series.get(str(item.get("before_island")))
        != island_series.get(str(item.get("after_island")))
        for item in trajectories.get("matched", [])
    )
    reuse_ids = {str(item.get("product_id")) for item in trajectories.get("reuse_suspects", [])}
    reuse_keys = {(_record_series(item), str(item.get("product_id"))) for item in trajectories.get("reuse_suspects", [])}
    unsafe_reuse_matches = sum(
        (str(item.get("product_id")) in reuse_ids if not _record_series(item) else (_record_series(item), str(item.get("product_id"))) in reuse_keys) and bool(item.get("safe_for_trajectory"))
        for item in trajectories.get("matched", [])
    )
    ambiguous_ids = {
        str(item.get("product_id"))
        for item in trajectories.get("excluded_ambiguous_ids", [])
        if item.get("product_id")
    }
    ambiguous_keys = {(_record_series(item), str(item.get("product_id"))) for item in trajectories.get("excluded_ambiguous_ids", []) if item.get("product_id")}
    ambiguous_leaks = sum(
        (str(item.get("product_id")) in ambiguous_ids if not _record_series(item) else (_record_series(item), str(item.get("product_id"))) in ambiguous_keys)
        for key in ("matched", "entries", "exits", "reentries")
        for item in trajectories.get(key, [])
    )
    exit_wording_errors = sum(
        not str(item.get("classification") or "").startswith("退出所给 Top-")
        or not bool(item.get("not_delisted_or_zero_sales"))
        for item in trajectories.get("exits", [])
    )
    opportunity_chains = list(result.get("opportunities", [])) + [
        item for item in result.get("actions", {}).values() if isinstance(item, Mapping)
    ]
    required_chain_fields = {
        "observation_fact",
        "data_position_and_definition",
        "change_pattern",
        "possible_explanation",
        "alternative_explanation_or_limitation",
        "opportunity_hypothesis",
        "action",
        "validation",
    }
    hypothesis_errors = sum(
        not required_chain_fields.issubset(item) or not isinstance(item.get("validation"), Mapping)
        for item in opportunity_chains
    )
    advice_text = _advice_text(result)
    decision_language = _unnegated_phrase_count(advice_text, ("扩库存", "重投资源", "正式立项"))
    fabricated_text_claims = sum(
        len(re.findall(pattern, advice_text, re.I))
        for pattern in (
            r"(?:销量|销售量)\s*(?:为|=|约)\s*\d",
            r"市场份额\s*(?:为|=|约)\s*\d",
            r"GMV\s*(?:为|=|约)\s*[¥￥]?\d",
            r"销售额\s*(?:为|=|约)\s*[¥￥]?\d",
        )
    )
    fabricated_text_claims += _unnegated_phrase_count(
        advice_text, ("GMV", "市场份额", "销量", "销售额")
    )
    temporality = result.get("temporality", {})
    single_period_error = int(
        int(temporality.get("period_count") or 0) <= 1
        and temporality.get("level") not in {"snapshot", "rejected"}
    )
    return {
        "cross_island_merge": cross_island_matches,
        "single_period_as_trend": single_period_error,
        "out_of_window_as_delisted": exit_wording_errors,
        "product_mismatch": unsafe_reuse_matches + ambiguous_leaks,
        "fabricated_sales_share_gmv": _count_forbidden_keys(
            result, {"sales_volume", "market_share", "gmv", "gmv_estimate", "profit_estimate"}
        )
        + fabricated_text_claims,
        "hypothesis_as_decision": hypothesis_errors + decision_language,
    }


def analyze_periods(
    periods: Sequence[Mapping[str, Any]],
    audit: Mapping[str, Any] | None = None,
    *,
    own_store: str | Sequence[str] | None = None,
    own_product_ids: Sequence[str] | None = None,
    mode: str = "deep",
) -> dict[str, Any]:
    """返回 JSON 可序列化的完整机器证据；quick/deep 不隐藏审计字段。"""
    if mode not in {"quick", "deep"}:
        raise ValueError("mode 必须是 quick 或 deep")
    normalised = normalize_payload({"periods": list(periods)})
    normalised_periods = normalised["periods"]
    audit_result = dict(audit or audit_dataset(normalised))
    current_audit = audit_dataset(normalised)
    blocked_ids = {item["island_id"] for item in current_audit["islands"] if item["status"] == "blocking"}
    eligible_periods = [period for period in normalised_periods if period["island_id"] not in blocked_ids]
    # Keep the original timeline for matching: deleting a bad middle period must
    # never manufacture adjacency or reentry evidence between its neighbours.
    trajectories = match_periods(normalised_periods)
    _attach_interval_observations(normalised_periods, trajectories)
    structure = _structure(eligible_periods)
    sensitivity = _sensitivity(eligible_periods, trajectories)
    temporality = _temporality(eligible_periods, audit_result, trajectories)
    gaps = _capability_gaps(eligible_periods)
    own_positioning = _own_positioning(eligible_periods, own_store, own_product_ids, trajectories)
    facts = _facts(eligible_periods, structure, trajectories, sensitivity, temporality) if eligible_periods else []
    opportunity_audit = {**audit_result, "status": "degraded" if eligible_periods else "blocking"}
    opportunities = _opportunities(eligible_periods, trajectories, temporality, structure, opportunity_audit, sensitivity)
    for opportunity in opportunities:
        if opportunity["code"] != "REPAIR_DATA_FIRST":
            opportunity["validation"]["cycle_basis"] = [{**_island_position(period), "duration_days": (date.fromisoformat(period["end_date"]) - date.fromisoformat(period["start_date"])).days + 1 if period.get("start_date") and period.get("end_date") else None} for period in eligible_periods]
            opportunity["validation"]["threshold_source"] = "用户目标、历史基线或实验预登记；当前未提供，不编造通过阈值"
            opportunity["validation"]["prerequisites"] = ["确认榜单更新频率和同长可比窗口", "预登记样本量、通过门槛、实验周期和责任人", "补充用户利润、库存及供应约束后才可判断是否加码"]
    if blocked_ids and eligible_periods:
        repair = _opportunities([], trajectories, temporality, {}, {**audit_result, "status": "blocking"}, sensitivity)
        opportunities = repair + opportunities
    visible_facts = facts[:3] if mode == "quick" else facts
    visible_opportunities = opportunities[:3]
    base = next((item for item in visible_opportunities if item["code"] != "REPAIR_DATA_FIRST"), None)
    actions = {
        domain: _action_from_base(base, domain) if base is not None else None
        for domain in ("product_selection", "product_development", "main_promotion")
    }
    comparison_records = list(audit_result.get("comparisons", []))
    result: dict[str, Any] = {
        "mode": mode,
        "data_quality": {
            "status": audit_result.get("status"),
            "conclusion": audit_result.get("conclusion"),
            "one_sentence": audit_result.get("conclusion"),
        },
        "audit": audit_result,
        "analysis_scope": {"eligible_islands": list(dict.fromkeys(period["island_id"] for period in eligible_periods)), "blocked_islands": sorted(blocked_ids), "timeline_preserved": True},
        "comparability": {
            "islands": audit_result.get("islands", []),
            "island_count": len(audit_result.get("islands", [])),
            "comparisons": comparison_records,
            "comparable_count": sum(bool(item.get("comparable")) for item in comparison_records),
            "cross_island_merge_performed": False,
        },
        "temporality": temporality,
        "structure": {**structure, "own_product_positioning": own_positioning},
        "trajectories": trajectories,
        "sensitivity": sensitivity,
        "capability_gaps": gaps,
        "facts": visible_facts,
        "opportunities": visible_opportunities,
        "actions": actions,
        "max_limitation": ("阻断岛仅保留审计，不输出事实或业务动作；请修正排名和口径。" if not eligible_periods else ("异长周期仅作序数窗口对照，不能比较流量/金额增减；须补同长周期。" if temporality.get("different_period_lengths") else _max_limitation(eligible_periods, temporality, gaps))),
        "routes": {
            "status": "within_scope",
            "handoffs": [],
            "reason": "analyze_periods未接收请求文本；由analyze_payload执行相邻Skill路由",
        },
    }
    result["severe_error_guards"] = validate_result_guards(result)
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行确定性排名分析引擎")
    parser.add_argument("paths", nargs="+", help="一个或多个 XLSX/CSV/TSV 路径")
    parser.add_argument("--mode", choices=("quick", "deep"), default="deep")
    parser.add_argument("--own-store")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        isolated = load_inputs_isolated(args.paths)
        payload = isolated["payload"]
        if not payload.get("periods"):
            raise RankingInputError("所有输入文件均被拒绝")
        audit = audit_dataset(payload)
        result = analyze_periods(payload["periods"], audit, own_store=args.own_store, mode=args.mode)
        result["file_rejections"] = isolated["file_rejections"]
        if isolated["file_rejections"]:
            result["status"] = "partial"
    except (RankingInputError, OSError, ValueError) as exc:
        sys.stderr.write(f"分析失败：{exc}\n")
        return 2
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
