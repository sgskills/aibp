"""Round-2 public output regressions using only new synthetic inputs."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from analyze_rankings import analyze_payload, render_markdown


def _period(
    index: int,
    rows: list[dict[str, Any]],
    *,
    platform: str = "天猫",
    category: str = "耳机",
    source_file: str | None = None,
) -> dict[str, Any]:
    start = 1 + index * 7
    return {
        "period": f"2026-07-{start:02d}~2026-07-{start + 6:02d}",
        "platform": platform,
        "scope": "全网",
        "category": category,
        "ranking_metric": "交易总量",
        "top_n": len(rows),
        "source_file": source_file or f"week{index + 1}.csv",
        "sheet": "Sheet1",
        "rows": rows,
    }


def _row(rank: int, product_id: str, **extra: Any) -> dict[str, Any]:
    return {
        "rank": rank,
        "product_id": product_id,
        "title": f"商品{product_id}",
        "shop": f"店铺{product_id}",
        **extra,
    }


def _stable_swap_payload() -> dict[str, Any]:
    return {
        "periods": [
            _period(0, [_row(1, "A"), _row(2, "B"), _row(3, "C"), _row(4, "D")]),
            _period(1, [_row(1, "B"), _row(2, "A"), _row(3, "C"), _row(4, "D")]),
        ]
    }


def _entrant_payload(*, platform: str = "天猫", category: str = "耳机", prefix: str = "") -> dict[str, Any]:
    return {
        "periods": [
            _period(
                0,
                [_row(1, f"{prefix}A"), _row(2, f"{prefix}B"), _row(3, f"{prefix}C"), _row(4, f"{prefix}D")],
                platform=platform,
                category=category,
                source_file=f"{prefix.lower()}week1.csv",
            ),
            _period(
                1,
                [_row(1, f"{prefix}E"), _row(2, f"{prefix}B"), _row(3, f"{prefix}C"), _row(4, f"{prefix}D")],
                platform=platform,
                category=category,
                source_file=f"{prefix.lower()}week2.csv",
            ),
        ]
    }


class ReleaseOutputSemanticsTests(unittest.TestCase):
    def test_pub_output_01_no_entrant_cannot_create_entry_opportunity_or_entry_actions(self) -> None:
        result = analyze_payload(_stable_swap_payload(), mode="deep")

        self.assertEqual(result["trajectories"]["entries"], [])
        self.assertNotIn("COMMON_WINDOW_ENTRY_TEST", [item["code"] for item in result["opportunities"]])
        self.assertTrue(
            all(action is None or action["code"] != "COMMON_WINDOW_ENTRY_TEST" for action in result["actions"].values())
        )

    def test_pub_output_01_positive_entrant_keeps_actual_object_and_source(self) -> None:
        result = analyze_payload(_entrant_payload(), mode="deep")
        opportunity = next(item for item in result["opportunities"] if item["code"] == "COMMON_WINDOW_ENTRY_TEST")

        self.assertEqual([item["product_id"] for item in opportunity["candidate_objects"]], ["E"])
        candidate = opportunity["candidate_objects"][0]
        self.assertEqual(candidate["rank"], 1)
        self.assertEqual(candidate["position"]["file"], "week2.csv")
        self.assertEqual(candidate["position"]["sheet"], "Sheet1")
        self.assertTrue(candidate["position"]["island_id"])
        self.assertTrue(all(action and action["candidate_objects"] == opportunity["candidate_objects"] for action in result["actions"].values()))

    def test_pub_output_02_deep_delivers_matched_rank_and_interval_evidence(self) -> None:
        payload = {
            "periods": [
                _period(
                    0,
                    [_row(1, "B"), _row(2, "A", buyers="220-260")],
                    source_file="week-before.csv",
                ),
                _period(
                    1,
                    [_row(1, "A", buyers="400-440"), _row(2, "B")],
                    source_file="week-after.csv",
                ),
            ]
        }
        result = analyze_payload(payload, mode="deep")
        markdown = render_markdown(result)

        match = next(item for item in result["trajectories"]["matched"] if item["product_id"] == "A")
        buyers = match["interval_observations"]["buyers"]
        self.assertEqual((buyers["before"]["lower"], buyers["before"]["upper"]), (220.0, 260.0))
        self.assertEqual((buyers["after"]["lower"], buyers["after"]["upper"]), (400.0, 440.0))
        self.assertEqual((buyers["change"]["lower_delta"], buyers["change"]["upper_delta"]), (140.0, 220.0))
        for fragment in (
            "### 代表性已匹配明细",
            "商品ID=A",
            "排名：2→1",
            "变化=+1",
            "前期区间=[220, 260]",
            "后期区间=[400, 440]",
            "变化区间=[140, 220]",
            "中点估算=240",
            "中点估算=420",
            "不确定性",
            r"week-before\.csv",
            r"week-after\.csv",
        ):
            self.assertIn(fragment, markdown)

    def test_pub_output_03_quick_uses_shared_sources_and_deduplicated_action_chain(self) -> None:
        tiny = _entrant_payload()
        multi_island = {
            "periods": tiny["periods"]
            + _entrant_payload(platform="淘宝", category="音箱", prefix="X")["periods"]
        }

        for label, payload in (("tiny", tiny), ("multi_island", multi_island)):
            with self.subTest(label=label):
                result = analyze_payload(payload, mode="quick")
                markdown = render_markdown(result)

                self.assertIn("## 来源索引", markdown)
                self.assertRegex(markdown, r"S1：.*范围=全网.*分母=4")
                self.assertRegex(markdown, r"来源=S\d+(?:/S\d+)*")
                self.assertIn("有效排名行=4 / 输入行=4", markdown)
                self.assertIn("置信度：", markdown)
                self.assertIn("停止条件=", markdown)
                self.assertNotIn("&quot;before&quot;", markdown)
                self.assertNotIn("&quot;file&quot;", markdown)
                for source_file in {period["source_file"] for period in payload["periods"]}:
                    source_label = f"文件={source_file.replace('.', r'\.')}；"
                    self.assertEqual(markdown.count(source_label), 1, source_file)

        first_hypothesis = analyze_payload(tiny, mode="quick")["opportunities"][0]["opportunity_hypothesis"]
        tiny_markdown = render_markdown(analyze_payload(tiny, mode="quick"))
        self.assertEqual(tiny_markdown.count(first_hypothesis), 1)
        self.assertEqual(len(re.findall(r"基于 O1（置信度：.*?；来源=S\d+(?:/S\d+)*）", tiny_markdown)), 3)


if __name__ == "__main__":
    unittest.main()
