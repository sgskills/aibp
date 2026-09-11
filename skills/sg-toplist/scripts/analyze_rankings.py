#!/usr/bin/env python3
"""sg-toplist 的稳定 Python API 与命令行入口。"""

from __future__ import annotations

import argparse
import html
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from audit_input import (
    RankingInputError,
    UnsafeInputError,
    audit_dataset,
    load_input,
    load_inputs_isolated,
    merge_payloads,
    normalize_payload,
)
from ranking_engine import analyze_periods, validate_result_guards
from maintenance_check import maintenance_status
from input_history import reconcile_periods


LOGGER = logging.getLogger(__name__)

ROUTE_RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("sg-review", ("评价", "评论", "voc", "差评", "好评"), "评价/VOC验证不属于榜单证据"),
    ("sg-insight", ("消费者洞察", "消费人群", "用户画像", "需求洞察"), "消费者洞察需独立证据"),
    ("sg-profit", ("利润", "毛利", "净利", "赚不赚钱", "成本核算"), "排名高不等于赚钱"),
    ("sg-tmads-report", ("roi", "cpc", "出价", "推广计划", "投放原因"), "推广原因和投放优化需广告报表"),
    ("sg-product", ("完整产品定义", "完整研发方案", "bom", "规格定义", "正式立项方案"), "完整产品定义与研发方案超出机会方向"),
    ("sg-mece", ("跨模块", "不知道先查", "问题很模糊", "经营问题拆解"), "模糊跨模块问题应先做MECE拆解"),
)


def route_request(request: Any) -> dict[str, Any]:
    text = str(request or "").lower()
    # 引用材料和已排除的任务不是本次授权；保留后续转折句中的正向请求。
    text = re.sub(r'“[^”]*”|「[^」]*」|『[^』]*』|"[^"]*"', "", text)
    clauses = re.split(r"[，,。；;！!\n]|但是|然而|而是|但", text)
    active_clauses = []
    for clause in clauses:
        if re.search(r"上次|之前|曾经|历史上", clause) and not re.search(r"本次|这次|现在|继续", clause):
            continue
        clause = re.sub(r"(?:不要|不能|不应)(?:只|仅|忽略|遗漏|漏掉|跳过)", "需要", clause)
        if re.search(r"不要|无需|不用|不必|不做|不分析|不判断|不看|不是|排除|不涉及|do\s+not|don't|without", clause):
            continue
        active_clauses.append(clause)
    matches: list[dict[str, str]] = []
    for target, terms, reason in ROUTE_RULES:
        if any(term.lower() in clause for term in terms for clause in active_clauses):
            matches.append({"target": target, "reason": reason})
    if not matches:
        return {
            "status": "within_scope",
            "handoffs": [],
            "boundaries": {
                "sg-product": "完整产品定义与研发方案",
                "sg-review": "评价/VOC验证",
                "sg-insight": "消费者洞察",
                "sg-profit": "利润判断",
                "sg-tmads-report": "推广原因、ROI、CPC与出价",
                "sg-mece": "模糊跨模块问题",
            },
        }
    result: dict[str, Any] = {
        "status": "partial_handoff",
        "handoffs": matches,
        "ranking_scope_can_continue": True,
        "reason": "仅把榜单证据转为机会方向，相邻专业判断必须让位。",
    }
    return result


def _empty_trajectories() -> dict[str, Any]:
    keys = (
        "matched",
        "entries",
        "exits",
        "reentries",
        "platform_new_listed",
        "reuse_suspects",
        "title_alias_candidates",
        "keyword_changes",
        "excluded_ambiguous_ids",
        "per_comparison",
    )
    result: dict[str, Any] = {
        **{key: [] for key in keys},
        "summary": {
            "matched_count": 0,
            "safe_matched_count": 0,
            "entry_count": 0,
            "exit_count": 0,
            "reentry_count": 0,
            "platform_new_listed_count": 0,
            "reuse_suspect_count": 0,
            "title_alias_candidate_count": 0,
            "keyword_change_count": 0,
            "excluded_ambiguous_id_count": 0,
        },
    }
    return result


def _source_position(row: Mapping[str, Any]) -> dict[str, Any]:
    source = row.get("_source") if isinstance(row.get("_source"), Mapping) else {}
    return {
        "file": source.get("file"),
        "sheet": source.get("sheet"),
        "island_id": source.get("island_id"),
        "series_id": source.get("series_id"),
        "row": source.get("row"),
    }


def _build_delivery_guardrails(periods: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    shop_positions: dict[str, list[dict[str, Any]]] = {}
    compositions: list[dict[str, Any]] = []
    metrics = ("buyers", "visitors", "payment_amount", "price", "cost")
    for period in periods:
        rows = list(period.get("rows", []))
        counts = {
            metric: {"exact": 0, "interval_or_bound": 0, "missing": 0}
            for metric in metrics
        }
        for row in rows:
            shop = row.get("shop")
            if shop not in (None, ""):
                value = str(shop)
                positions = shop_positions.setdefault(value, [])
                position = _source_position(row)
                if position not in positions:
                    positions.append(position)
            for metric in metrics:
                interval = row.get(f"{metric}_interval")
                if not isinstance(interval, Mapping):
                    counts[metric]["missing"] += 1
                elif interval.get("midpoint_is_estimate"):
                    counts[metric]["interval_or_bound"] += 1
                else:
                    counts[metric]["exact"] += 1
        compositions.append(
            {
                "island_id": period.get("island_id"),
                "period": period.get("period"),
                "source_file": period.get("source_file"),
                "sheet": period.get("sheet"),
                "row_count": len(rows),
                "metrics": counts,
            }
        )
    return {
        "identity_verbatim_required": True,
        "identity_fields": ["shop", "brand", "product_id"],
        "identity_rule": "身份值必须逐字来自结构化结果或源表；不得翻译、扩写、品牌化、大小写改写或无证别名替换。",
        "source_shop_names": [
            {"value": value, "positions": positions, "occurrence_count": len(positions)}
            for value, positions in shop_positions.items()
        ],
        "compression_must_keep": ["来源", "周期", "范围", "排名口径", "验证指标", "周期设置依据", "停止/回退条件"],
        "period_setting_rule": "不能把源表统计周期直接当作测试周期；输入跨度仅是证据窗口，测试周期依据榜单更新频率、同长可比窗口、用户目标、历史基线或实验预登记设置。",
        "column_generalization_rule": "不得把部分缺失、部分区间或单个字段的能力缺口普遍化为全列事实；全称判断必须由结构化计数支持。",
        "metric_value_composition": compositions,
        "final_value_check": "最终回答前逐项核对所有店名、商品ID和数字是否可定位到源值。",
    }


def _rejected_result(mode: str, exc: Exception, request: Any = "") -> dict[str, Any]:
    if isinstance(exc, UnsafeInputError):
        code = "UNSAFE_ACTIVE_CONTENT"
    else:
        code = "INPUT_REJECTED"
    message = str(exc)
    audit = {
        "valid": False,
        "status": "blocking",
        "conclusion": f"输入已安全拒绝：{message}",
        "error_count": 1,
        "warning_count": 0,
        "issues": [{"code": code, "severity": "error", "message": message, "evidence": {}}],
        "period_count": 0,
        "islands": [],
        "comparisons": [],
    }
    result: dict[str, Any] = {
        "mode": mode,
        "status": "rejected",
        "data_quality": {"status": "blocking", "conclusion": audit["conclusion"], "one_sentence": audit["conclusion"]},
        "audit": audit,
        "comparability": {
            "islands": [],
            "island_count": 0,
            "comparisons": [],
            "comparable_count": 0,
            "cross_island_merge_performed": False,
        },
        "temporality": {
            "period_count": 0,
            "max_comparable_series_periods": 0,
            "level": "rejected",
            "label": "输入被拒绝，不能形成时间信号",
            "strong_trend": False,
            "strong_trend_candidates": [],
            "causality_proven": False,
        },
        "structure": {"periods": [], "period_count": 0, "own_product_positioning": {"provided": False, "matches": []}},
        "trajectories": _empty_trajectories(),
        "sensitivity": {
            "evidence_first": [],
            "removed_silently": False,
            "cleaning_used_for_sensitivity_only": True,
            "all_data": {"row_count": 0, "matched_count": 0, "entry_count": 0, "exit_count": 0},
            "cleaned_view": {"row_count": 0, "matched_count": 0, "entry_count": 0, "exit_count": 0},
            "difference": {"row_count": 0, "matched_count": 0, "entry_count": 0, "exit_count": 0},
        },
        "capability_gaps": [{"code": "INPUT_REJECTED", "message": "输入未通过安全与结构校验"}],
        "routes": route_request(request),
        "facts": [],
        "opportunities": [],
        "actions": {"product_selection": None, "product_development": None, "main_promotion": None},
        "max_limitation": "输入被拒绝，不能给出榜单机会或行动判断。",
        "rendered_sections": [],
        "delivery_guardrails": _build_delivery_guardrails([]),
    }
    result["severe_error_guards"] = validate_result_guards(result)
    return result


def _resolve_mode(mode: str, period_count: int) -> str:
    if mode not in {"auto", "quick", "deep"}:
        raise ValueError("mode 必须是 auto、quick 或 deep")
    if mode == "auto":
        return "quick" if period_count <= 1 else "deep"
    return mode


def analyze_payload(
    payload: Mapping[str, Any], mode: str = "auto", own_store: str | Sequence[str] | None = None,
    maintenance_state: str | Path | None = None,
) -> dict[str, Any]:
    """分析内联 payload；所有返回值均可直接 JSON 序列化。"""
    request = payload.get("request") or payload.get("question") or payload.get("task") or "" if isinstance(payload, Mapping) else ""
    try:
        normalised = normalize_payload(payload)
        normalised, input_history = reconcile_periods(normalised, payload.get("selected_revision_hashes", []))
        audit = audit_dataset(normalised)
        effective_mode = _resolve_mode(mode, audit["period_count"])
        payload_own_store = payload.get("own_store") if isinstance(payload, Mapping) else None
        payload_own_ids = payload.get("own_product_ids", []) if isinstance(payload, Mapping) else []
        result = analyze_periods(
            normalised["periods"],
            audit,
            own_store=own_store if own_store is not None else payload_own_store,
            own_product_ids=payload_own_ids if isinstance(payload_own_ids, Sequence) and not isinstance(payload_own_ids, (str, bytes)) else [],
            mode=effective_mode,
        )
    except (RankingInputError, OSError, ValueError, TypeError) as exc:
        fallback_mode = mode if mode in {"quick", "deep"} else "quick"
        return _rejected_result(fallback_mode, exc, request)
    result["status"] = "analyzed" if result["audit"]["status"] != "blocking" else "limited"
    result["mode_selection"] = (
        "用户明确指定模式" if mode != "auto"
        else "单期默认极速分析版" if effective_mode == "quick" else "多期默认深度分析版"
    )
    result["routes"] = route_request(normalised.get("request") or request)
    result["input_history"] = input_history
    result["maintenance"] = maintenance_status(state_path=Path(maintenance_state) if maintenance_state else None)
    result["delivery_guardrails"] = _build_delivery_guardrails(normalised["periods"])
    result["rendered_sections"] = (
        ["data_quality", "facts", "opportunities", "actions", "max_limitation"]
        if effective_mode == "quick"
        else [
            "data_quality_and_comparability",
            "structure",
            "trajectories",
            "explicit_attributes",
            "own_product_positioning",
            "opportunity_matrix",
            "actions",
            "validation_and_stop",
            "uncertainty",
        ]
    )
    return result


def analyze_paths(
    paths: Sequence[str],
    mode: str = "auto",
    own_store: str | Sequence[str] | None = None,
    request: str = "",
    maintenance_state: str | Path | None = None,
    selected_revision_hashes: Sequence[str] = (),
) -> dict[str, Any]:
    """逐文件隔离分析；坏文件结构化拒绝，安全文件继续形成独立数据岛。"""
    isolated = load_inputs_isolated(paths)
    payload = isolated["payload"]
    rejections = isolated["file_rejections"]
    if request:
        payload["request"] = request
    payload["selected_revision_hashes"] = list(selected_revision_hashes)
    if not payload.get("periods"):
        message = rejections[0]["message"] if rejections else "没有可分析文件"
        result = _rejected_result(mode if mode in {"quick", "deep"} else "quick", RankingInputError(message), request)
        if rejections:
            result["audit"]["issues"] = [
                {
                    "code": item["code"],
                    "severity": "error",
                    "message": item["message"],
                    "evidence": {"path": item["path"]},
                }
                for item in rejections
            ]
        result["file_rejections"] = rejections
        result["severe_error_guards"] = validate_result_guards(result)
        return result
    result = analyze_payload(payload, mode=mode, own_store=own_store, maintenance_state=maintenance_state)
    result["file_rejections"] = rejections
    result["audit"]["file_rejections"] = rejections
    if rejections:
        safe_status = result["audit"]["status"]
        result["status"] = "partial"
        result["audit"]["safe_island_status"] = safe_status
        result["audit"]["status"] = "partial"
        result["audit"]["issues"] = list(result["audit"].get("issues", [])) + [
            {
                "code": item["code"],
                "severity": "error",
                "message": item["message"],
                "evidence": {"path": item["path"], "isolated_file_only": True},
            }
            for item in rejections
        ]
        result["data_quality"]["status"] = "partial"
        result["data_quality"]["conclusion"] = (
            f"{result['data_quality']['conclusion']} 另有 {len(rejections)} 个文件被隔离拒绝，安全数据岛继续分析。"
        )
        result["data_quality"]["one_sentence"] = result["data_quality"]["conclusion"]
    result["severe_error_guards"] = validate_result_guards(result)
    return result


def _md(value: Any) -> str:
    """转义所有源文本，避免 Markdown 控制符或 HTML 标签进入渲染结果。"""
    if isinstance(value, (Mapping, list, tuple)):
        raw = json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
    else:
        raw = str(value if value is not None else "")
    escaped = html.escape(raw, quote=True)
    return re.sub(r"([\\`*_{}\[\]()#+.!|])", r"\\\1", escaped)


def _validation_setting_basis(validation: Mapping[str, Any]) -> str:
    durations = sorted(
        {
            int(item["duration_days"])
            for item in validation.get("cycle_basis", [])
            if item.get("duration_days") is not None
        }
    )
    window = "/".join(str(item) for item in durations) + "天" if durations else "不可得"
    threshold = validation.get("threshold_source") or "未提供；先确认后启动"
    return (
        f"输入统计窗口={window}（仅证据窗口，不等于测试周期）；"
        "测试周期依据=榜单更新频率、同长可比窗口与实验预登记；"
        f"阈值来源={threshold}"
    )


def _render_chain(chain: Mapping[str, Any], index: int | None = None) -> str:
    prefix = f"{index}. " if index is not None else ""
    validation = chain.get("validation") or {}
    metrics = "、".join(_md(item) for item in validation.get("metrics", []))
    return (
        f"{prefix}{_md(chain.get('opportunity_hypothesis'))}（置信度：{_md(chain.get('confidence'))}）\n"
        f"   - 观察事实：{_md(chain.get('observation_fact'))}\n"
        f"   - 数据位置与口径：{_md(chain.get('data_position_and_definition'))}\n"
        f"   - 变化模式：{_md(chain.get('change_pattern'))}\n"
        f"   - 可能解释：{_md(chain.get('possible_explanation'))}\n"
        f"   - 替代解释/限制：{_md(chain.get('alternative_explanation_or_limitation'))}\n"
        f"   - 行动：{_md(chain.get('action'))}\n"
        f"   - 验证：指标={metrics}；周期={_md(validation.get('cycle'))}；"
        f"周期设置依据={_md(_validation_setting_basis(validation))}；停止条件={_md(validation.get('stop_condition'))}"
    )


def _source_ids(result: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(island.get("island_id")): f"S{index}"
        for index, island in enumerate(result.get("audit", {}).get("islands", []), start=1)
    }


def _source_refs(value: Any, source_ids: Mapping[str, str]) -> list[str]:
    refs: list[str] = []

    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            island_id = item.get("island_id")
            source_id = source_ids.get(str(island_id)) if island_id is not None else None
            if source_id and source_id not in refs:
                refs.append(source_id)
            for child in item.values():
                visit(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)

    visit(value)
    return refs


def _compact_definition(value: Any, source_ids: Mapping[str, str]) -> str:
    refs = _source_refs(value, source_ids)
    collected: dict[str, list[Any]] = {
        "denominator": [],
        "common_k": [],
        "formula": [],
        "aggregation": [],
        "filter": [],
    }

    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                if key in collected and child not in (None, "") and child not in collected[key]:
                    collected[key].append(child)
                visit(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)

    visit(value)
    parts = [f"来源={'/'.join(refs) if refs else '无可定位来源'}"]
    labels = {
        "denominator": "分母",
        "common_k": "commonK",
        "formula": "公式",
        "aggregation": "聚合",
        "filter": "筛选",
    }
    for key, label in labels.items():
        if collected[key]:
            parts.append(f"{label}={'/'.join(_md(item) for item in collected[key])}")
    return "；".join(parts)


def _compact_observation(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        rendered_items = []
        for item in value:
            if isinstance(item, Mapping):
                rendered_items.append(
                    ", ".join(
                        f"{_md(key)}={_md(child)}"
                        for key, child in item.items()
                        if not isinstance(child, (Mapping, list, tuple))
                    )
                )
            else:
                rendered_items.append(_md(item))
        return "；".join(rendered_items)
    if not isinstance(value, Mapping):
        return _md(value)
    parts: list[str] = []
    for key, item in value.items():
        if isinstance(item, (list, tuple)):
            rendered = "/".join(_md(child) for child in item)
        elif isinstance(item, Mapping):
            continue
        else:
            rendered = _md(item)
        parts.append(f"{_md(key)}={rendered}")
    return "；".join(parts)


def _render_quick_chain(
    chain: Mapping[str, Any], index: int, source_ids: Mapping[str, str]
) -> str:
    validation = chain.get("validation") or {}
    metrics = "、".join(_md(item) for item in validation.get("metrics", []))
    candidates = [
        str(item.get("product_id"))
        for item in chain.get("candidate_objects", [])
        if item.get("product_id") not in (None, "")
    ]
    candidate_note = f"；候选对象={_md('/'.join(candidates))}" if candidates else ""
    return (
        f"O{index}. {_md(chain.get('opportunity_hypothesis'))}（置信度：{_md(chain.get('confidence'))}）\n"
        f"   - 事实：{_compact_observation(chain.get('observation_fact'))}{candidate_note}\n"
        f"   - 口径与来源：{_compact_definition(chain.get('data_position_and_definition'), source_ids)}\n"
        f"   - 模式与解释：{_md(chain.get('change_pattern'))}；{_md(chain.get('possible_explanation'))}\n"
        f"   - 替代解释/限制：{_md(chain.get('alternative_explanation_or_limitation'))}\n"
        f"   - 可逆测试：{_md(chain.get('action'))}\n"
        f"   - 验证：指标={metrics}；周期={_md(validation.get('cycle'))}；"
        f"周期设置依据={_md(_validation_setting_basis(validation))}；停止条件={_md(validation.get('stop_condition'))}"
    )


def _render_source_index(result: Mapping[str, Any], source_ids: Mapping[str, str]) -> list[str]:
    audit = result.get("audit", {})
    lines = ["", "## 来源索引"]
    for island in audit.get("islands", []):
        source_id = source_ids.get(str(island.get("island_id")), "S?")
        lines.append(
            f"- {source_id}：文件={_md(island.get('source_file'))}；sheet={_md(island.get('sheet'))}；"
            f"周期={_md(island.get('period'))}；平台={_md(island.get('platform'))}；"
            f"范围={_md(island.get('scope'))}；类目={_md(island.get('category'))}；"
            f"排名指标={_md(island.get('ranking_metric'))}；Top-N={_md(island.get('top_n'))}；"
            f"分母={_md(island.get('row_count'))}。"
        )
    for comparison in audit.get("comparisons", []):
        before = source_ids.get(str(comparison.get("before_island")), "S?")
        after = source_ids.get(str(comparison.get("after_island")), "S?")
        lines.append(
            f"- 比较 {before}→{after}：commonK={_md(comparison.get('common_k'))}；"
            f"可比={_md(comparison.get('comparable'))}；口径={_md(comparison.get('series_id'))}。"
        )
    lines.append(r"- 公式：rank\_delta=前期排名-本期排名（正数为上升）；commonK=min\(前期Top-N, 本期Top-N\)；区间变化=[本期下界-前期上界, 本期上界-前期下界]。")
    return lines


def _render_delivery_guardrails(
    result: Mapping[str, Any], source_ids: Mapping[str, str]
) -> list[str]:
    guardrails = result.get("delivery_guardrails", {})
    lines = ["", "## 交付硬规则（压缩也不得省略）"]
    shops = []
    for item in guardrails.get("source_shop_names", []):
        refs = _source_refs(item.get("positions", []), source_ids)
        source_note = "/".join(refs) if refs else "无可定位来源"
        shops.append(f"{_md(item.get('value'))}（{source_note}）")
    lines.append(
        f"- 身份原值：{_md(guardrails.get('identity_rule'))}"
        f" 本次源店名={'、'.join(shops) if shops else '未提供'}。"
    )
    required = "、".join(_md(item) for item in guardrails.get("compression_must_keep", []))
    lines.append(f"- 关键口径与行动：压缩仍须保留 {required}。")
    lines.append(f"- 周期设置：{_md(guardrails.get('period_setting_rule'))}")
    metric_labels = {
        "buyers": "买家数",
        "visitors": "访客数",
        "payment_amount": "支付金额",
        "price": "价格",
        "cost": "成本",
    }
    for composition in guardrails.get("metric_value_composition", []):
        source_id = source_ids.get(str(composition.get("island_id")), "S?")
        parts = []
        for metric, counts in composition.get("metrics", {}).items():
            observed = int(counts.get("exact", 0)) + int(counts.get("interval_or_bound", 0))
            if observed:
                parts.append(
                    f"{metric_labels.get(metric, _md(metric))}：精确值={_md(counts.get('exact'))}，"
                    f"区间/边界值={_md(counts.get('interval_or_bound'))}，缺失={_md(counts.get('missing'))}"
                )
        if parts:
            lines.append(
                f"- 字段形态计数（{source_id}）：{'；'.join(parts)}；不得概括为全列区间或全列缺失。"
            )
    lines.append(f"- 字段边界：{_md(guardrails.get('column_generalization_rule'))}")
    lines.append(f"- 最终值核对：{_md(guardrails.get('final_value_check'))}")
    return lines


def _render_analysis_basis(
    result: Mapping[str, Any], source_ids: Mapping[str, str] | None = None
) -> list[str]:
    """两种交付共享会改变结论可信度的最小口径，不为极速版隐去异常。"""
    audit = result.get("audit", {})
    structures = {p.get("island_id"): p for p in result.get("structure", {}).get("periods", [])}
    lines = ["", "## 分析口径", f"模式选择：{_md(result.get('mode_selection', '依输入条件确定'))}；数据岛={len(audit.get('islands', []))}。"]
    for island in audit.get("islands", []):
        island_id = island.get("island_id")
        structure = structures.get(island_id, {})
        issues = [i for i in audit.get("issues", []) if i.get("evidence", {}).get("island_id") == island_id]
        def count(code: str) -> int:
            return sum(int(i.get("evidence", {}).get("count", 0)) for i in issues if i.get("code") == code)
        platforms = structure.get("shop_type_distribution") or island.get("shop_type_distribution") or "不可得；见审计"
        display_id = source_ids.get(str(island_id), str(island_id)) if source_ids else island_id
        lines.append(
            f"- {_md(display_id)}：平台构成={_md(platforms)}；范围={_md(island.get('scope'))}；"
            f"类目={_md(island.get('category'))}；排名指标={_md(island.get('ranking_metric'))}；"
            f"状态={_md(island.get('status', audit.get('status')))}；"
            f"有效排名行={_md(island.get('valid_rank_count', island.get('unique_ranks')))} / 输入行={_md(island.get('row_count'))}；"
            f"缺失ID={count('MISSING_PRODUCT_ID')}；重复ID种类={count('DUPLICATE_PRODUCT_ID')}；"
            f"缺失/非法排名={count('MISSING_OR_INVALID_RANK')}；重复排名种类={count('DUPLICATE_RANK')}。"
        )
    for issue in audit.get("issues", []):
        evidence = (
            _compact_definition(issue.get("evidence"), source_ids)
            if source_ids
            else _md(issue.get("evidence"))
        )
        lines.append(f"- 审计：{_md(issue.get('code'))}；{_md(issue.get('message'))}；证据={evidence}。")
    sensitivity = result.get("sensitivity", {})
    lines.append("- 清洗规则：依据显式错类/福利/差价/专拍词标候选，保留原排名且人工复核；不静默删原数据、不把过滤后的天猫子集当完整天猫榜。")
    if source_ids:
        all_data = sensitivity.get("all_data", {})
        cleaned = sensitivity.get("cleaned_view", {})
        lines.append(
            f"- 全量：行={_md(all_data.get('row_count'))}、匹配={_md(all_data.get('matched_count'))}、进入={_md(all_data.get('entry_count'))}、退出={_md(all_data.get('exit_count'))}；"
            f"清洗后：行={_md(cleaned.get('row_count'))}、匹配={_md(cleaned.get('matched_count'))}、进入={_md(cleaned.get('entry_count'))}、退出={_md(cleaned.get('exit_count'))}；"
            f"污染候选={len(sensitivity.get('evidence_first', []))}；疑似链接复用={len(result.get('trajectories', {}).get('reuse_suspects', []))}。"
        )
        gaps = "；".join(
            f"{_md(item.get('code'))}={_md(item.get('message'))}"
            for item in result.get("capability_gaps", [])
        ) or "无"
        lines.append(f"- 缺失与不可算：{gaps}。")
    else:
        lines.append(f"- 全量={_md(sensitivity.get('all_data'))}；清洗后={_md(sensitivity.get('cleaned_view'))}；污染候选={len(sensitivity.get('evidence_first', []))}；疑似链接复用={len(result.get('trajectories', {}).get('reuse_suspects', []))}。")
        lines.append(f"- 缺失与不可算：{_md(result.get('capability_gaps', []))}。")
    return lines


def _number(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _interval_text(interval: Mapping[str, Any]) -> str:
    lower = _number(interval.get("lower"))
    upper = "∞" if interval.get("upper") is None else _number(interval.get("upper"))
    text = f"[{lower}, {upper}]"
    if interval.get("midpoint_is_estimate") and interval.get("estimated_midpoint") is not None:
        text += f"（中点估算={_number(interval.get('estimated_midpoint'))}）"
    return text


def _row_source(position: Mapping[str, Any]) -> str:
    return (
        f"{_md(position.get('file'))}/{_md(position.get('sheet'))}/row {_md(position.get('row'))}"
    )


def _render_matched_details(result: Mapping[str, Any]) -> list[str]:
    safe = [
        item
        for item in result.get("trajectories", {}).get("matched", [])
        if item.get("safe_for_trajectory")
    ]
    safe.sort(
        key=lambda item: (
            not bool(item.get("interval_observations")),
            -abs(int(item.get("rank_delta") or 0)),
            str(item.get("product_id")),
        )
    )
    lines = ["", "### 代表性已匹配明细"]
    if not safe:
        lines.append("- 无安全的普通匹配链接可展示；未用复用疑点或重复ID补数。")
        return lines
    metric_labels = {
        "buyers": "买家数",
        "visitors": "访客数",
        "payment_amount": "支付金额",
        "price": "价格",
    }
    for item in safe[:5]:
        delta = int(item.get("rank_delta") or 0)
        delta_text = f"+{delta}" if delta > 0 else str(delta)
        lines.append(
            f"- 商品ID={_md(item.get('product_id'))}；排名：{_md(item.get('before_rank'))}→{_md(item.get('after_rank'))}，"
            f"变化={delta_text}（前期-本期，正数为上升）；来源：前期={_row_source(item.get('before_position', {}))}；"
            f"后期={_row_source(item.get('after_position', {}))}。"
        )
        for metric, observation in item.get("interval_observations", {}).items():
            change = observation.get("change", {})
            if change.get("lower_delta") is None or change.get("upper_delta") is None:
                change_text = f"方向={_md(change.get('direction'))}"
            else:
                change_text = (
                    f"变化区间=[{_number(change.get('lower_delta'))}, {_number(change.get('upper_delta'))}]；"
                    f"方向={_md(change.get('direction'))}"
                )
            lines.append(
                f"  - {metric_labels.get(metric, _md(metric))}：前期区间={_interval_text(observation.get('before', {}))}；"
                f"后期区间={_interval_text(observation.get('after', {}))}；{change_text}；"
                "不确定性：区间端点来自原字段解析，中点仅为估算，不代表精确观测或因果。"
            )
    return lines


def _action_source_ref(
    action: Mapping[str, Any], opportunities: Sequence[Mapping[str, Any]]
) -> str:
    for index, opportunity in enumerate(opportunities, start=1):
        if (
            action.get("code") == opportunity.get("code")
            and action.get("data_position_and_definition")
            == opportunity.get("data_position_and_definition")
        ):
            return f"O{index}"
    return "对应机会"


def render_markdown(result: Mapping[str, Any]) -> str:
    """按 quick/deep 契约渲染 Markdown；机器审计字段仍保留在 JSON API。"""
    mode = result.get("mode")
    title = "极速分析版" if mode == "quick" else "深度分析版"
    lines = [f"# {title}", "", f"数据质量：{_md(result.get('data_quality', {}).get('one_sentence'))}"]
    if result.get("status") == "rejected":
        lines.extend(["", f"最大限制：{_md(result.get('max_limitation'))}"])
        return "\n".join(lines) + "\n"

    audit = result.get("audit", {})
    source_ids = _source_ids(result)
    if mode == "quick":
        lines.extend(_render_source_index(result, source_ids))
    lines.extend(_render_analysis_basis(result, source_ids if mode == "quick" else None))
    history = result.get("input_history", {})
    for key, label in (("deduplicated", "重复副本"), ("conflicts", "周期更正待确认"), ("resolved", "已确认更正")):
        if history.get(key):
            lines.append(f"- {label}：{_md(history[key])}。")
    if mode == "deep":
        lines.extend(["", "## 口径溯源"])
        for island in audit.get("islands", []):
            source_id = source_ids.get(str(island.get("island_id")), "S?")
            lines.append(
                f"- {source_id}：文件={_md(island.get('source_file'))}；sheet={_md(island.get('sheet'))}；"
                f"island={_md(island.get('island_id'))}；周期={_md(island.get('period'))}；"
                f"平台={_md(island.get('platform'))}；范围={_md(island.get('scope'))}；"
                f"类目={_md(island.get('category'))}；排名指标={_md(island.get('ranking_metric'))}；"
                f"Top-N={_md(island.get('top_n'))}（{_md(island.get('top_n_source'))}）。"
            )
        for comparison in audit.get("comparisons", []):
            lines.append(
                f"- {_md(comparison.get('before_period'))}→{_md(comparison.get('after_period'))}："
                f"commonK={_md(comparison.get('common_k'))}；可比={_md(comparison.get('comparable'))}；"
                f"口径={_md(comparison.get('series_id'))}。"
            )
        lines.append(r"- 公式：rank\_delta=前期排名-本期排名（正数为上升）；commonK=min\(前期Top-N, 本期Top-N\)；区间变化=[本期下界-前期上界, 本期上界-前期下界]。")
    lines.extend(_render_delivery_guardrails(result, source_ids))

    if mode == "quick":
        lines.extend(["", "## 事实信号"])
        for index, fact in enumerate(list(result.get("facts", []))[:3], start=1):
            lines.append(
                f"{index}. {_compact_observation(fact.get('observation'))}（口径：{_compact_definition(fact.get('data_position_and_definition'), source_ids)}；"
                f"限制：{_md(fact.get('limitation'))}）"
            )
        lines.extend(["", "## 机会假设"])
        for index, opportunity in enumerate(list(result.get("opportunities", []))[:3], start=1):
            lines.append(_render_quick_chain(opportunity, index, source_ids))
    else:
        lines.extend(["", "## 数据审计与可比性"])
        lines.append(
            f"- 数据岛：{len(audit.get('islands', []))}；可比较相邻期："
            f"{sum(bool(item.get('comparable')) for item in audit.get('comparisons', []))}。"
        )
        for island in audit.get("islands", []):
            lines.append(
                f"- {_md(island.get('period'))}｜{_md(island.get('platform'))}/{_md(island.get('scope'))}｜"
                f"{_md(island.get('category'))}｜{_md(island.get('ranking_metric'))}｜Top-{_md(island.get('top_n'))}｜"
                f"{_md(island.get('row_count'))}行；文件={_md(island.get('source_file'))}；"
                f"sheet={_md(island.get('sheet'))}；island={_md(island.get('island_id'))}。"
            )
        for issue in audit.get("issues", []):
            lines.append(f"- [{_md(issue.get('severity'))}] {_md(issue.get('message'))}：{_md(issue.get('evidence'))}")

        lines.extend(["", "## 榜单结构与商品轨迹", "", "### 榜单结构"])
        for period in result.get("structure", {}).get("periods", []):
            lines.append(
                f"- {_md(period.get('period'))}：店铺类型={_md(period.get('shop_type_distribution'))}；"
                f"头部店铺={_md(period.get('top_shops'))}。"
            )

        lines.extend(["", "### 商品轨迹与更替"])
        lines.append(f"- 时间证据级别：{_md(result.get('temporality', {}).get('label'))}。")
        lines.append(f"- 轨迹汇总：{_md(result.get('trajectories', {}).get('summary', {}))}。")
        for comparison in result.get("trajectories", {}).get("per_comparison", []):
            if not comparison.get("skipped"):
                lines.append(
                    f"- {_md(comparison.get('before_period'))}→{_md(comparison.get('after_period'))}，共同Top-{_md(comparison.get('common_k'))}："
                    f"共同ID {_md(comparison.get('matched_count'))}，进入 {_md(comparison.get('entry_count'))}，"
                    f"退出 {_md(comparison.get('exit_count'))}，Top20重合 {_md(comparison.get('top20_overlap_count'))}。"
                )
        trajectory_labels = {
            "entries": ("进入", "colon"),
            "exits": ("退出", "colon"),
            "reentries": ("回榜", "parentheses"),
            "reuse_suspects": ("链接复用", "parentheses"),
        }
        for key, (label, style) in trajectory_labels.items():
            items = list(result.get("trajectories", {}).get(key, []))
            count_text = f"{label}：{len(items)}" if style == "colon" else f"{label}（{len(items)}）"
            lines.append(f"- {count_text}；样例={_md(items[:5])}。")
        lines.extend(_render_matched_details(result))

        lines.extend(["", "## 店铺 / 品牌 / 价格 / 标题显式属性"])
        for period in result.get("structure", {}).get("periods", []):
            lines.append(f"- {_md(period.get('period'))} 品牌：{_md(period.get('top_brands') or '无显式品牌字段')}。")
            lines.append(f"- 标题显式提及：{_md(period.get('title_explicit_attributes') or '无可稳定抽取项')}。")
            lines.append(f"- 商品关键词显式字段：{_md(period.get('keyword_explicit_attributes') or '无')}；不等于消费者需求。")
            lines.append(f"- 价格分析：{_md(period.get('price_analysis') or '缺少价格，不做价格带分析')}。")
        lines.append(f"- 能力降级：{_md(result.get('capability_gaps', []))}。")

        lines.extend(["", "## 用户商品定位"])
        own = result.get("structure", {}).get("own_product_positioning", {})
        lines.append(f"- 是否提供：{_md(own.get('provided'))}；命中：{_md(own.get('matches', []))}；限制：{_md(own.get('limitation'))}。")

        lines.extend(["", "## 机会矩阵"])
        for index, opportunity in enumerate(list(result.get("opportunities", []))[:3], start=1):
            lines.append(_render_chain(opportunity, index))

    lines.extend(["", "## 打品 / 研发 / 主推"])
    action_labels = {
        "product_selection": "打品",
        "product_development": "研发",
        "main_promotion": "主推",
    }
    for key, label in action_labels.items():
        action = result.get("actions", {}).get(key)
        if action:
            lines.append(f"### {label}")
            lines.append("")
            if mode == "quick":
                validation = action.get("validation", {})
                metrics = "、".join(_md(item) for item in validation.get("metrics", []))
                source_ref = _action_source_ref(action, list(result.get("opportunities", []))[:3])
                refs = _source_refs(action.get("data_position_and_definition"), source_ids)
                lines.append(
                    f"- 基于 {source_ref}（置信度：{_md(action.get('confidence'))}；来源={'/'.join(refs) if refs else '无可定位来源'}）："
                    f"{_md(action.get('action'))}"
                )
                lines.append(
                    f"- 验证：指标={metrics}；周期={_md(validation.get('cycle'))}；"
                    f"周期设置依据={_md(_validation_setting_basis(validation))}；"
                    f"停止条件={_md(validation.get('stop_condition'))}。"
                )
            else:
                lines.append(_render_chain(action))

    if mode == "deep":
        lines.extend(["", "## 验证与止损"])
        for key, action in result.get("actions", {}).items():
            if action:
                validation = action.get("validation", {})
                lines.append(
                    f"- {_md(key)}：指标={_md(validation.get('metrics'))}；周期={_md(validation.get('cycle'))}；"
                    f"周期设置依据={_md(_validation_setting_basis(validation))}；"
                    f"停止条件={_md(validation.get('stop_condition'))}。"
                )
        lines.extend(["", "## 污染敏感性与能力降级", "", "### 不确定性与污染敏感性"])
        lines.append(f"- 全量/清洗后对照：{_md(result.get('sensitivity', {}).get('all_data'))} / {_md(result.get('sensitivity', {}).get('cleaned_view'))}。")
        lines.append(f"- 污染证据：{_md(result.get('sensitivity', {}).get('evidence_first'))}。")
        lines.append(f"- 严重错误复算：{_md(result.get('severe_error_guards'))}。")
        lines.extend(["", "## 相邻 Skill 让位", "", _md(result.get("routes"))])
    lines.extend(["", "## 最大限制", "", _md(result.get("max_limitation"))])
    maintenance = result.get("maintenance")
    if maintenance:
        lines.extend(["", f"维护检查（30天）：{_md(maintenance.get('message'))} 状态={_md(maintenance.get('reason'))}。"])
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="把商品排名表转为可追溯机会假设")
    parser.add_argument("paths", nargs="+", help="一个或多个 XLSX/CSV/TSV 路径")
    parser.add_argument("--mode", choices=("auto", "quick", "deep"), default="auto")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--own-store", action="append", help="用户自有店铺名，可重复")
    parser.add_argument("--request", help="原始分析诉求，用于相邻Skill路由")
    parser.add_argument("--maintenance-state", type=Path, help="只读用户明确指定的维护状态JSON；默认不写状态")
    parser.add_argument("--select-revision", action="append", default=[], help="明确选择当前输入中的周期内容SHA256，可重复；不默认替换")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = analyze_paths(
        args.paths,
        mode=args.mode,
        own_store=args.own_store,
        request=args.request or "",
        maintenance_state=args.maintenance_state,
        selected_revision_hashes=args.select_revision,
    )
    if args.format == "markdown":
        sys.stdout.write(render_markdown(result))
    else:
        sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 2 if result.get("status") == "rejected" else 0


if __name__ == "__main__":
    raise SystemExit(main())
