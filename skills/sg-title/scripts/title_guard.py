#!/usr/bin/env python3
"""对国内货架电商商品标题做确定性校验。

输入是单个 JSON 对象；可通过 --input 文件或 stdin 提供。脚本只负责可确定
检查，不生成标题，也不会把未知平台口径推断成硬规则。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILES = SKILL_ROOT / "references" / "platform-profiles.json"

PLATFORM_ALIASES = {
    "天猫": "tmall",
    "tmall": "tmall",
    "京东": "jd",
    "jd": "jd",
    "拼多多": "pinduoduo",
    "pdd": "pinduoduo",
    "pinduoduo": "pinduoduo",
    "抖店": "douyin",
    "抖音电商": "douyin",
    "douyin": "douyin",
}

VALID_SOURCE_STATUSES = {"confirmed", "matched_confirmed"}
PROFILE_REQUIRED_FIELDS = {"profile_id", "scope", "source", "confirmed_at", "version"}

# 这是该 Skill 所有者确认的天猫经营口径，不是天猫官方发布规则。它独立于
# platform profile 的官方证据状态，避免把内部交付标准误标成平台事实。
TMALL_OPERATING_LENGTH = {
    "metric": "legacy_weighted_bytes",
    "min": 59,
    "max": 60,
    "enforcement": "hard",
    "source": "owner_operating_default",
}
REVISION_MODES = {"keep", "micro_edit", "rebuild"}
MICRO_REMOVAL_REASONS = {
    "duplicate",
    "forbidden_term",
    "unverified_attribute",
    "platform_hard_conflict",
}
REBUILD_REASONS = {
    "platform_hard_conflict",
    "required_term_conflict",
    "risk_conflict",
    "original_structure_unusable",
}

# 风险信号只触发证据复核，不等于法律定性；普通商品词不在此列表。
RISK_SIGNALS = {
    "医疗级": "qualification", "医用": "qualification",
    "治疗": "qualification", "治愈": "qualification",
    "官方授权": "authorization", "官方首发": "authorization",
    "官方": "authorization", "授权": "authorization", "首发": "authorization",
    "联名": "authorization", "迪士尼": "authorization", "原装": "authorization",
    "进口": "qualification", "专利": "qualification", "儿童": "qualification",
    "食品级": "qualification", "母婴级": "qualification", "安全认证": "qualification",
    "全网第一": "comparison", "第一": "comparison", "顶级": "comparison",
    "国家级": "qualification",
}


def input_errors(request: Any) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if not isinstance(request, dict):
        return [{"code": "input_schema_invalid", "detail": "输入必须是 JSON 对象"}]
    for field in ("title", "platform"):
        if not isinstance(request.get(field), str) or not request[field].strip():
            add_issue(errors, "input_schema_invalid", field + " 必须是非空字符串")
    string_lists = ("title_core_terms", "required_terms", "forbidden_terms",
                    "unverified_attributes", "repeat_sensitive_terms")
    object_lists = ("keyword_sources", "preference_profiles", "trend_claims", "competitor_claims")
    for field in string_lists + object_lists:
        if field not in request:
            continue
        value = request[field]
        element_type = str if field in string_lists else dict
        if (not isinstance(value, list) or any(not isinstance(x, element_type) for x in value)
                or (element_type is str and any(not x.strip() for x in value))):
            add_issue(errors, "input_schema_invalid", field + " 的列表或元素类型错误")
    for field in ("current_requirements", "context"):
        if field in request and not isinstance(request[field], dict):
            add_issue(errors, "input_schema_invalid", field + " 必须是对象")
    if "original_title" in request:
        if not isinstance(request["original_title"], str) or not request["original_title"].strip():
            add_issue(errors, "input_schema_invalid", "original_title 必须是非空字符串")
        revision = request.get("revision")
        if not isinstance(revision, dict):
            add_issue(errors, "input_schema_invalid", "提供 original_title 时必须提供 revision 对象")
        else:
            mode = revision.get("mode")
            if mode not in REVISION_MODES:
                add_issue(errors, "input_schema_invalid", "revision.mode 只能为 keep/micro_edit/rebuild")
            removals = revision.get("removals", [])
            if not isinstance(removals, list) or any(not isinstance(item, dict) for item in removals):
                add_issue(errors, "input_schema_invalid", "revision.removals 必须是对象列表")
            else:
                for item in removals:
                    term = item.get("term")
                    reason = item.get("reason_code")
                    if not isinstance(term, str) or not term:
                        add_issue(errors, "input_schema_invalid", "revision.removals.term 必须是非空字符串")
                    if reason not in MICRO_REMOVAL_REASONS:
                        add_issue(errors, "input_schema_invalid", "revision.removals.reason_code 不受支持")
            if mode == "rebuild" and revision.get("reason_code") not in REBUILD_REASONS:
                add_issue(errors, "input_schema_invalid", "rebuild 必须提供受支持的 revision.reason_code")
    elif "revision" in request:
        add_issue(errors, "input_schema_invalid", "revision 不能脱离 original_title 使用")
    for field in ("title_core_terms", "keyword_sources"):
        if not request.get(field):
            add_issue(errors, "provenance_missing", field + " 不得遗漏或为空")
    if errors:
        return errors
    requirements = request.get("current_requirements", {})
    if set(requirements) - {"space_policy"}:
        add_issue(errors, "unsupported_current_requirement", sorted(set(requirements) - {"space_policy"}))
    if requirements.get("space_policy", "allow") not in {"allow", "forbid"}:
        add_issue(errors, "input_schema_invalid", "space_policy 只能为 allow/forbid")
    seen: set[str] = set()
    for record in request["keyword_sources"]:
        if any(not isinstance(record.get(k), str) or not record[k].strip() for k in ("term", "status", "source")):
            add_issue(errors, "input_schema_invalid", "词源须含非空 term/status/source")
        elif record["term"] in seen:
            add_issue(errors, "input_schema_invalid", "词源重复：" + record["term"])
        else:
            seen.add(record["term"])
        if "category_match" in record and not isinstance(record["category_match"], bool):
            add_issue(errors, "input_schema_invalid", "category_match 必须是布尔值")
        if "evidence" in record and not isinstance(record["evidence"], dict):
            add_issue(errors, "input_schema_invalid", "evidence 必须是对象")
    for profile in request.get("preference_profiles", []):
        for field in ("scope", "preferences"):
            if field in profile and not isinstance(profile[field], dict):
                add_issue(errors, "input_schema_invalid", "profile." + field + " 必须是对象")
    return errors


def rejected_input(errors: list[dict[str, Any]]) -> dict[str, Any]:
    return {"allowed": False, "errors": errors, "warnings": [], "platform": None,
            "platform_profile_version": None, "platform_profile_status": "invalid",
            "active_profile_id": None,
            "measurements": {
                "length": 0,
                "length_metric": "codepoints",
                "length_policy_source": None,
                "original_length": None,
                "spaces": 0,
            },
            "checks": {
                "hard_rule_compliant": False,
                "revision_mode": None,
                "original_title_qualified": None,
                "original_order_preserved": None,
            }}


def load_profiles(path: Path | None = None) -> dict[str, Any]:
    source = path or DEFAULT_PROFILES
    return json.loads(source.read_text(encoding="utf-8"))


def normalize_platform(value: Any) -> str:
    text = str(value or "").strip()
    return PLATFORM_ALIASES.get(text, text.lower())


def measure_title(title: str, metric: str) -> int:
    if metric == "legacy_weighted_bytes":
        return sum(1 if ord(char) < 128 else 2 for char in title)
    if metric == "utf8_bytes":
        return len(title.encode("utf-8"))
    if metric == "codepoints":
        return len(title)
    raise ValueError(f"不支持的长度口径：{metric}")


def scope_matches(scope: dict[str, Any], context: dict[str, Any]) -> bool:
    for key in ("platform", "store", "category"):
        expected = scope.get(key)
        if expected is None:
            return False
        if expected == "*":
            continue
        actual = context.get(key)
        if key == "platform":
            expected = normalize_platform(expected)
            actual = normalize_platform(actual)
        if str(actual or "") != str(expected):
            return False
    return True


def resolve_preference_profile(
    request: dict[str, Any], warnings: list[dict[str, Any]]
) -> dict[str, Any] | None:
    active_id = request.get("active_profile_id")
    if not active_id:
        return None
    profiles = request.get("preference_profiles") or []
    profile = next((item for item in profiles if item.get("profile_id") == active_id), None)
    if profile is None:
        warnings.append({"code": "profile_not_found", "detail": str(active_id)})
        return None
    missing = sorted(PROFILE_REQUIRED_FIELDS - set(profile))
    if missing:
        warnings.append({"code": "profile_schema_invalid", "detail": ",".join(missing)})
        return None
    if profile.get("status", "active") != "active":
        warnings.append({"code": "profile_inactive", "detail": str(active_id)})
        return None
    context = dict(request.get("context") or {})
    context.setdefault("platform", request.get("platform"))
    if not scope_matches(profile["scope"], context):
        warnings.append({"code": "profile_scope_mismatch", "detail": str(active_id)})
        return None
    return profile


def add_issue(
    issues: list[dict[str, Any]], code: str, detail: Any, **extra: Any
) -> None:
    item = {"code": code, "detail": detail}
    item.update(extra)
    issues.append(item)


def _enforce_or_warn(
    enforcement: str,
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    code: str,
    detail: Any,
) -> None:
    if enforcement == "hard":
        add_issue(errors, code, detail)
    else:
        add_issue(warnings, f"{code}_{enforcement}", detail)


def effective_length_rule(platform_key: str, platform: dict[str, Any]) -> dict[str, Any]:
    if platform_key == "tmall":
        configured = (platform.get("operating_defaults") or {}).get("length")
        return dict(configured or TMALL_OPERATING_LENGTH)
    rule = dict(platform.get("length") or {})
    rule.setdefault("source", "platform_profile")
    return rule


def _unsupported_risk_terms(title: str, source_records: dict[str, dict[str, Any]]) -> list[str]:
    risk_hits = {term: kind for term, kind in RISK_SIGNALS.items() if term in title}
    risk_hits.update({
        match.group(): "test_report"
        for match in re.finditer(r"100[%％][\u4e00-\u9fff]{1,6}", title)
    })
    unsupported: list[str] = []
    for term, kind in risk_hits.items():
        supported = any(
            term in record["term"] and record["term"] in title
            and record.get("status") in VALID_SOURCE_STATUSES
            and record.get("category_match", True) is True
            and (record.get("evidence") or {}).get("type") == kind
            and isinstance((record.get("evidence") or {}).get("reference"), str)
            and (record.get("evidence") or {})["reference"].strip()
            and (record.get("evidence") or {}).get("product_match") is True
            for record in source_records.values()
        )
        if not supported:
            unsupported.append(term)
    return unsupported


def _is_subsequence(source: str, candidate: str) -> bool:
    position = 0
    for char in candidate:
        if position < len(source) and char == source[position]:
            position += 1
    return position == len(source)


def _apply_declared_removals(
    original: str,
    removals: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> str:
    reduced = original
    for removal in removals:
        term = removal["term"]
        if term not in reduced:
            add_issue(errors, "revision_removal_not_found", term)
            continue
        reduced = reduced.replace(term, "", 1)
    return reduced


def validate_title(
    request: dict[str, Any], profiles_data: dict[str, Any] | None = None
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    errors = input_errors(request)
    if errors:
        return rejected_input(errors)
    title = request.get("title")
    if not isinstance(title, str) or not title.strip():
        add_issue(errors, "title_missing", "title 必须是非空字符串")
        title = "" if title is None else str(title)

    platform_key = normalize_platform(request.get("platform"))
    profiles_data = profiles_data or load_profiles()
    platform = (profiles_data.get("platforms") or {}).get(platform_key)
    if platform is not None and "freshness" in platform:
        from platform_guard import inspect_platform
        inspection = inspect_platform(profiles_data, platform_key)
        platform = inspection["profile"]
        if not inspection["schema_valid"]:
            return rejected_input(inspection["errors"])
        if inspection["review_due"]:
            add_issue(warnings, "platform_review_due", "已到复核日期；过期硬规则停用，不主动联网")
    elif platform is not None:
        if platform.get("status") == "test_only":
            add_issue(warnings, "platform_freshness_missing", "测试档案无复核日期；仅用于冻结回归")
        else:
            return rejected_input([
                {"code": "platform_schema_invalid", "detail": "非测试平台档案必须提供 freshness"}
            ])
    if platform is None:
        add_issue(errors, "platform_profile_missing", platform_key or "未提供")
        platform = {
            "version": None,
            "status": "missing",
            "length": {"metric": "codepoints", "min": None, "max": None, "enforcement": "unknown"},
            "space_policy": {"value": "allow", "enforcement": "unknown"},
            "symbol_policy": {"forbidden": [], "enforcement": "unknown"},
            "max_term_repetitions": {"value": 1, "enforcement": "advisory"},
        }

    active_profile = resolve_preference_profile(request, warnings)
    current_requirements = request.get("current_requirements") or {}

    length_rule = effective_length_rule(platform_key, platform)
    metric = length_rule.get("metric") or "codepoints"
    try:
        measured = measure_title(title, metric)
    except ValueError as error:
        add_issue(errors, "length_metric_invalid", str(error))
        metric = "codepoints"
        measured = len(title)
    length_enforcement = length_rule.get("enforcement", "unknown")
    minimum = length_rule.get("min")
    maximum = length_rule.get("max")
    if minimum is not None and measured < int(minimum):
        _enforce_or_warn(
            length_enforcement,
            errors,
            warnings,
            "length_below_min",
            {"actual": measured, "min": minimum, "metric": metric},
        )
    if maximum is not None and measured > int(maximum):
        _enforce_or_warn(
            length_enforcement,
            errors,
            warnings,
            "length_above_max",
            {"actual": measured, "max": maximum, "metric": metric},
        )
    if minimum is None and maximum is None:
        add_issue(warnings, "length_rule_unknown", {"metric": metric})

    platform_space = platform.get("space_policy") or {}
    space_policy = platform_space.get("value", "allow")
    space_enforcement = platform_space.get("enforcement", "unknown")
    requested_space = current_requirements.get("space_policy")
    profile_space = None
    if active_profile:
        profile_space = (active_profile.get("preferences") or {}).get("space_policy")
    if space_enforcement != "hard":
        space_policy = requested_space or profile_space or space_policy
    elif (requested_space or profile_space) and (requested_space or profile_space) != space_policy:
        add_issue(warnings, "space_preference_overridden_by_hard_rule", space_policy)
    whitespace_count = sum(char.isspace() for char in title)
    if whitespace_count and space_policy == "forbid":
        _enforce_or_warn(
            "hard" if space_enforcement == "hard" or requested_space == "forbid" else "advisory",
            errors,
            warnings,
            "space_forbidden",
            whitespace_count,
        )
    elif " " in title and space_enforcement == "unknown" and not (requested_space or profile_space):
        add_issue(warnings, "space_rule_unknown", title.count(" "))

    symbol_rule = platform.get("symbol_policy") or {}
    forbidden_symbols = [str(item) for item in symbol_rule.get("forbidden") or []]
    symbol_hits = sorted({symbol for symbol in forbidden_symbols if symbol and symbol in title})
    if symbol_hits:
        _enforce_or_warn(
            symbol_rule.get("enforcement", "unknown"),
            errors,
            warnings,
            "symbol_forbidden",
            symbol_hits,
        )

    required_terms = [str(term) for term in request.get("required_terms") or [] if str(term)]
    missing_required = [term for term in required_terms if term not in title]
    if missing_required:
        add_issue(errors, "required_term_missing", missing_required)

    forbidden_terms = [str(term) for term in request.get("forbidden_terms") or [] if str(term)]
    forbidden_hits = [term for term in forbidden_terms if term in title]
    if forbidden_hits:
        add_issue(errors, "forbidden_term_hit", forbidden_hits)

    source_records = {
        str(item.get("term")): item
        for item in request.get("keyword_sources") or []
        if isinstance(item, dict) and item.get("term")
    }
    unsupported_core_terms: list[str] = []
    phantom_core_terms: list[str] = []
    for term in [str(item) for item in request.get("title_core_terms") or [] if str(item)]:
        if term not in title:
            phantom_core_terms.append(term)
        record = source_records.get(term)
        if (
            record is None
            or record.get("status") not in VALID_SOURCE_STATUSES
            or record.get("category_match", True) is False
        ):
            unsupported_core_terms.append(term)
    if unsupported_core_terms:
        add_issue(errors, "unsupported_core_term", unsupported_core_terms)
    if phantom_core_terms:
        add_issue(errors, "core_term_not_in_title", phantom_core_terms)

    unverified_hits = [
        str(term)
        for term in request.get("unverified_attributes") or []
        if str(term) and str(term) in title
    ]
    if unverified_hits:
        add_issue(errors, "unverified_attribute_hit", unverified_hits)

    unsupported_risks = _unsupported_risk_terms(title, source_records)
    if unsupported_risks:
        add_issue(errors, "high_risk_evidence_missing", unsupported_risks)

    repeat_rule = platform.get("max_term_repetitions") or {}
    repeat_max = int(repeat_rule.get("value", 1))
    repeat_terms = request.get("repeat_sensitive_terms")
    if repeat_terms is None:
        repeat_terms = request.get("title_core_terms") or []
    repeated = {
        str(term): title.count(str(term))
        for term in repeat_terms
        if str(term) and title.count(str(term)) > repeat_max
    }
    if repeated:
        _enforce_or_warn(
            repeat_rule.get("enforcement", "advisory"),
            errors,
            warnings,
            "term_repeated",
            repeated,
        )

    invalid_trends = [
        claim.get("term")
        for claim in request.get("trend_claims") or []
        if isinstance(claim, dict)
        and claim.get("comparable") is False
        and claim.get("claim") not in {None, "", "not_comparable"}
    ]
    if invalid_trends:
        add_issue(errors, "incomparable_trend_claim", invalid_trends)

    invalid_competitor_claims = [
        claim.get("term")
        for claim in request.get("competitor_claims") or []
        if isinstance(claim, dict)
        and claim.get("source") == "competitor_frequency"
        and claim.get("claim_type") in {"search_demand", "search_volume", "conversion"}
    ]
    if invalid_competitor_claims:
        add_issue(errors, "competitor_frequency_as_demand", invalid_competitor_claims)

    original_title = request.get("original_title")
    revision = request.get("revision") or {}
    revision_mode = revision.get("mode") if original_title is not None else None
    original_length: int | None = None
    original_qualified: bool | None = None
    original_order_preserved: bool | None = None
    if isinstance(original_title, str):
        original_length = measure_title(original_title, metric)
        original_issues: list[str] = []
        if minimum is not None and original_length < int(minimum):
            original_issues.append("length_below_min")
        if maximum is not None and original_length > int(maximum):
            original_issues.append("length_above_max")
        original_spaces = sum(char.isspace() for char in original_title)
        if original_spaces and space_policy == "forbid" and (
            space_enforcement == "hard" or requested_space == "forbid"
        ):
            original_issues.append("space_forbidden")
        if symbol_rule.get("enforcement", "unknown") == "hard" and any(
            symbol and symbol in original_title for symbol in forbidden_symbols
        ):
            original_issues.append("symbol_forbidden")
        if any(term not in original_title for term in required_terms):
            original_issues.append("required_term_missing")
        if any(term in original_title for term in forbidden_terms):
            original_issues.append("forbidden_term_hit")
        if any(term in original_title for term in request.get("unverified_attributes") or []):
            original_issues.append("unverified_attribute_hit")
        if _unsupported_risk_terms(original_title, source_records):
            original_issues.append("high_risk_evidence_missing")
        original_qualified = not original_issues

        if original_qualified and title != original_title:
            add_issue(errors, "qualified_original_changed", "原标题已合格，必须原样保留")
        if revision_mode == "keep" and title != original_title:
            add_issue(errors, "keep_mode_changed_title", "keep 模式的 title 必须与 original_title 完全一致")
        elif revision_mode == "micro_edit":
            reduced_original = _apply_declared_removals(
                original_title,
                revision.get("removals") or [],
                errors,
            )
            original_order_preserved = _is_subsequence(reduced_original, title)
            if not original_order_preserved:
                add_issue(
                    errors,
                    "original_order_not_preserved",
                    "微调必须保留原标题未声明删除内容的相对顺序",
                )
        elif revision_mode == "rebuild" and original_qualified:
            # qualified_original_changed 已给出主错误；保留独立分支使重构门明确可审计。
            original_order_preserved = False

    hard_rule_errors = {
        item["code"]
        for item in errors
        if item["code"]
        in {"length_below_min", "length_above_max", "space_forbidden", "symbol_forbidden"}
    }
    return {
        "allowed": not errors,
        "platform": platform_key,
        "platform_profile_version": platform.get("version"),
        "platform_profile_status": platform.get("status"),
        "active_profile_id": active_profile.get("profile_id") if active_profile else None,
        "measurements": {
            "length": measured,
            "length_metric": metric,
            "length_policy_source": length_rule.get("source"),
            "original_length": original_length,
            "spaces": whitespace_count,
        },
        "checks": {
            "required_terms_total": len(required_terms),
            "required_terms_met": len(required_terms) - len(missing_required),
            "forbidden_hits": forbidden_hits,
            "unsupported_core_terms": unsupported_core_terms,
            "unverified_attribute_hits": unverified_hits,
            "hard_rule_compliant": not hard_rule_errors,
            "revision_mode": revision_mode,
            "original_title_qualified": original_qualified,
            "original_order_preserved": original_order_preserved,
        },
        "errors": errors,
        "warnings": warnings,
    }


def classify_route(text: str) -> str:
    lowered = text.lower()
    routes = [
        (("公众号", "文章标题"), "guan-san-title"),
        (("短视频标题", "直播标题", "图文标题"), "content-title"),
        (("完整listing", "完整 listing", "详情页文案"), "listing-copy"),
        (("市场榜单", "行业趋势", "机会品"), "market-research"),
        (("产品研发", "概念设计", "选品开发"), "product-development"),
        (("评价分析", "评论分析", "voc"), "voc-research"),
        (("广告投放", "roi", "cpc", "出价", "推广计划"), "sg-tmads-report"),
        (("利润", "赚不赚钱", "毛利", "履约侵蚀"), "sg-profit"),
        (("跨模块", "不知道先查哪个", "经营问题拆解"), "sg-mece"),
    ]
    for terms, route in routes:
        if any(term in lowered for term in terms):
            return route
    return "sg-title"


def route_request(text: str) -> dict[str, Any]:
    """混合任务保留标题子任务；旧 classify_route 仅供单标签接口兼容。"""
    first_route = classify_route(text)
    title_task = any(term in text for term in ("商品标题", "电商标题", "$sg-title"))
    platform_title = "标题" in text and any(
        platform in text for platform in ("天猫", "京东", "拼多多", "抖店", "抖音电商")
    )
    if platform_title:
        title_task = True
    adjacent = []
    for segment in re.split(r"[，。；,;]|同时|并且|以及", text):
        route = classify_route(segment)
        if route != "sg-title" and route not in adjacent:
            adjacent.append(route)
    if not adjacent and first_route == "sg-title":
        title_task = True
    return {"title_task": title_task, "adjacent_routes": adjacent}


def read_request(path: str | None) -> dict[str, Any]:
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError("未从 --input 或 stdin 收到 JSON")
    return json.loads(raw)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="输入 JSON 文件；省略时读取 stdin")
    parser.add_argument("--profiles", help="平台档案 JSON；默认 references/platform-profiles.json")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser.parse_args()


def render_text(result: dict[str, Any]) -> None:
    print(f"allowed={str(result['allowed']).lower()}")
    print(
        f"platform={result['platform']} profile={result['platform_profile_version']} "
        f"length={result['measurements']['length']}({result['measurements']['length_metric']})"
    )
    for issue in result["errors"]:
        print(f"ERROR {issue['code']}: {issue['detail']}")
    for issue in result["warnings"]:
        print(f"WARN {issue['code']}: {issue['detail']}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = parse_args()
    try:
        request = read_request(args.input)
        profiles = load_profiles(Path(args.profiles)) if args.profiles else load_profiles()
        result = validate_title(request, profiles)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"allowed": False, "fatal_error": str(error)}, ensure_ascii=False))
        return 2
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        render_text(result)
    return 0 if result["allowed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
