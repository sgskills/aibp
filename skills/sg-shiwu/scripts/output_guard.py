#!/usr/bin/env python3
"""Fail-closed validation for sg-shiwu reports and incremental updates.

This module uses only the Python standard library.  It validates both the
machine-readable sidecar and the Markdown that is actually delivered.
"""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path
from typing import Any


SECTIONS = (
    "输入质量审计与图片编号", "产品/变体/配件/包装/道具分组", "视觉指纹证据表",
    "工具中立的固定身份锚点", "场景变量", "负面约束与易漂移点",
    "未知、冲突和最小补拍清单",
)
FALLBACK_SECTIONS = ("无法分析的原因", "未做出的结论", "最小上传清单")
EVIDENCE_TYPES = {"清晰观察", "用户确认", "外观推断", "冲突", "不可判断"}
STABILITIES = {"身份不变量", "变体特征", "状态变量", "拍摄伪影", "未知"}
PRIORITIES = {"P0", "P1", "P2"}
CONFIDENCE = {"高", "中", "低"}
GROUP_KINDS = {"product", "variant", "accessory", "packaging", "prop", "unknown"}
GROUP_ID = re.compile(r"^(?:P\d{2}(?:-V\d{2})?|ACC\d*|PACK\d*|PROP\d*|UNK\d*)$")
PLACEHOLDERS = {"", "待补充", "待完善", "todo", "n/a", "无内容", "略"}
COLOR_TERMS = ("色", "颜色", "色面", "色区", "色泽", "色调", "色彩")
PHOTOMETRIC_TERMS = ("受光", "高光", "亮斑", "直射光", "强反射", "反光", "曝光", "倒影", "透色", "色偏", "环境光", "当前视角")


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _photometric_anchor_risk(feature: dict[str, Any], sources: dict[str, dict[str, Any]]) -> bool:
    """Return True when a single-image colour claim admits photometric contamination."""
    subject = f"{feature.get('name', '')} {feature.get('value', '')}"
    reason = str(feature.get("confidence", {}).get("reason", ""))
    image_ids = {
        item.get("source_id")
        for item in feature.get("evidence", [])
        if isinstance(item, dict) and sources.get(item.get("source_id"), {}).get("kind") == "image"
    }
    return (
        len(image_ids) < 2
        and any(term in subject for term in COLOR_TERMS)
        and (any(term in str(feature.get("name", "")) for term in PHOTOMETRIC_TERMS)
             or ("色区" in str(feature.get("name", "")) and any(term in reason for term in PHOTOMETRIC_TERMS)))
        and any(term in f"{subject} {reason}" for term in PHOTOMETRIC_TERMS)
    )


def _section_bodies(markdown: str, titles: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """Return ordered bodies for title-matching Markdown headings."""
    if not _text(markdown):
        return [], ["markdown must be non-empty"]
    heading = re.compile(r"(?m)^#{1,6}\s+(?:\d+[.、]\s*)?(.+?)\s*$")
    hits = []
    for match in heading.finditer(markdown):
        title = match.group(1).strip()
        if title in titles:
            hits.append((match.start(), match.end(), title))
    errors: list[str] = []
    if [h[2] for h in hits] != list(titles):
        return [], ["markdown sections are missing, duplicated, or out of order"]
    bodies = []
    for index, (_, end, _) in enumerate(hits):
        stop = hits[index + 1][0] if index + 1 < len(hits) else len(markdown)
        body = markdown[end:stop].strip()
        normalized = re.sub(r"[\s*`_#：:。.;；|-]", "", body).lower()
        if normalized in PLACEHOLDERS or not normalized:
            errors.append(f"section '{titles[index]}' has no substantive body")
        bodies.append(body)
    return bodies, errors


def _maps(sources: Any) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(sources, list):
        return result, ["sources must be a list"]
    for i, source in enumerate(sources):
        if not isinstance(source, dict) or not _text(source.get("id")):
            errors.append(f"sources[{i}] is invalid")
            continue
        if set(source) != {"id", "kind", "readable", "active", "group_ids"}:
            errors.append(f"sources[{i}] must use the exact source schema")
        if source.get("kind") not in {"image", "user", "reference", "untrusted"}:
            errors.append(f"sources[{i}].kind is invalid")
        if not isinstance(source.get("readable"), bool) or not isinstance(source.get("active"), bool):
            errors.append(f"sources[{i}] readable and active must be booleans")
        if not isinstance(source.get("group_ids"), list) or any(not _text(g) for g in source.get("group_ids", [])):
            errors.append(f"sources[{i}].group_ids must be a string list")
        sid = source["id"]
        if sid in result:
            errors.append(f"duplicate source {sid}")
        result[sid] = source
    return result, errors


def _feature_errors(feature: Any, groups: dict[str, dict[str, Any]], sources: dict[str, dict[str, Any]], path: str) -> list[str]:
    errors: list[str] = []
    required = {"id", "group_id", "name", "value", "evidence", "evidence_type", "stability", "priority", "confidence"}
    if not isinstance(feature, dict):
        return [f"{path} must be an object"]
    missing = required - set(feature)
    if missing:
        errors.append(f"{path} missing {sorted(missing)}")
    for key in ("id", "group_id", "name", "value"):
        if not _text(feature.get(key)):
            errors.append(f"{path}.{key} must be non-empty")
    if str(feature.get("name", "")).strip() in {"主体几何", "整体几何", "综合外观", "整体外观"}:
        errors.append(f"{path}.name is a composite field; split independently updateable observations")
    gid = feature.get("group_id")
    if gid not in groups:
        errors.append(f"{path}.group_id is unknown")
    etype, stability, priority = feature.get("evidence_type"), feature.get("stability"), feature.get("priority")
    if etype not in EVIDENCE_TYPES:
        errors.append(f"{path}.evidence_type is invalid")
    if stability not in STABILITIES:
        errors.append(f"{path}.stability is invalid")
    if priority not in PRIORITIES:
        errors.append(f"{path}.priority is invalid")
    confidence = feature.get("confidence")
    level = confidence.get("level") if isinstance(confidence, dict) else None
    if not isinstance(confidence, dict) or level not in CONFIDENCE or not _text(confidence.get("reason")):
        errors.append(f"{path}.confidence is invalid")
    evidence = feature.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append(f"{path}.evidence must be non-empty")
        evidence = []
    cited: list[dict[str, Any]] = []
    for j, citation in enumerate(evidence):
        if not isinstance(citation, dict) or not _text(citation.get("source_id")) or not _text(citation.get("location")):
            errors.append(f"{path}.evidence[{j}] requires source_id and location")
            continue
        source = sources.get(citation["source_id"])
        if source is None:
            errors.append(f"{path}.evidence[{j}] source is unregistered")
            continue
        cited.append(source)
        if source.get("readable") is not True or source.get("active") is not True:
            errors.append(f"{path}.evidence[{j}] source is unreadable or inactive")
        allowed_groups = source.get("group_ids", [])
        # A variant may use a source explicitly assigned to itself (the source
        # can also be assigned to its parent).  Merely sharing the parent must
        # not let it borrow a sibling variant's image.
        if gid not in allowed_groups:
            errors.append(f"{path}.evidence[{j}] source is not assigned to owning group")
    if etype == "用户确认" and not any(s.get("kind") == "user" for s in cited):
        errors.append(f"{path} user confirmation requires an active trusted user source")
    if etype != "用户确认" and not any(s.get("kind") == "image" for s in cited):
        errors.append(f"{path} visual evidence requires an image source")
    if etype == "冲突" and len({s.get("id") for s in cited}) < 2:
        errors.append(f"{path} conflict requires two sources")
    if etype in {"外观推断", "冲突", "不可判断"} and level == "高":
        errors.append(f"{path} unresolved evidence cannot be high confidence")
    value = str(feature.get("value", ""))
    if etype == "不可判断" and "不可判断" not in value:
        errors.append(f"{path} unknown value must say 不可判断")
    if etype == "外观推断" and not any(x in value for x in ("疑似", "可能", "视觉呈现")):
        errors.append(f"{path} inference lacks a qualifier")
    # Material, brand authenticity, exact specifications and performance are not
    # visually established by an unqualified appearance inference.
    if etype == "外观推断" and any(x in value for x in ("纯钛", "316L", "IP68", "确定为", "正品", "准确尺寸")):
        errors.append(f"{path} contains an unqualified non-visual claim")
    return errors


def validate_report(report: Any, sources: Any) -> list[str]:
    """Validate one complete or degraded report; return all errors."""
    try:
        return _validate_report(report, sources)
    except Exception as exc:  # fail closed for malformed external data
        return [f"malformed report: {type(exc).__name__}: {exc}"]


def _validate_report(report: Any, sources: Any) -> list[str]:
    if not isinstance(report, dict):
        return ["report must be an object"]
    required = {"route", "markdown", "groups", "features", "identity_anchors", "history", "rule_version"}
    errors = [f"report missing {sorted(required - set(report))}"] if required - set(report) else []
    route = report.get("route")
    if route not in {"analyze", "correct", "request_upload", "handoff"}:
        errors.append("route is invalid")
    for field in ("groups", "features", "identity_anchors", "history"):
        if not isinstance(report.get(field), list):
            errors.append(f"{field} must be a list")
    if not _text(report.get("rule_version")):
        errors.append("rule_version must be non-empty")
    source_map, source_errors = _maps(sources)
    errors.extend(source_errors)
    if errors and any(not isinstance(report.get(k), list) for k in ("groups", "features", "identity_anchors")):
        return errors

    if route == "request_upload":
        _, section_errors = _section_bodies(report.get("markdown", ""), FALLBACK_SECTIONS)
        errors.extend(section_errors)
        if any(report.get(k) for k in ("groups", "features", "identity_anchors")):
            errors.append("request_upload must not fabricate analysis")
        if any(s.get("kind") == "image" and s.get("readable") is True and s.get("active") is True for s in source_map.values()):
            errors.append("request_upload cannot ignore an active readable image")
        return errors
    if route == "handoff":
        if any(report.get(k) for k in ("groups", "features", "identity_anchors")):
            errors.append("handoff must not fabricate analysis")
        target = report.get("handoff_target")
        md = str(report.get("markdown", ""))
        if target or re.search(r"(?:自动|已经|已)\s*(?:转交|委派|开始执行)", md):
            errors.append("handoff may state the boundary but cannot claim an unverified delegation")
        if not _text(md):
            errors.append("handoff markdown must explain the boundary stop")
        return errors
    if route not in {"analyze", "correct"}:
        return errors

    if not report.get("groups") or not report.get("features"):
        errors.append("analysis requires groups and evidence-bearing features")
    if not any(s.get("kind") == "image" and s.get("readable") is True and s.get("active") is True for s in source_map.values()):
        errors.append("analysis requires at least one active readable image source")

    bodies, section_errors = _section_bodies(report.get("markdown", ""), SECTIONS)
    errors.extend(section_errors)
    groups: dict[str, dict[str, Any]] = {}
    for i, group in enumerate(report.get("groups", [])):
        path = f"groups[{i}]"
        required_group = {"id", "kind", "image_ids", "relation", "parent_id", "basis", "confidence"}
        if not isinstance(group, dict):
            errors.append(f"{path} must be an object")
            continue
        if required_group - set(group):
            errors.append(f"{path} is incomplete")
        gid = group.get("id")
        if not _text(gid) or not GROUP_ID.fullmatch(gid):
            errors.append(f"{path}.id is invalid")
        elif gid in groups:
            errors.append(f"duplicate group {gid}")
        else:
            groups[gid] = group
        if group.get("kind") not in GROUP_KINDS or not isinstance(group.get("image_ids"), list) or not group.get("image_ids"):
            errors.append(f"{path} kind or image_ids is invalid")
        elif any(image_id not in source_map or source_map[image_id].get("kind") != "image" for image_id in group["image_ids"]):
            errors.append(f"{path}.image_ids contains an unregistered image source")
        if not _text(group.get("basis")) or group.get("confidence") not in CONFIDENCE:
            errors.append(f"{path} basis or confidence is invalid")
    for gid, group in groups.items():
        parent = group.get("parent_id")
        if group.get("kind") == "variant" and parent not in groups:
            errors.append(f"variant {gid} has no registered parent")
        if parent is not None and parent not in groups:
            errors.append(f"group {gid} has unknown parent")

    features: dict[str, dict[str, Any]] = {}
    for i, feature in enumerate(report.get("features", [])):
        errors.extend(_feature_errors(feature, groups, source_map, f"features[{i}]"))
        if isinstance(feature, dict) and _text(feature.get("id")):
            if feature["id"] in features:
                errors.append(f"duplicate feature {feature['id']}")
            features[feature["id"]] = feature
    for i, anchor in enumerate(report.get("identity_anchors", [])):
        path = f"identity_anchors[{i}]"
        if not isinstance(anchor, dict) or set(anchor) != {"group_id", "text", "feature_ids"}:
            errors.append(f"{path} is invalid")
            continue
        gid, text_value, ids = anchor.get("group_id"), anchor.get("text"), anchor.get("feature_ids")
        if gid not in groups or not _text(text_value) or not isinstance(ids, list) or not ids:
            errors.append(f"{path} is incomplete")
            continue
        permitted_values: list[str] = []
        for fid in ids:
            feature = features.get(fid)
            if not feature:
                errors.append(f"{path} cites unknown feature {fid}")
                continue
            owner = feature.get("group_id")
            parent = groups.get(gid, {}).get("parent_id")
            if owner not in {gid, parent}:
                errors.append(f"{path} borrows a sibling or unrelated feature")
            if feature.get("stability") not in {"身份不变量", "变体特征"} or feature.get("priority") not in {"P0", "P1"} or feature.get("evidence_type") in {"冲突", "不可判断"} or feature.get("confidence", {}).get("level") == "低":
                errors.append(f"{path} uses an ineligible feature")
            if _photometric_anchor_risk(feature, source_map):
                errors.append(f"{path} uses a single-image photometric colour feature")
            permitted_values.append(str(feature.get("value", "")))
        compact_anchor = re.sub(r"[，,、；;。\s]", "", str(text_value))
        compact_values = "".join(re.sub(r"[，,、；;。\s]", "", v) for v in permitted_values)
        remainder = compact_anchor
        for value in sorted((re.sub(r"[，,、；;。\s]", "", v) for v in permitted_values), key=len, reverse=True):
            remainder = remainder.replace(value, "", 1)
        if remainder or not compact_values:
            errors.append(f"{path}.text contains unsupported claims")

    if len(bodies) == 7 and route == "analyze":
        feature_body, anchor_body = bodies[2], bodies[3]
        for feature in features.values():
            tokens = [feature.get("name"), feature.get("value"), feature.get("evidence_type"), feature.get("stability"), feature.get("priority"), feature.get("confidence", {}).get("level"), feature.get("confidence", {}).get("reason")]
            for citation in feature.get("evidence", []):
                tokens.extend((citation.get("source_id"), citation.get("location")))
            if any(_text(t) and str(t) not in feature_body for t in tokens):
                errors.append(f"actual feature body does not match sidecar feature {feature.get('id')}")
        for anchor in report.get("identity_anchors", []):
            if isinstance(anchor, dict) and (_text(anchor.get("group_id")) and anchor["group_id"] not in anchor_body or _text(anchor.get("text")) and anchor["text"] not in anchor_body):
                errors.append(f"actual anchor body does not match sidecar group {anchor.get('group_id')}")
    return errors


def _by_id(items: list[Any], key: str = "id") -> dict[str, Any]:
    return {item[key]: item for item in items if isinstance(item, dict) and _text(item.get(key))}


def validate_update(before: Any, after: Any, event: Any, sources: Any) -> list[str]:
    """Validate field-local incremental evolution plus its delivered delta."""
    try:
        errors = validate_report(after, sources)
        if not isinstance(before, dict) or not isinstance(after, dict) or not isinstance(event, dict):
            return errors + ["before, after and event must be objects"]
        kind = event.get("kind")
        if kind not in {"add_image", "correct", "revoke_confirmation", "rule_change"}:
            errors.append("event kind is invalid")
        affected = event.get("affected_feature_ids")
        if not isinstance(affected, list) or not affected or any(not _text(x) for x in affected):
            return errors + ["affected_feature_ids must be a non-empty list"]
        affected_set = set(affected)
        old_features, new_features = _by_id(before.get("features", [])), _by_id(after.get("features", []))
        actual = {fid for fid in old_features.keys() | new_features.keys() if old_features.get(fid) != new_features.get(fid)}
        if actual != affected_set:
            errors.append("actual feature delta must exactly match affected_feature_ids")
        old_groups, new_groups = _by_id(before.get("groups", [])), _by_id(after.get("groups", []))
        old_anchors = _by_id(before.get("identity_anchors", []), "group_id")
        new_anchors = _by_id(after.get("identity_anchors", []), "group_id")
        affected_groups = {new_features.get(fid, old_features.get(fid, {})).get("group_id") for fid in affected_set}
        parent_groups = {new_groups.get(g, old_groups.get(g, {})).get("parent_id") for g in affected_groups}
        allowed_groups = affected_groups | parent_groups
        for gid in old_groups.keys() | new_groups.keys():
            old, new = old_groups.get(gid), new_groups.get(gid)
            if kind == "add_image" and gid in allowed_groups:
                if old and new:
                    a, b = old.get("image_ids", []), new.get("image_ids", [])
                    if b[:len(a)] != a or any(k != "image_ids" and old.get(k) != new.get(k) for k in old):
                        errors.append(f"add_image rewrote group {gid}")
                continue
            if old != new:
                errors.append(f"unaffected group {gid} changed")
        changed_anchor_groups = {gid for gid in old_anchors.keys() | new_anchors.keys() if old_anchors.get(gid) != new_anchors.get(gid)}
        if not affected_groups.issubset(changed_anchor_groups):
            errors.append("dependent anchor was not updated")
        if changed_anchor_groups - affected_groups:
            errors.append("an unaffected anchor changed")
        old_history, new_history = before.get("history", []), after.get("history", [])
        if not isinstance(old_history, list) or not isinstance(new_history, list) or new_history[:len(old_history)] != old_history:
            errors.append("history prefix was rewritten")
        appended = new_history[len(old_history):] if isinstance(new_history, list) and isinstance(old_history, list) else []
        if len(appended) != len(affected_set):
            errors.append("one immutable history record is required per affected field")
        for record in appended:
            if not isinstance(record, dict) or record.get("kind") != kind or record.get("feature_id") not in affected_set or record.get("before") != old_features.get(record.get("feature_id")) or record.get("after") != new_features.get(record.get("feature_id")):
                errors.append("history record does not preserve the full before/after state")
        if kind == "rule_change":
            if event.get("rule_version") != after.get("rule_version") or before.get("rule_version") == after.get("rule_version"):
                errors.append("rule change version is missing or mismatched")
            for fid in affected_set:
                old, new = old_features.get(fid, {}), new_features.get(fid, {})
                for key in ("value", "evidence", "evidence_type", "stability", "priority"):
                    if old.get(key) != new.get(key):
                        errors.append(f"rule change rewrote observed field {fid}.{key}")
        elif before.get("rule_version") != after.get("rule_version"):
            errors.append("non-rule update changed rule_version")
        if kind == "correct":
            sid = event.get("source_id")
            source_map, _ = _maps(sources)
            if sid not in source_map or source_map[sid].get("kind") != "user" or source_map[sid].get("active") is not True:
                errors.append("correction requires an active trusted user source")
            for fid in affected_set:
                new = new_features.get(fid, {})
                if new.get("evidence_type") != "用户确认" or not any(e.get("source_id") == sid for e in new.get("evidence", []) if isinstance(e, dict)):
                    errors.append("correction provenance was laundered or lost")
        if kind == "revoke_confirmation":
            sid = event.get("source_id")
            source_map, _ = _maps(sources)
            if sid in source_map and source_map[sid].get("active") is not False:
                errors.append("revoked user source remains active")
            for feature in new_features.values():
                if any(e.get("source_id") == sid for e in feature.get("evidence", []) if isinstance(e, dict)):
                    errors.append("revoked confirmation remains in active evidence")
        markdown = str(after.get("markdown", ""))
        if markdown == str(before.get("markdown", "")) or not re.search(r"(?m)^#{1,6}\s+变更摘要\s*$", markdown):
            errors.append("actual delta and 变更摘要 are required")
        delta_bodies, delta_errors = _section_bodies(markdown, SECTIONS)
        errors.extend(delta_errors)
        if len(delta_bodies) == 7:
            for fid in affected_set:
                feature = new_features.get(fid, {})
                tokens = [feature.get("name"), feature.get("value"), feature.get("evidence_type"),
                          feature.get("stability"), feature.get("priority"),
                          feature.get("confidence", {}).get("level"),
                          feature.get("confidence", {}).get("reason")]
                for citation in feature.get("evidence", []):
                    tokens.extend((citation.get("source_id"), citation.get("location")))
                if any(_text(t) and str(t) not in delta_bodies[2] for t in tokens):
                    errors.append(f"actual delta feature body does not match {fid}")
            for gid in changed_anchor_groups:
                anchor = new_anchors.get(gid)
                if anchor and (str(gid) not in delta_bodies[3] or str(anchor.get("text", "")) not in delta_bodies[3]):
                    errors.append(f"actual delta anchor body does not match {gid}")
        return errors
    except Exception as exc:
        return [f"malformed update: {type(exc).__name__}: {exc}"]


def main(argv: list[str]) -> int:
    if len(argv) not in {3, 5}:
        print("usage: output_guard.py REPORT.json SOURCES.json [BEFORE.json EVENT.json]", file=sys.stderr)
        return 2
    report = json.loads(Path(argv[1]).read_text(encoding="utf-8-sig"))
    sources = json.loads(Path(argv[2]).read_text(encoding="utf-8-sig"))
    if len(argv) == 3:
        errors = validate_report(report, sources)
    else:
        before = json.loads(Path(argv[3]).read_text(encoding="utf-8-sig"))
        event = json.loads(Path(argv[4]).read_text(encoding="utf-8-sig"))
        errors = validate_update(before, report, event, sources)
    print(json.dumps({"passed": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
