"""按标准化内容识别周期副本和更正，不持久缓存或静默覆盖历史。"""
from __future__ import annotations
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping, Sequence

def period_content_hash(period: Mapping[str, Any]) -> str:
    # 文件名、表名和源行只是来源；相同业务内容的异名副本不能增加观测期。
    rows = [{key: value for key, value in row.items() if not key.startswith("_")} for row in period["rows"]]
    rows.sort(key=lambda row: json.dumps(row, sort_keys=True, ensure_ascii=False, default=str))
    content = {key: period.get(key) for key in ("period", "platform", "scope", "category", "ranking_metric", "top_n")}
    content["rows"] = rows
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()

def reconcile_periods(payload: Mapping[str, Any], selected_hashes: Sequence[str] = ()) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(selected_hashes, (str, bytes)) or not isinstance(selected_hashes, Sequence):
        raise ValueError("selected_revision_hashes须为内容SHA256列表")
    selected = set(selected_hashes)
    grouped: dict[str, dict[str, list[Mapping[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for period in payload["periods"]:
        grouped[str(period["island_id"])][period_content_hash(period)].append(period)
    history: dict[str, Any] = {"deduplicated": [], "conflicts": [], "resolved": [], "selection_rule": "explicit_content_sha256", "result_cache_used": False}
    output = []
    consumed: set[str] = set()
    for island, variants in sorted(grouped.items()):
        evidence = []
        candidates = []
        for digest, copies in sorted(variants.items()):
            sources = [{"file": p.get("source_file"), "sheet": p.get("sheet"), "row_count": len(p["rows"])} for p in copies]
            evidence.append({"content_sha256": digest, "sources": sources})
            kept = deepcopy(copies[0])
            kept["content_sha256"] = digest
            kept["all_sources"] = sources
            candidates.append((digest, kept))
            if len(copies) > 1:
                history["deduplicated"].append({"island_id": island, "content_sha256": digest, "copies": len(copies), "sources": sources})
        choices = selected.intersection(variants)
        if len(choices) > 1:
            raise ValueError("同一数据岛不能同时选择两个更正版本")
        if len(variants) > 1 and choices:
            chosen = next(iter(choices))
            consumed.add(chosen)
            output.extend(p for digest, p in candidates if digest == chosen)
            history["resolved"].append({"island_id": island, "variants": evidence, "selected_sha256": chosen, "authorization": "explicit_user_selection"})
        else:
            output.extend(p for _, p in candidates)
            consumed.update(choices)
            if len(variants) > 1:
                history["conflicts"].append({"island_id": island, "variants": evidence, "action": "请确认一个内容指纹后重跑；当前冲突岛仅输出审计"})
    if selected - consumed:
        raise ValueError("指定的更正SHA256不属于当前输入，不能使用历史缓存代替")
    return {**payload, "periods": output}, history
