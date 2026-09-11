#!/usr/bin/env python3
"""Validate sg-shiwu's deterministic contracts and Golden Set manifests."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
SKILL_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_SECTIONS = (
    "输入质量审计与图片编号",
    "产品/变体/配件/包装/道具分组",
    "视觉指纹证据表",
    "工具中立的固定身份锚点",
    "场景变量",
    "负面约束与易漂移点",
    "未知、冲突和最小补拍清单",
)
DEGRADED_SECTIONS = (
    "无法分析的原因",
    "未做出的结论",
    "最小上传清单",
)

CASE_KINDS = frozenset(
    {"positive", "degraded", "conflict", "security", "correction", "antitrigger"}
)
ROUTES = frozenset({"analyze", "correct", "request_upload", "handoff"})
GROUPING_MODES = frozenset(
    {
        "single_product",
        "same_sku_multi_view",
        "separate_variants",
        "separate_products",
        "classify_objects",
        "undetermined",
        "not_applicable",
    }
)
SOURCE_KINDS = frozenset({"uploaded", "local", "url"})
AVAILABILITY_VALUES = frozenset({"readable", "degraded", "unavailable"})

EVIDENCE_TYPES = frozenset({"清晰观察", "用户确认", "外观推断", "冲突", "不可判断"})
STABILITY_VALUES = frozenset({"身份不变量", "变体特征", "状态变量", "拍摄伪影", "未知"})
PRIORITIES = frozenset({"P0", "P1", "P2"})
CONFIDENCE_LEVELS = frozenset({"高", "中", "低"})

FEATURE_REQUIRED_KEYS = frozenset(
    {"id", "name", "value", "evidence", "evidence_type", "stability", "priority", "confidence"}
)
OUTPUT_REQUIRED_KEYS = frozenset(
    {
        "route",
        "handoff_target",
        "section_order",
        "groups",
        "features",
        "identity_anchors",
        "correction",
    }
)

SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
CASE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
IMAGE_ID_RE = re.compile(r"^IMG-\d{2,}$")
USER_SOURCE_ID_RE = re.compile(r"^USER-\d{2,}$")

# Each requirement is satisfied when at least one alias occurs anywhere in the set.
COVERAGE_REQUIREMENTS = {
    "single image": frozenset({"single_image", "single_product"}),
    "multiple angles": frozenset({"multi_angle", "multiple_angles"}),
    "same model in multiple colors": frozenset(
        {"same_model_multicolor", "same_model_multi_color", "color_variants"}
    ),
    "mixed SKU": frozenset({"mixed_sku", "different_sku"}),
    "accessory": frozenset({"accessory", "accessories"}),
    "packaging": frozenset({"packaging", "package"}),
    "prop": frozenset({"prop", "props"}),
    "transparent object": frozenset({"transparent", "transparency"}),
    "mirror or reflective object": frozenset({"mirror", "reflective", "reflection"}),
    "soft object": frozenset({"soft_body", "soft_object", "soft_goods"}),
    "color cast": frozenset({"color_cast", "colour_cast"}),
    "low resolution": frozenset({"low_resolution", "low_res"}),
    "crop": frozenset({"cropped", "crop"}),
    "occlusion": frozenset({"occluded", "occlusion"}),
    "no scale": frozenset({"no_scale", "missing_scale"}),
    "blurred text": frozenset({"blurred_text", "unreadable_text"}),
    "specification conflict": frozenset({"spec_conflict", "specification_conflict"}),
    "photo and render conflict": frozenset({"photo_render_conflict", "render_conflict"}),
    "URL only": frozenset({"url_only", "unreadable_url"}),
    "no image": frozenset({"no_image", "missing_image"}),
    "prompt injection": frozenset({"prompt_injection", "embedded_instruction"}),
    "correction": frozenset({"correction", "user_correction"}),
    "direct image generation": frozenset({"direct_image_generation", "direct_image_edit"}),
    "sg-product boundary": frozenset({"adjacent_sg_product", "product_decision"}),
    "sg-review boundary": frozenset({"adjacent_sg_review", "review_voc"}),
    "sg-insight boundary": frozenset({"adjacent_sg_insight", "market_insight"}),
    "generic OCR boundary": frozenset({"generic_ocr"}),
    "Listing copy boundary": frozenset({"listing_copy", "listing_writing"}),
}


def _exact_keys(value: Any, expected: set[str] | frozenset[str], path: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{path} must be an object"]
    actual = set(value)
    errors: list[str] = []
    missing = sorted(set(expected) - actual)
    extra = sorted(actual - set(expected))
    if missing:
        errors.append(f"{path} missing keys: {', '.join(missing)}")
    if extra:
        errors.append(f"{path} has unexpected keys: {', '.join(extra)}")
    return errors


def _nonempty_string(value: Any, path: str) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        return [f"{path} must be a non-empty string"]
    return []


def _token_list(value: Any, path: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list):
        return [f"{path} must be a list"]
    errors: list[str] = []
    if not value and not allow_empty:
        errors.append(f"{path} must not be empty")
    seen: set[str] = set()
    for index, token in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(token, str) or not SNAKE_CASE_RE.fullmatch(token):
            errors.append(f"{item_path} must be a snake_case string")
            continue
        if token in seen:
            errors.append(f"{item_path} duplicates '{token}'")
        seen.add(token)
    return errors


def _validate_manifest_list_item(value: Any, path: str) -> list[str]:
    if isinstance(value, str):
        return _nonempty_string(value, path)
    if not isinstance(value, dict) or not value:
        return [f"{path} must be a non-empty string or object"]
    errors: list[str] = []
    for key, item in value.items():
        errors.extend(_nonempty_string(key, f"{path} key"))
        if not isinstance(item, (str, int, float, bool)) or isinstance(item, str) and not item.strip():
            errors.append(f"{path}.{key} must be a non-empty scalar")
    return errors


def _validate_image_manifest(value: Any, path: str) -> list[str]:
    errors = _exact_keys(
        value,
        frozenset({"id", "source_kind", "availability", "quality_flags"}),
        path,
    )
    if not isinstance(value, dict):
        return errors

    image_id = value.get("id")
    if not isinstance(image_id, str) or not IMAGE_ID_RE.fullmatch(image_id):
        errors.append(f"{path}.id must match IMG-nn")
    if value.get("source_kind") not in SOURCE_KINDS:
        errors.append(f"{path}.source_kind must be one of {sorted(SOURCE_KINDS)}")
    if value.get("availability") not in AVAILABILITY_VALUES:
        errors.append(f"{path}.availability must be one of {sorted(AVAILABILITY_VALUES)}")
    errors.extend(_token_list(value.get("quality_flags"), f"{path}.quality_flags", allow_empty=True))
    return errors


def _expected_sections(route: str) -> tuple[str, ...]:
    if route in {"analyze", "correct"}:
        return REQUIRED_SECTIONS
    if route == "request_upload":
        return DEGRADED_SECTIONS
    return ()


def _apply_tag_rules(case: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    tags = set(case.get("tags", [])) if isinstance(case.get("tags"), list) else set()
    expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
    route = expected.get("route")
    grouping = expected.get("grouping")
    def require(tag_aliases: set[str], *, wanted_route: str, wanted_grouping: str) -> None:
        if not tags.intersection(tag_aliases):
            return
        if route != wanted_route:
            errors.append(f"tags {sorted(tags.intersection(tag_aliases))} require route '{wanted_route}'")
        if grouping != wanted_grouping:
            errors.append(
                f"tags {sorted(tags.intersection(tag_aliases))} require grouping '{wanted_grouping}'"
            )

    require({"multi_angle", "multiple_angles"}, wanted_route="analyze", wanted_grouping="same_sku_multi_view")
    require(
        {"same_model_multicolor", "same_model_multi_color", "color_variants"},
        wanted_route="analyze",
        wanted_grouping="separate_variants",
    )
    require({"mixed_sku", "different_sku"}, wanted_route="analyze", wanted_grouping="separate_products")
    if {"accessory", "packaging", "prop"}.issubset(tags):
        if route != "analyze" or grouping != "classify_objects":
            errors.append("accessory, packaging and prop tags require analyze/classify_objects")
    require({"url_only", "unreadable_url"}, wanted_route="request_upload", wanted_grouping="undetermined")
    require({"no_image", "missing_image"}, wanted_route="request_upload", wanted_grouping="undetermined")
    require({"correction", "user_correction"}, wanted_route="correct", wanted_grouping=grouping)
    require(
        {"direct_image_generation", "direct_image_edit"},
        wanted_route="handoff",
        wanted_grouping="not_applicable",
    )
    require(
        {"adjacent_sg_product", "product_decision"},
        wanted_route="handoff",
        wanted_grouping="not_applicable",
    )
    require(
        {"adjacent_sg_review", "review_voc"},
        wanted_route="handoff",
        wanted_grouping="not_applicable",
    )
    require(
        {"adjacent_sg_insight", "market_insight"},
        wanted_route="handoff",
        wanted_grouping="not_applicable",
    )
    require({"generic_ocr"}, wanted_route="handoff", wanted_grouping="not_applicable")
    require({"listing_copy", "listing_writing"}, wanted_route="handoff", wanted_grouping="not_applicable")
    return errors


def validate_case(case: Any, directory_name: str | None = None) -> list[str]:
    """Return every deterministic contract error in one Golden Set manifest."""
    required_keys = frozenset(
        {"schema_version", "case_id", "title", "kind", "tags", "request", "input_manifest", "expected"}
    )
    errors = _exact_keys(case, required_keys, "case")
    if not isinstance(case, dict):
        return errors

    if case.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")

    case_id = case.get("case_id")
    if not isinstance(case_id, str) or not CASE_ID_RE.fullmatch(case_id):
        errors.append("case_id must be lowercase hyphen-case")
    elif directory_name is not None and case_id != directory_name:
        errors.append(f"case_id '{case_id}' must match directory '{directory_name}'")
    errors.extend(_nonempty_string(case.get("title"), "title"))
    errors.extend(_nonempty_string(case.get("request"), "request"))

    if case.get("kind") not in CASE_KINDS:
        errors.append(f"kind must be one of {sorted(CASE_KINDS)}")
    errors.extend(_token_list(case.get("tags"), "tags"))

    manifest = case.get("input_manifest")
    errors.extend(
        _exact_keys(
            manifest,
            frozenset({"images", "trusted_user_facts", "untrusted_payloads"}),
            "input_manifest",
        )
    )
    image_ids: set[str] = set()
    available_images = 0
    if isinstance(manifest, dict):
        images = manifest.get("images")
        if not isinstance(images, list):
            errors.append("input_manifest.images must be a list")
        else:
            for index, image in enumerate(images):
                path = f"input_manifest.images[{index}]"
                errors.extend(_validate_image_manifest(image, path))
                if isinstance(image, dict):
                    image_id = image.get("id")
                    if isinstance(image_id, str):
                        if image_id in image_ids:
                            errors.append(f"{path}.id duplicates '{image_id}'")
                        image_ids.add(image_id)
                    if image.get("availability") in {"readable", "degraded"}:
                        available_images += 1

        for field in ("trusted_user_facts", "untrusted_payloads"):
            items = manifest.get(field)
            if not isinstance(items, list):
                errors.append(f"input_manifest.{field} must be a list")
                continue
            for index, item in enumerate(items):
                errors.extend(_validate_manifest_list_item(item, f"input_manifest.{field}[{index}]"))

    expected = case.get("expected")
    errors.extend(
        _exact_keys(
            expected,
            frozenset(
                {"route", "handoff_target", "grouping", "required_sections", "must_assert", "must_not_claim"}
            ),
            "expected",
        )
    )
    if isinstance(expected, dict):
        route = expected.get("route")
        target = expected.get("handoff_target")
        grouping = expected.get("grouping")
        if route not in ROUTES:
            errors.append(f"expected.route must be one of {sorted(ROUTES)}")
        if target is not None:
            errors.append("expected.handoff_target must be null; boundary stops do not claim delegation")
        if route != "handoff" and target is not None:
            errors.append("expected.handoff_target must be null unless route is handoff")
        if grouping not in GROUPING_MODES:
            errors.append(f"expected.grouping must be one of {sorted(GROUPING_MODES)}")

        sections = expected.get("required_sections")
        if not isinstance(sections, list) or any(not isinstance(item, str) for item in sections):
            errors.append("expected.required_sections must be a list of strings")
        elif route in ROUTES and tuple(sections) != _expected_sections(route):
            errors.append(f"expected.required_sections do not match route '{route}'")

        errors.extend(_token_list(expected.get("must_assert"), "expected.must_assert"))
        errors.extend(_token_list(expected.get("must_not_claim"), "expected.must_not_claim"))

        if route in {"analyze", "correct"} and available_images == 0:
            errors.append(f"route '{route}' requires at least one readable or degraded image")
        if route == "request_upload" and available_images:
            errors.append("request_upload must not be used when a readable or degraded image is available")
        if route == "handoff" and grouping != "not_applicable":
            errors.append("handoff route requires not_applicable grouping")
        if route == "request_upload" and grouping != "undetermined":
            errors.append("request_upload route requires undetermined grouping")

    errors.extend(_apply_tag_rules(case))
    return errors


def validate_feature_record(record: Any, known_source_ids: Iterable[str]) -> list[str]:
    """Validate a machine-readable feature row used by contract tests."""
    errors = _exact_keys(record, FEATURE_REQUIRED_KEYS, "feature")
    if not isinstance(record, dict):
        return errors

    for field in ("id", "name", "value"):
        errors.extend(_nonempty_string(record.get(field), f"feature.{field}"))

    evidence_type = record.get("evidence_type")
    stability = record.get("stability")
    priority = record.get("priority")
    if evidence_type not in EVIDENCE_TYPES:
        errors.append(f"feature.evidence_type must be one of {sorted(EVIDENCE_TYPES)}")
    if stability not in STABILITY_VALUES:
        errors.append(f"feature.stability must be one of {sorted(STABILITY_VALUES)}")
    if priority not in PRIORITIES:
        errors.append(f"feature.priority must be one of {sorted(PRIORITIES)}")

    known_sources = set(known_source_ids)
    cited_sources: list[str] = []
    evidence = record.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append("feature.evidence must be a non-empty list")
    else:
        for index, citation in enumerate(evidence):
            path = f"feature.evidence[{index}]"
            errors.extend(_exact_keys(citation, frozenset({"source_id", "location"}), path))
            if not isinstance(citation, dict):
                continue
            source_id = citation.get("source_id")
            if not isinstance(source_id, str) or not (
                IMAGE_ID_RE.fullmatch(source_id) or USER_SOURCE_ID_RE.fullmatch(source_id)
            ):
                errors.append(f"{path}.source_id must match IMG-nn or USER-nn")
            else:
                cited_sources.append(source_id)
                if source_id not in known_sources:
                    errors.append(f"{path}.source_id '{source_id}' is not registered")
            errors.extend(_nonempty_string(citation.get("location"), f"{path}.location"))

    confidence = record.get("confidence")
    errors.extend(_exact_keys(confidence, frozenset({"level", "reason"}), "feature.confidence"))
    confidence_level = confidence.get("level") if isinstance(confidence, dict) else None
    if isinstance(confidence, dict):
        if confidence_level not in CONFIDENCE_LEVELS:
            errors.append(f"feature.confidence.level must be one of {sorted(CONFIDENCE_LEVELS)}")
        errors.extend(_nonempty_string(confidence.get("reason"), "feature.confidence.reason"))

    image_sources = {source for source in cited_sources if IMAGE_ID_RE.fullmatch(source)}
    user_sources = {source for source in cited_sources if USER_SOURCE_ID_RE.fullmatch(source)}
    if evidence_type == "用户确认":
        if not user_sources:
            errors.append("用户确认 evidence must cite a registered USER-nn source")
    elif evidence_type in EVIDENCE_TYPES and not image_sources:
        errors.append(f"{evidence_type} evidence must cite at least one IMG-nn source")

    if evidence_type == "冲突" and len(set(cited_sources)) < 2:
        errors.append("冲突 evidence must cite at least two distinct sources")
    if evidence_type in {"外观推断", "冲突", "不可判断"} and confidence_level == "高":
        errors.append(f"{evidence_type} evidence cannot have high confidence")
    value = record.get("value")
    if evidence_type == "不可判断" and isinstance(value, str) and "不可判断" not in value:
        errors.append("不可判断 evidence must state 不可判断 in its value")
    if evidence_type == "外观推断" and isinstance(value, str) and not any(
        qualifier in value for qualifier in ("视觉呈现", "疑似", "可能")
    ):
        errors.append("外观推断 value must contain a visible uncertainty qualifier")
    return errors


def _validate_group(group: Any, known_image_ids: set[str], path: str) -> list[str]:
    errors = _exact_keys(group, frozenset({"id", "kind", "image_ids", "relation"}), path)
    if not isinstance(group, dict):
        return errors
    errors.extend(_nonempty_string(group.get("id"), f"{path}.id"))
    if group.get("kind") not in {"product", "variant", "accessory", "packaging", "prop", "unknown"}:
        errors.append(f"{path}.kind is invalid")
    if group.get("relation") not in {
        "same_sku",
        "color_variant",
        "different_sku",
        "unknown",
        "not_applicable",
    }:
        errors.append(f"{path}.relation is invalid")
    image_ids = group.get("image_ids")
    if not isinstance(image_ids, list) or not image_ids:
        errors.append(f"{path}.image_ids must be a non-empty list")
    else:
        seen: set[str] = set()
        for index, image_id in enumerate(image_ids):
            item_path = f"{path}.image_ids[{index}]"
            if not isinstance(image_id, str) or image_id not in known_image_ids:
                errors.append(f"{item_path} must reference a registered image")
            elif image_id in seen:
                errors.append(f"{item_path} duplicates '{image_id}'")
            seen.add(image_id)
    return errors


def _validate_correction_metadata(value: Any, feature_ids: set[str]) -> list[str]:
    errors = _exact_keys(value, frozenset({"changed_feature_ids", "change_summary"}), "correction")
    if not isinstance(value, dict):
        return errors

    changed = value.get("changed_feature_ids")
    changed_ids: set[str] = set()
    if not isinstance(changed, list) or not changed:
        errors.append("correction.changed_feature_ids must be a non-empty list")
    else:
        for index, feature_id in enumerate(changed):
            path = f"correction.changed_feature_ids[{index}]"
            if not isinstance(feature_id, str) or feature_id not in feature_ids:
                errors.append(f"{path} must reference an existing feature")
            elif feature_id in changed_ids:
                errors.append(f"{path} duplicates '{feature_id}'")
            changed_ids.add(feature_id)

    summaries = value.get("change_summary")
    summary_ids: set[str] = set()
    if not isinstance(summaries, list) or not summaries:
        errors.append("correction.change_summary must be a non-empty list")
    else:
        for index, summary in enumerate(summaries):
            path = f"correction.change_summary[{index}]"
            errors.extend(
                _exact_keys(summary, frozenset({"feature_id", "from", "to", "source", "reason"}), path)
            )
            if not isinstance(summary, dict):
                continue
            feature_id = summary.get("feature_id")
            if not isinstance(feature_id, str) or feature_id not in changed_ids:
                errors.append(f"{path}.feature_id must reference a declared changed feature")
            elif feature_id in summary_ids:
                errors.append(f"{path}.feature_id duplicates '{feature_id}'")
            summary_ids.add(feature_id) if isinstance(feature_id, str) else None
            for field in ("from", "to", "source", "reason"):
                errors.extend(_nonempty_string(summary.get(field), f"{path}.{field}"))
    if changed_ids != summary_ids:
        errors.append("correction change_summary must cover changed_feature_ids exactly once")
    return errors


def validate_output_contract(output: Any, known_source_ids: Iterable[str]) -> list[str]:
    """Validate a structured representative output without judging image semantics."""
    errors = _exact_keys(output, OUTPUT_REQUIRED_KEYS, "output")
    if not isinstance(output, dict):
        return errors

    route = output.get("route")
    target = output.get("handoff_target")
    if route not in ROUTES:
        errors.append(f"output.route must be one of {sorted(ROUTES)}")
    if target is not None:
        errors.append("output.handoff_target must be null; boundary stops do not claim delegation")
    if route != "handoff" and target is not None:
        errors.append("output.handoff_target must be null unless route is handoff")

    sections = output.get("section_order")
    if not isinstance(sections, list) or tuple(sections) != _expected_sections(route):
        errors.append(f"output.section_order does not match route '{route}'")

    known_sources = set(known_source_ids)
    known_image_ids = {source for source in known_sources if IMAGE_ID_RE.fullmatch(source)}
    groups = output.get("groups")
    group_ids: set[str] = set()
    if not isinstance(groups, list):
        errors.append("output.groups must be a list")
    else:
        for index, group in enumerate(groups):
            path = f"output.groups[{index}]"
            errors.extend(_validate_group(group, known_image_ids, path))
            if isinstance(group, dict) and isinstance(group.get("id"), str):
                group_id = group["id"]
                if group_id in group_ids:
                    errors.append(f"{path}.id duplicates '{group_id}'")
                group_ids.add(group_id)

    features = output.get("features")
    feature_by_id: dict[str, dict[str, Any]] = {}
    if not isinstance(features, list):
        errors.append("output.features must be a list")
    else:
        for index, feature in enumerate(features):
            feature_errors = validate_feature_record(feature, known_sources)
            errors.extend(f"output.features[{index}]: {error}" for error in feature_errors)
            if isinstance(feature, dict) and isinstance(feature.get("id"), str):
                feature_id = feature["id"]
                if feature_id in feature_by_id:
                    errors.append(f"output.features[{index}].id duplicates '{feature_id}'")
                feature_by_id[feature_id] = feature

    anchors = output.get("identity_anchors")
    if not isinstance(anchors, list):
        errors.append("output.identity_anchors must be a list")
    else:
        for index, anchor in enumerate(anchors):
            path = f"output.identity_anchors[{index}]"
            errors.extend(_exact_keys(anchor, frozenset({"group_id", "text", "feature_ids"}), path))
            if not isinstance(anchor, dict):
                continue
            if anchor.get("group_id") not in group_ids:
                errors.append(f"{path}.group_id must reference an existing group")
            errors.extend(_nonempty_string(anchor.get("text"), f"{path}.text"))
            feature_ids = anchor.get("feature_ids")
            if not isinstance(feature_ids, list) or not feature_ids:
                errors.append(f"{path}.feature_ids must be a non-empty list")
                continue
            seen: set[str] = set()
            for feature_id in feature_ids:
                if not isinstance(feature_id, str) or feature_id not in feature_by_id:
                    errors.append(f"{path}.feature_ids must reference existing features")
                    continue
                if feature_id in seen:
                    errors.append(f"{path}.feature_ids duplicates '{feature_id}'")
                seen.add(feature_id)
                feature = feature_by_id[feature_id]
                if feature.get("priority") not in {"P0", "P1"}:
                    errors.append(f"{path} may only cite P0/P1 features")
                if feature.get("stability") not in {"身份不变量", "变体特征"}:
                    errors.append(f"{path} cites a non-identity stability value")
                if feature.get("evidence_type") in {"冲突", "不可判断"}:
                    errors.append(f"{path} cites unresolved evidence")

    correction = output.get("correction")
    if route == "correct":
        errors.extend(_validate_correction_metadata(correction, set(feature_by_id)))
    elif correction is not None:
        errors.append("output.correction must be null unless route is correct")

    if route in {"request_upload", "handoff"} and any((groups, features, anchors)):
        errors.append(f"route '{route}' must not fabricate groups, features, or identity anchors")
    if route in {"analyze", "correct"} and not groups:
        errors.append(f"route '{route}' requires at least one group")
    return errors


def validate_correction(previous_output: Any, corrected_output: Any) -> list[str]:
    """Check field-local correction and preservation of user-confirmed provenance."""
    if not isinstance(previous_output, dict) or not isinstance(corrected_output, dict):
        return ["previous_output and corrected_output must be objects"]
    errors: list[str] = []
    previous_features = previous_output.get("features")
    corrected_features = corrected_output.get("features")
    if not isinstance(previous_features, list) or not isinstance(corrected_features, list):
        return ["both outputs must contain feature lists"]

    old_by_id = {
        item.get("id"): item
        for item in previous_features
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    new_by_id = {
        item.get("id"): item
        for item in corrected_features
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if set(old_by_id) != set(new_by_id):
        errors.append("correction must not add or remove feature rows")
        return errors

    correction = corrected_output.get("correction")
    if not isinstance(correction, dict):
        return ["corrected_output.correction must be an object"]
    declared = correction.get("changed_feature_ids")
    declared_ids = set(declared) if isinstance(declared, list) else set()
    actual_ids = {feature_id for feature_id in old_by_id if old_by_id[feature_id] != new_by_id[feature_id]}
    if declared_ids != actual_ids:
        errors.append("changed_feature_ids must match the feature rows that actually changed")

    summaries = correction.get("change_summary")
    summary_by_id = {
        item.get("feature_id"): item
        for item in summaries or []
        if isinstance(item, dict) and isinstance(item.get("feature_id"), str)
    }
    for feature_id in actual_ids:
        summary = summary_by_id.get(feature_id)
        if not summary:
            continue
        if summary.get("from") != old_by_id[feature_id].get("value"):
            errors.append(f"change_summary for '{feature_id}' has the wrong from value")
        if summary.get("to") != new_by_id[feature_id].get("value"):
            errors.append(f"change_summary for '{feature_id}' has the wrong to value")

        old_feature = old_by_id[feature_id]
        new_feature = new_by_id[feature_id]
        if old_feature.get("evidence_type") == "用户确认":
            old_user_sources = {
                evidence.get("source_id")
                for evidence in old_feature.get("evidence", [])
                if isinstance(evidence, dict) and isinstance(evidence.get("source_id"), str)
                and USER_SOURCE_ID_RE.fullmatch(evidence["source_id"])
            }
            new_user_sources = {
                evidence.get("source_id")
                for evidence in new_feature.get("evidence", [])
                if isinstance(evidence, dict) and isinstance(evidence.get("source_id"), str)
                and USER_SOURCE_ID_RE.fullmatch(evidence["source_id"])
            }
            if not old_user_sources.issubset(new_user_sources):
                errors.append(f"correction for '{feature_id}' dropped user-confirmed provenance")

    if previous_output.get("groups") != corrected_output.get("groups"):
        errors.append("field-local correction must preserve unaffected grouping")
    return errors


def evaluate_all(skill_root: Path | str = SKILL_ROOT) -> dict[str, Any]:
    """Evaluate every case, aggregate errors, and never stop at the first failure."""
    root = Path(skill_root)
    fixtures_root = root / "tests" / "fixtures"
    global_errors: list[str] = []
    case_results: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []

    if not fixtures_root.is_dir():
        return {
            "total": 0,
            "passed": 0,
            "case_results": [],
            "errors": [f"fixtures directory not found: {fixtures_root}"],
        }

    fixture_dirs = sorted(path for path in fixtures_root.iterdir() if path.is_dir())
    if len(fixture_dirs) < 20:
        global_errors.append(f"Golden Set requires at least 20 cases; found {len(fixture_dirs)}")

    seen_case_ids: set[str] = set()
    all_tags: set[str] = set()
    for fixture_dir in fixture_dirs:
        case_path = fixture_dir / "case.json"
        case_errors: list[str] = []
        case_id = fixture_dir.name
        if not case_path.is_file():
            case_errors.append("case.json not found")
        else:
            try:
                case = json.loads(case_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                case_errors.append(f"cannot read valid UTF-8 JSON: {exc}")
            else:
                case_errors.extend(validate_case(case, fixture_dir.name))
                if isinstance(case, dict):
                    cases.append(case)
                    actual_id = case.get("case_id")
                    if isinstance(actual_id, str):
                        case_id = actual_id
                        if actual_id in seen_case_ids:
                            case_errors.append(f"duplicate case_id '{actual_id}'")
                        seen_case_ids.add(actual_id)
                    tags = case.get("tags")
                    if isinstance(tags, list):
                        all_tags.update(tag for tag in tags if isinstance(tag, str))
        case_results.append({"case_id": case_id, "errors": case_errors})

    missing_coverage = [
        label
        for label, aliases in COVERAGE_REQUIREMENTS.items()
        if not all_tags.intersection(aliases)
    ]
    if missing_coverage:
        global_errors.append("Golden Set missing coverage: " + ", ".join(missing_coverage))

    passed = sum(not result["errors"] for result in case_results)
    return {
        "total": len(fixture_dirs),
        "passed": passed,
        "case_results": case_results,
        "errors": global_errors,
    }


def main() -> int:
    summary = evaluate_all()
    print("CONTRACT_ONLY: sg-shiwu deterministic contract evaluation")
    print("说明：本程序只验证结构、路由、证据与输出合同，不验证视觉正确性。")
    for result in summary["case_results"]:
        if result["errors"]:
            print(f"[FAIL] {result['case_id']}")
            for error in result["errors"]:
                print(f"  - {error}")
        else:
            print(f"[PASS] {result['case_id']}")
    for error in summary["errors"]:
        print(f"[FAIL] GLOBAL: {error}")
    print(f"SUMMARY: {summary['passed']}/{summary['total']} case contracts passed")
    return 0 if summary["passed"] == summary["total"] and not summary["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
