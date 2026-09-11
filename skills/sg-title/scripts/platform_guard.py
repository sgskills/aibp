#!/usr/bin/env python3
"""目标平台档案的离线结构与30天惰性复核；不下载、不修改输入、不证明网页真实性。"""
from __future__ import annotations

import argparse
import copy
import json
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse


RULES = ("length", "space_policy", "symbol_policy", "max_term_repetitions")
OFFICIAL_HOSTS = {"tmall": ("tmall.com", "taobao.com"), "jd": ("jd.com",),
                  "pinduoduo": ("pinduoduo.com", "yangkeduo.com"),
                  "douyin": ("jinritemai.com", "douyin.com")}


def inspect_platform(source: dict, key: str, as_of: str | None = None) -> dict:
    errors = []

    def fail(detail):
        errors.append({"code": "platform_schema_invalid", "detail": detail})

    try:
        today = date.fromisoformat(as_of) if as_of is not None else date.today()
    except (TypeError, ValueError):
        today = date.today()
        fail("as_of 必须是有效日期")
    platforms = source.get("platforms") if isinstance(source, dict) else None
    raw = platforms.get(key) if isinstance(platforms, dict) else None
    profile = copy.deepcopy(raw) if isinstance(raw, dict) else {}
    if not profile:
        fail("目标平台不存在或不是对象")
    for field in ("version", "scope", "status"):
        if not isinstance(profile.get(field), str) or not profile[field].strip():
            fail(field + " 必须是非空字符串")
    freshness = profile.get("freshness")
    review_due = True
    if not isinstance(freshness, dict):
        fail("freshness 必须是对象")
    else:
        try:
            verified = date.fromisoformat(freshness["verified_at"])
            review = date.fromisoformat(freshness["review_after"])
            if verified > today or type(freshness.get("interval_days")) is not int or freshness["interval_days"] != 30:
                raise ValueError("日期在未来或间隔不是30天")
            if review != verified + timedelta(days=30):
                raise ValueError("review_after 必须等于 verified_at 加30天")
            review_due = today >= review
        except (KeyError, TypeError, ValueError) as error:
            fail("freshness 日期/间隔无效：" + str(error))
    for name in RULES:
        rule = profile.get(name)
        if not isinstance(rule, dict):
            fail(name + " 必须是对象")
            profile[name] = {}
            continue
        if rule.get("enforcement") not in ("hard", "advisory", "unknown"):
            fail(name + " enforcement 无效")
    length = profile.get("length", {})
    if length.get("metric") not in ("codepoints", "legacy_weighted_bytes", "utf8_bytes"):
        fail("长度计数口径无效")
    for bound in ("min", "max"):
        value = length.get(bound)
        if value is not None and (type(value) is not int or value < 0):
            fail("长度上下限必须是非负整数或null")
    minimum, maximum = length.get("min"), length.get("max")
    if type(minimum) is int and type(maximum) is int and minimum > maximum:
        fail("最小长度超过最大长度")
    operating_defaults = profile.get("operating_defaults")
    if operating_defaults is not None:
        if not isinstance(operating_defaults, dict):
            fail("operating_defaults 必须是对象")
        else:
            operating_length = operating_defaults.get("length")
            if not isinstance(operating_length, dict):
                fail("operating_defaults.length 必须是对象")
            else:
                if operating_length.get("metric") not in (
                    "codepoints", "legacy_weighted_bytes", "utf8_bytes"
                ):
                    fail("经营长度计数口径无效")
                if operating_length.get("enforcement") != "hard":
                    fail("经营长度标准必须为 hard")
                if operating_length.get("source") != "owner_operating_default":
                    fail("经营长度标准来源必须为 owner_operating_default")
                if (
                    not isinstance(operating_length.get("scope"), str)
                    or not operating_length["scope"].strip()
                ):
                    fail("经营长度标准必须提供非空 scope")
                try:
                    confirmed = date.fromisoformat(operating_length["confirmed_at"])
                    if confirmed > today:
                        raise ValueError("确认日期在未来")
                except (KeyError, TypeError, ValueError) as error:
                    fail("经营长度确认日期无效：" + str(error))
                operating_min = operating_length.get("min")
                operating_max = operating_length.get("max")
                for bound, value in (("min", operating_min), ("max", operating_max)):
                    if type(value) is not int or value < 0:
                        fail("经营长度 " + bound + " 必须是非负整数")
                if (
                    type(operating_min) is int
                    and type(operating_max) is int
                    and operating_min > operating_max
                ):
                    fail("经营长度最小值超过最大值")
    if profile.get("space_policy", {}).get("value") not in ("allow", "forbid"):
        fail("space_policy 无效")
    symbols = profile.get("symbol_policy", {}).get("forbidden")
    if not isinstance(symbols, list) or any(not isinstance(x, str) or not x for x in symbols):
        fail("symbol_policy.forbidden 必须是非空字符串列表")
    repeats = profile.get("max_term_repetitions", {}).get("value")
    if type(repeats) is not int or repeats < 1:
        fail("重复次数必须是正整数")
    sources = profile.get("sources")
    verified_source = False
    if not isinstance(sources, list):
        fail("sources 必须是列表")
    else:
        for item in sources:
            if not isinstance(item, dict):
                fail("source 必须是对象")
                continue
            if any(not isinstance(item.get(k), str) or not item[k].strip()
                   for k in ("uri", "status", "accessed_at", "claim")):
                fail("来源须含 uri/status/accessed_at/claim")
                continue
            try:
                accessed = date.fromisoformat(item["accessed_at"])
                if accessed > today:
                    raise ValueError("来源访问日期在未来")
                if item["status"] == "official_verified":
                    effective = date.fromisoformat(item["effective_date"])
                    parsed = urlparse(item["uri"])
                    host = parsed.hostname or ""
                    official = parsed.scheme == "https" and any(
                        host == domain or host.endswith("." + domain) for domain in OFFICIAL_HOSTS.get(key, ()))
                    if not official or effective > today:
                        raise ValueError("官方域名或生效日期无效")
                    verified_source = True
            except (KeyError, TypeError, ValueError) as error:
                fail("来源日期/域名无效：" + str(error))
    hard_rules = any(profile.get(name, {}).get("enforcement") == "hard" for name in RULES)
    if hard_rules and (profile.get("status") != "verified" or not verified_source):
        fail("hard 规则必须关联已核实的官方来源和适用范围；元数据不替代正文核查")
    # 到期或畸形档案只允许离线降级，绝不自动延期或改写事实。
    if errors or review_due:
        for name in RULES:
            if profile.get(name, {}).get("enforcement") == "hard":
                profile[name]["enforcement"] = "unknown"
    return {"platform": key, "as_of": today.isoformat(), "schema_valid": not errors,
            "review_due": review_due or bool(errors), "profile": profile, "errors": errors,
            "verification_scope": "offline_metadata_only"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--profiles", type=Path, default=Path(__file__).resolve().parents[1] / "references/platform-profiles.json")
    parser.add_argument("--as-of", help="用于复现实验；正常使用省略，按本机日期检查")
    args = parser.parse_args()
    try:
        source = json.loads(args.profiles.read_text(encoding="utf-8"))
        result = inspect_platform(source, args.platform, args.as_of)
    except (OSError, ValueError) as error:
        result = {"schema_valid": False, "errors": [str(error)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["schema_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
