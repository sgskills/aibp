from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from report_contract import main as report_contract_main, validate_report  # noqa: E402


def complete_report(*, evidence_ids: str = "R000001、R000002", opportunity_extra: str = "") -> str:
    return f"""# 评价分析报告【合成测试水杯】

**统计周期：** 2026-08-01 ~ 2026-08-31
**评价总量：** 12 条 | **数据来源：** 用户提供

## 一、本期总体评价

### 1.1 评价占比
好评 8/12，差评 4/12。当前样本显示保温是主要正向体验，杯盖渗漏是主要负向问题。

## 二、用户需求分析

### 2.1 核心需求 TOP10
保温体验由 5 条不同评价提及；杯盖密封由 4 条评价提及。覆盖率分母均为 12 条有效评价。

## 三、场景分析

### 3.1 使用场景分布
通勤场景有 4 条明确证据，办公室场景有 3 条；其他评价未明确说明使用场景。

## 四、人群分析

### 4.1 用户人群分布
明确线索显示通勤使用者和办公室使用者关注防漏与便携；年龄、收入和城市层级未知。

## 五、情绪分析

### 5.1 正向情绪 TOP10
正向集中在保温和外观，负向集中在杯盖渗漏；星级与正文冲突另行保留。

## 综合结论与优先行动项

当前应先处理通勤携带时的杯盖密封风险，再测试不同场景对应的杯盖选择说明。以下机会是当前样本中的探索性判断，不能证明市场空白。

### 隐藏商业机会：通勤场景的防漏选择机制

- **机会类型：** 场景人群错配
- **目标人群：** 携带水杯通勤的使用者
- **触发场景：** 水杯放入通勤包并移动时
- **未满足结果：** 不增加操作负担地避免渗漏弄湿随身物品
- **机会假设：** 按携带方式提供杯盖选择提示和可验证的防漏组合，可能降低选择错配
- **证据：** {evidence_ids}：“放包里会漏”“通勤带着不放心”
- **证据强度与置信度：** 多评价信号｜中置信度｜探索性假设
- **为什么不只是整改：** 不只修复杯盖，还增加按场景选择规格和使用指导的价值
- **反证或替代解释：** 个别渗漏也可能来自未旋紧杯盖或偶发批次问题
- **验证动作：** 对两个杯盖说明版本进行小流量场景化测试
- **主指标与分母：** 通勤订单中的渗漏反馈订单占比 / 同期已妥投通勤测试订单数
- **周期与判定：** 连续观察四周，反馈占比下降且退货护栏不恶化时继续
- **停止条件：** 两个周期无改善或退货护栏恶化时停止并回查结构原因
{opportunity_extra}

### P0/P1/P2 优先行动清单

| 优先级 | 行动项 | 依据 | 预期方向 | 执行难度 | 验证方法 |
|---|---|---|---|---|---|
| P0 | 排查杯盖密封 | R000001 | 待验证 | 中 | 同期妥投订单中的反馈占比 |
| P1 | 测试场景化说明 | R000002 | 待验证 | 低 | 四周小流量测试 |
| P2 | 评估杯盖组合 | 当前机会 | 待验证 | 高 | 补充成本与退货数据 |

### 局限性
当前是单商品买后评价样本，没有曝光、未购买者和成本数据，不能推断全体消费者或 ROI。

### 建议补充的数据项
建议补充订单妥投数、退货原因、杯盖批次和同周期竞品评价，以验证发生率和比较结论。
"""


def codes(report: str, mode: str = "complete") -> set[str]:
    return {item.code for item in validate_report(report, mode=mode)}


class V11BusinessReportTests(unittest.TestCase):
    def test_complete_v11_report_passes(self) -> None:
        self.assertEqual([], validate_report(complete_report()))

    def test_all_five_modules_are_required(self) -> None:
        names = (
            "本期总体评价", "用户需求分析", "场景分析", "人群分析", "情绪分析",
        )
        for name in names:
            with self.subTest(name=name):
                report = complete_report().replace(f"## {'一二三四五'[names.index(name)]}、{name}", "## 已删除模块", 1)
                self.assertIn("RPT-003", codes(report))

    def test_module_order_is_v11_order(self) -> None:
        report = complete_report()
        report = report.replace("## 二、用户需求分析", "## 临时模块", 1)
        report = report.replace("## 三、场景分析", "## 二、用户需求分析", 1)
        report = report.replace("## 临时模块", "## 三、场景分析", 1)
        self.assertIn("RPT-005", codes(report))

    def test_headings_inside_fence_do_not_form_report(self) -> None:
        fenced = "```md\n" + complete_report() + "\n```"
        self.assertIn("RPT-001", codes(fenced))
        self.assertIn("RPT-003", codes(fenced))

    def test_hidden_business_opportunity_is_mandatory(self) -> None:
        report = complete_report().replace("### 隐藏商业机会：通勤场景的防漏选择机制", "### 普通改进建议", 1)
        self.assertIn("RPT-006", codes(report))

    def test_no_opportunity_phrase_cannot_replace_opportunity(self) -> None:
        report = complete_report().replace(
            "### 隐藏商业机会：通勤场景的防漏选择机制",
            "### 隐藏商业机会：暂无隐藏商业机会",
            1,
        )
        self.assertIn("RPT-007", codes(report))

    def test_every_opportunity_field_is_required(self) -> None:
        fields = (
            "机会类型", "目标人群", "触发场景", "未满足结果", "机会假设", "证据",
            "证据强度与置信度", "为什么不只是整改", "反证或替代解释", "验证动作",
            "主指标与分母", "周期与判定", "停止条件",
        )
        for field in fields:
            with self.subTest(field=field):
                report = complete_report().replace(f"**{field}：**", "**字段已删除：**", 1)
                self.assertIn("RPT-008", codes(report))

    def test_opportunity_requires_internal_review_evidence(self) -> None:
        report = complete_report(evidence_ids="两条评价")
        self.assertIn("RPT-009", codes(report))

    def test_single_point_opportunity_requires_all_downgrades(self) -> None:
        base = complete_report(
            evidence_ids="R000001",
            opportunity_extra="\n单点信号｜低置信度｜探索性假设",
        )
        self.assertEqual([], validate_report(base))
        for label in ("单点信号", "低置信度", "探索性假设"):
            with self.subTest(label=label):
                self.assertIn("RPT-010", codes(base.replace(label, "已删除")))

    def test_evaluation_asset_opportunity_needs_low_information_basis(self) -> None:
        report = complete_report().replace("场景人群错配", "评价资产", 1)
        self.assertIn("RPT-011", codes(report))
        report = report.replace("评价资产", "评价资产：当前评价低信息，需要改进反馈采集", 1)
        self.assertNotIn("RPT-011", codes(report))

    def test_p0_p1_p2_are_all_required(self) -> None:
        for priority in ("P0", "P1", "P2"):
            with self.subTest(priority=priority):
                report = complete_report().replace(priority, "PX")
                self.assertIn("RPT-012", codes(report))

    def test_missing_data_list_is_required(self) -> None:
        report = complete_report().replace("建议补充的数据项", "后续说明", 1)
        self.assertIn("RPT-013", codes(report))

    def test_unqualified_market_claim_is_rejected(self) -> None:
        report = complete_report(opportunity_extra="\n这是一个市场空白。")
        self.assertIn("RPT-030", codes(report))

    def test_explicitly_limited_market_claim_is_allowed(self) -> None:
        report = complete_report(opportunity_extra="\n当前证据不能证明这是市场空白。")
        self.assertNotIn("RPT-030", codes(report))

    def test_targeted_report_needs_evidence_or_degradation(self) -> None:
        valid = "# 差评分析\n\n数据口径为 12 条有效评价。R000001 提到杯盖渗漏，建议先核对批次并观察同期妥投订单反馈。"
        self.assertEqual([], validate_report(valid, mode="targeted"))
        invalid = "# 差评分析\n\n这批评价有一些值得关注的问题，后续可以继续优化产品体验并完善服务流程。"
        self.assertIn("RPT-021", codes(invalid, mode="targeted"))

    def test_html_headings_are_supported(self) -> None:
        markdown = complete_report()
        lines: list[str] = []
        for line in markdown.splitlines():
            if line.startswith("### "):
                lines.append(f"<h3>{line[4:]}</h3>")
            elif line.startswith("## "):
                lines.append(f"<h2>{line[3:]}</h2>")
            elif line.startswith("# "):
                lines.append(f"<h1>{line[2:]}</h1>")
            else:
                lines.append(f"<p>{line}</p>" if line else "")
        self.assertEqual([], validate_report("<html><body>" + "\n".join(lines) + "</body></html>"))

    def test_cli_returns_zero_for_valid_report_and_nonzero_for_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "report.md"
            path.write_text(complete_report(), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(0, report_contract_main(["--report", str(path)]))
            path.write_text("# 空报告", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(1, report_contract_main(["--report", str(path)]))


class SourceFidelityTests(unittest.TestCase):
    def test_skill_keeps_v11_core_modules_and_mandatory_opportunity(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        positions = [skill.index(name) for name in (
            "本期总体评价", "用户需求分析", "场景分析", "人群分析", "情绪分析",
        )]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("隐藏商业机会：完整报告硬要求", skill)
        self.assertIn("只要存在有效评价，完整报告必须输出至少一条隐藏商业机会", skill)

    def test_incomplete_data_rule_matches_v11(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("【数据不足，以下为推断性分析】", skill)
        self.assertIn("建议补充的数据", skill)
        self.assertIn("基于现有数据尽力分析", skill)

    def test_default_flow_no_longer_requires_legacy_contracts(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for obsolete in ("coding_contract.py", "opportunity_contract.py", "BUSINESS_DRAFT", "VERIFIED_COMPLETE"):
            with self.subTest(obsolete=obsolete):
                self.assertNotIn(obsolete, skill)

    def test_template_contains_v11_subsections_and_opportunity_fields(self) -> None:
        template = (ROOT / "assets" / "report-template.md").read_text(encoding="utf-8")
        required = (
            "1.1 评价占比", "1.2 高频短语", "1.3 评价趋势", "1.4 SKU 分布 TOP10",
            "2.1 核心需求 TOP10", "2.2 关键维度深度解读", "3.1 使用场景分布",
            "3.3 场景化运营与产品优化建议", "4.2 典型使用人群画像",
            "4.4 针对性运营建议", "5.2 正向评价深度解读", "5.4 负向评价深度解读",
            "隐藏商业机会（完整报告必须输出）", "反证或替代解释", "停止条件",
        )
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, template)


if __name__ == "__main__":
    unittest.main()
