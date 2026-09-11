#!/usr/bin/env python3
"""按商品链接 ID 做跨期匹配，并保留错配保护证据。"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any, Mapping, Sequence

from audit_input import (
    RankingInputError,
    audit_dataset,
    build_comparisons,
    interval_change,
    merge_payloads,
    normalize_payload,
    load_input,
)


def _normalise_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE)


def _normalise_keywords(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def _row_position(row: Mapping[str, Any]) -> dict[str, Any]:
    source = row.get("_source") if isinstance(row.get("_source"), Mapping) else {}
    return {
        "file": source.get("file"),
        "sheet": source.get("sheet"),
        "row": source.get("row"),
        "island_id": source.get("island_id"),
        "series_id": source.get("series_id"),
        "rank": row.get("rank"),
    }


def _rows_by_id(
    period: Mapping[str, Any], common_k: int | None = None
) -> tuple[dict[str, Mapping[str, Any]], set[str], list[dict[str, Any]]]:
    candidates: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    missing: list[dict[str, Any]] = []
    for row in period.get("rows", []):
        product_id = str(row.get("product_id") or "")
        rank = row.get("rank")
        if not isinstance(rank, int):
            continue
        if not product_id:
            if common_k is None or rank <= common_k:
                missing.append(_row_position(row))
            continue
        candidates[product_id].append(row)
    duplicates = {product_id for product_id, rows in candidates.items() if len(rows) > 1}
    output = {
        product_id: rows[0]
        for product_id, rows in candidates.items()
        if len(rows) == 1 and (common_k is None or int(rows[0]["rank"]) <= common_k)
    }
    return output, duplicates, missing


def _period_lookup(periods: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(period.get("island_id")): period for period in periods}


def _reuse_evidence(
    product_id: str,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    comparison: Mapping[str, Any],
) -> dict[str, Any] | None:
    before_title = _normalise_text(before.get("title"))
    after_title = _normalise_text(after.get("title"))
    before_shop = _normalise_text(before.get("shop"))
    after_shop = _normalise_text(after.get("shop"))
    title_similarity = SequenceMatcher(None, before_title, after_title).ratio() if before_title and after_title else None
    shop_changed = bool(before_shop and after_shop and before_shop != after_shop)
    title_changed_substantially = title_similarity is not None and title_similarity < 0.45
    if not shop_changed and not title_changed_substantially:
        return None
    reasons: list[str] = []
    if shop_changed:
        reasons.append("shop_changed")
    if title_changed_substantially:
        reasons.append("title_changed_substantially")
    return {
        "product_id": product_id,
        "link_not_sku": True,
        "before_period": comparison["before_period"],
        "after_period": comparison["after_period"],
        "series_id": comparison["series_id"],
        "before_island": comparison["before_island"],
        "after_island": comparison["after_island"],
        "before_title": before.get("title"),
        "after_title": after.get("title"),
        "before_shop": before.get("shop"),
        "after_shop": after.get("shop"),
        "title_similarity": round(title_similarity, 4) if title_similarity is not None else None,
        "reasons": reasons,
        "classification": "疑似链接复用；不作为同一商品轨迹",
        "before_position": _row_position(before),
        "after_position": _row_position(after),
    }


def _title_alias_candidates(
    before_rows: Mapping[str, Mapping[str, Any]],
    after_rows: Mapping[str, Mapping[str, Any]],
    comparison: Mapping[str, Any],
) -> list[dict[str, Any]]:
    before_titles: dict[str, list[tuple[str, Mapping[str, Any]]]] = defaultdict(list)
    after_titles: dict[str, list[tuple[str, Mapping[str, Any]]]] = defaultdict(list)
    for product_id, row in before_rows.items():
        title = _normalise_text(row.get("title"))
        if title:
            before_titles[title].append((product_id, row))
    for product_id, row in after_rows.items():
        title = _normalise_text(row.get("title"))
        if title:
            after_titles[title].append((product_id, row))

    candidates: list[dict[str, Any]] = []
    for title in sorted(set(before_titles) & set(after_titles)):
        for before_id, before_row in before_titles[title]:
            for after_id, after_row in after_titles[title]:
                if before_id == after_id:
                    continue
                candidates.append(
                    {
                        "before_product_id": before_id,
                        "after_product_id": after_id,
                        "title": before_row.get("title"),
                        "same_shop": _normalise_text(before_row.get("shop")) == _normalise_text(after_row.get("shop")),
                        "before_period": comparison["before_period"],
                        "after_period": comparison["after_period"],
                        "classification": "同标题不同ID候选；禁止自动合并",
                        "before_position": _row_position(before_row),
                        "after_position": _row_position(after_row),
                    }
                )
    return candidates


def _matched_record(
    product_id: str,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    comparison: Mapping[str, Any],
    reuse: Mapping[str, Any] | None,
) -> dict[str, Any]:
    before_rank = int(before["rank"])
    after_rank = int(after["rank"])
    rank_delta = before_rank - after_rank
    if rank_delta > 0:
        direction = "up"
    elif rank_delta < 0:
        direction = "down"
    else:
        direction = "flat"
    interval_changes: dict[str, Any] = {}
    for metric in ("buyers", "visitors", "payment_amount", "price"):
        if metric != "price" and not comparison.get("same_period_length"):
            continue
        change = interval_change(before.get(f"{metric}_interval"), after.get(f"{metric}_interval"))
        if change is not None:
            interval_changes[metric] = change
    return {
        "product_id": product_id,
        "product_id_semantics": "商品链接ID，不代表SKU",
        "before_period": comparison["before_period"],
        "after_period": comparison["after_period"],
        "series_id": comparison["series_id"],
        "before_island": comparison["before_island"],
        "after_island": comparison["after_island"],
        "same_period_length": comparison.get("same_period_length"),
        "common_k": comparison["common_k"],
        "before_rank": before_rank,
        "after_rank": after_rank,
        "rank_delta": rank_delta,
        "rank_delta_definition": "前期排名-本期排名；正数为上升",
        "direction": direction,
        "rank_is_ordinal": True,
        "safe_for_trajectory": reuse is None,
        "title_changed": _normalise_text(before.get("title")) != _normalise_text(after.get("title")),
        "keywords_changed": _normalise_keywords(before.get("keywords")) != _normalise_keywords(after.get("keywords")),
        "interval_changes": interval_changes,
        "before_position": _row_position(before),
        "after_position": _row_position(after),
    }


def match_periods(periods: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """在同一可比序列内按字符串商品 ID 匹配相邻周期。"""
    normalised_periods = normalize_payload({"periods": list(periods)})["periods"]
    audit = audit_dataset({"periods": normalised_periods})
    comparisons = build_comparisons(normalised_periods, audit.get("issues", []))
    period_by_id = _period_lookup(normalised_periods)

    matched: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    exits: list[dict[str, Any]] = []
    reentries: list[dict[str, Any]] = []
    platform_new_listed: list[dict[str, Any]] = []
    reuse_suspects: list[dict[str, Any]] = []
    title_alias_candidates: list[dict[str, Any]] = []
    keyword_changes: list[dict[str, Any]] = []
    excluded_ambiguous_ids: list[dict[str, Any]] = []
    per_comparison: list[dict[str, Any]] = []
    seen_by_series: dict[str, set[str]] = defaultdict(set)
    history_rows: dict[str, dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]]] = defaultdict(dict)
    history_window: dict[str, int] = {}
    ambiguous_by_series: dict[str, set[str]] = defaultdict(set)
    for period in normalised_periods:
        _, duplicate_ids, _ = _rows_by_id(period)
        ambiguous_by_series[str(period["series_id"])].update(duplicate_ids)

    for comparison in comparisons:
        if not comparison["comparable"]:
            seen_by_series[comparison["series_id"]].clear()
            history_rows[comparison["series_id"]].clear()
            per_comparison.append({**comparison, "matched_count": 0, "entry_count": 0, "exit_count": 0, "skipped": True})
            continue
        before_period = period_by_id[str(comparison["before_island"])]
        after_period = period_by_id[str(comparison["after_island"])]
        common_k = int(comparison["common_k"])
        before_rows, before_duplicates, before_missing = _rows_by_id(before_period, common_k)
        after_rows, after_duplicates, after_missing = _rows_by_id(after_period, common_k)
        ambiguous_ids = before_duplicates | after_duplicates | ambiguous_by_series[comparison["series_id"]]
        for product_id in ambiguous_ids:
            before_rows.pop(product_id, None)
            after_rows.pop(product_id, None)
        for product_id in sorted(ambiguous_ids):
            excluded_ambiguous_ids.append(
                {
                    "product_id": product_id,
                    "before_period": comparison["before_period"],
                    "after_period": comparison["after_period"],
                    "series_id": comparison["series_id"],
                    "before_island": comparison["before_island"],
                    "after_island": comparison["after_island"],
                    "reason": "duplicate_product_id_excluded_not_first_wins",
                }
            )
        for position in before_missing + after_missing:
            excluded_ambiguous_ids.append(
                {
                    "product_id": None,
                    "before_period": comparison["before_period"],
                    "after_period": comparison["after_period"],
                    "reason": "missing_product_id_excluded",
                    "position": position,
                }
            )
        before_ids = set(before_rows)
        after_ids = set(after_rows)
        shared_ids = before_ids & after_ids
        entered_ids = after_ids - before_ids
        exited_ids = before_ids - after_ids
        comparison_reuse_ids: set[str] = set()

        for product_id in sorted(shared_ids):
            before_row = before_rows[product_id]
            after_row = after_rows[product_id]
            reuse = _reuse_evidence(product_id, before_row, after_row, comparison)
            if reuse:
                reuse_suspects.append(reuse)
                comparison_reuse_ids.add(product_id)
            record = _matched_record(product_id, before_row, after_row, comparison, reuse)
            matched.append(record)
            if record["keywords_changed"]:
                keyword_changes.append(
                    {
                        "product_id": product_id,
                        "before_period": comparison["before_period"],
                        "after_period": comparison["after_period"],
                        "before_keywords": before_row.get("keywords"),
                        "after_keywords": after_row.get("keywords"),
                        "before_position": _row_position(before_row),
                        "after_position": _row_position(after_row),
                    }
                )

        prior_seen = seen_by_series[comparison["series_id"]]
        prior_rows = history_rows[comparison["series_id"]]
        if history_window.get(comparison["series_id"], common_k) != common_k or not comparison.get("continuous") or not comparison.get("same_period_length"):
            prior_seen.clear()
            prior_rows.clear()
        history_window[comparison["series_id"]] = common_k
        for product_id in sorted(entered_ids):
            row = after_rows[product_id]
            entry = {
                "product_id": product_id,
                "period": comparison["after_period"],
                "series_id": comparison["series_id"],
                "before_island": comparison["before_island"],
                "after_island": comparison["after_island"],
                "rank": row.get("rank"),
                "common_k": common_k,
                "classification": f"进入共同 Top-{common_k} 窗口",
                "not_equivalent_to_platform_new": True,
                "position": _row_position(row),
            }
            entries.append(entry)
            if product_id in prior_seen:
                earlier_row, earlier_period = prior_rows[product_id]
                history_comparison = {**comparison, "before_period": earlier_period["period"], "before_island": earlier_period["island_id"]}
                reuse = _reuse_evidence(product_id, earlier_row, row, history_comparison)
                if reuse:
                    reuse_suspects.append(reuse)
                else:
                    reentries.append({**entry, "classification": f"回到共同 Top-{common_k} 窗口", "earlier_position": _row_position(earlier_row)})
        for product_id in sorted(exited_ids):
            row = before_rows[product_id]
            exits.append(
                {
                    "product_id": product_id,
                    "period": comparison["after_period"],
                    "series_id": comparison["series_id"],
                    "before_island": comparison["before_island"],
                    "after_island": comparison["after_island"],
                    "previous_rank": row.get("rank"),
                    "common_k": common_k,
                    "classification": f"退出所给 Top-{common_k} 窗口",
                    "not_delisted_or_zero_sales": True,
                    "position": _row_position(row),
                }
            )
        for product_id, row in sorted(after_rows.items()):
            if "新上榜" in str(row.get("trend") or ""):
                platform_new_listed.append(
                    {
                        "product_id": product_id,
                        "period": comparison["after_period"],
                        "rank": row.get("rank"),
                        "source_field": "trend",
                        "classification": "平台字段标记新上榜",
                        "position": _row_position(row),
                    }
                )
        title_alias_candidates.extend(_title_alias_candidates(before_rows, after_rows, comparison))
        top20_k = min(common_k, 20)
        before_top20 = {product_id for product_id, row in before_rows.items() if int(row["rank"]) <= top20_k}
        after_top20 = {product_id for product_id, row in after_rows.items() if int(row["rank"]) <= top20_k}
        per_comparison.append(
            {
                **comparison,
                "matched_count": len(shared_ids),
                "safe_matched_count": len(shared_ids - comparison_reuse_ids),
                "before_valid_id_count": len(before_ids),
                "after_valid_id_count": len(after_ids),
                "excluded_ambiguous_id_count": len(ambiguous_ids),
                "before_position": {"file": before_period.get("source_file"), "sheet": before_period.get("sheet"), "island_id": before_period.get("island_id"), "denominator": len(before_ids), "filter": f"unique nonmissing ID, rank <= {common_k}"},
                "after_position": {"file": after_period.get("source_file"), "sheet": after_period.get("sheet"), "island_id": after_period.get("island_id"), "denominator": len(after_ids), "filter": f"unique nonmissing ID, rank <= {common_k}"},
                "entry_count": len(entered_ids),
                "exit_count": len(exited_ids),
                "top20_overlap_count": len(before_top20 & after_top20),
                "platform_new_listed_count": sum(
                    "新上榜" in str(row.get("trend") or "") for row in after_rows.values()
                ),
                "keyword_change_count": sum(
                    _normalise_keywords(before_rows[product_id].get("keywords"))
                    != _normalise_keywords(after_rows[product_id].get("keywords"))
                    for product_id in shared_ids
                ),
                "skipped": False,
            }
        )
        prior_seen.update(before_ids)
        prior_seen.update(after_ids)
        prior_rows.update({product_id: (row, before_period) for product_id, row in before_rows.items()})
        prior_rows.update({product_id: (row, after_period) for product_id, row in after_rows.items()})

    reuse_keys = {(item["series_id"], item["product_id"]) for item in reuse_suspects}
    for record in matched:
        if (record["series_id"], record["product_id"]) in reuse_keys:
            record["safe_for_trajectory"] = False
    reentries = [item for item in reentries if (item["series_id"], item["product_id"]) not in reuse_keys]
    for comparison in per_comparison:
        if not comparison.get("skipped"):
            comparison["safe_matched_count"] = sum(record["safe_for_trajectory"] for record in matched if record["before_island"] == comparison["before_island"] and record["after_island"] == comparison["after_island"])

    return {
        "matched": matched,
        "entries": entries,
        "exits": exits,
        "reentries": reentries,
        "platform_new_listed": platform_new_listed,
        "reuse_suspects": reuse_suspects,
        "title_alias_candidates": title_alias_candidates,
        "keyword_changes": keyword_changes,
        "excluded_ambiguous_ids": excluded_ambiguous_ids,
        "per_comparison": per_comparison,
        "summary": {
            "matched_count": len(matched),
            "safe_matched_count": sum(bool(record["safe_for_trajectory"]) for record in matched),
            "entry_count": len(entries),
            "exit_count": len(exits),
            "reentry_count": len(reentries),
            "platform_new_listed_count": len(platform_new_listed),
            "reuse_suspect_count": len(reuse_suspects),
            "title_alias_candidate_count": len(title_alias_candidates),
            "keyword_change_count": len(keyword_changes),
            "excluded_ambiguous_id_count": len(excluded_ambiguous_ids),
        },
        "guardrails": {
            "id_matching": "字符串精确匹配",
            "product_id_semantics": "商品链接ID，不代表SKU",
            "same_title_different_id": "仅列候选，禁止自动合并",
            "exit_wording": "退出所给Top-N窗口，不等于下架或销量为零",
            "rank_delta": "前期排名-本期排名，正数为上升；排名为序数",
        },
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="按字符串商品ID匹配排名周期")
    parser.add_argument("paths", nargs="+", help="一个或多个 XLSX/CSV/TSV 路径")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        payload = merge_payloads([load_input(path) for path in args.paths])
        result = match_periods(payload["periods"])
    except (RankingInputError, OSError) as exc:
        sys.stderr.write(f"输入拒绝：{exc}\n")
        return 2
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
