# -*- coding: utf-8 -*-
"""sg-tmads-report 一键回归：跑诊断 + 12 条断言自动验收。

用法：
    python tests/run_regression.py           # 脱敏 demo 数据（公开 fixture）
    python tests/run_regression.py --local   # K3 真实数据（本机 fixtures-local）

退出码：0 = 全部通过；1 = 有断言失败；2 = 输入缺失无法运行。
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
TESTS = SKILL_ROOT / "tests"


def load_fixture(local: bool):
    if local:
        norm = TESTS / "fixtures-local" / "normalized-k3.json"
        narr = TESTS / "fixtures-local" / "narrative-k3.json"
        store = "K3店"  # 故意带「店」，验证归一化不会产生「店店铺」
        label = "K3 真实数据（本机）"
    else:
        norm = TESTS / "fixtures" / "normalized-demo.json"
        narr = TESTS / "fixtures" / "narrative-demo.json"
        store = "示例"
        label = "脱敏 demo 数据"
    if not norm.exists() or not narr.exists():
        print(f"SKIP：缺少 {norm} 或 {narr}")
        sys.exit(2)
    return norm, narr, store, label


def compute_expectations(norm_path: Path):
    data = json.loads(norm_path.read_text(encoding="utf-8"))
    assumptions = data.get("assumptions") or {}
    margin = float(assumptions.get("gross_margin_rate") or 0)
    refund = float(assumptions.get("refund_amount_rate") or 0)
    factor = margin * (1 - refund)
    plans = {}  # (dataset_id, plan_id) -> {spend, gmv}
    for ds in data["datasets"]:
        for row in ds["rows"]:
            key = (ds["dataset_id"], str(row["计划ID"]))
            p = plans.setdefault(key, {"spend": 0.0, "gmv": 0.0})
            p["spend"] += float(row.get("花费") or 0)
            p["gmv"] += float(row.get("总成交金额") or 0)
    for p in plans.values():
        p["contribution"] = p["gmv"] * factor - p["spend"]
    total_spend = sum(p["spend"] for p in plans.values())
    worst_key = min(plans, key=lambda k: plans[k]["contribution"])
    zero_sale = {k: p for k, p in plans.items() if p["gmv"] == 0 and p["spend"] >= 1000}
    top_zero = max(zero_sale, key=lambda k: zero_sale[k]["spend"]) if zero_sale else None
    return {
        "plans": plans,
        "plan_count": len(plans),
        "total_spend": total_spend,
        "worst_id": worst_key[1],
        "top_zero_id": top_zero[1] if top_zero else None,
        "has_big_zero": bool(zero_sale),
    }


def run_analyze(norm, narr, store, out_dir: Path):
    cmd = [
        sys.executable, str(SKILL_ROOT / "scripts" / "analyze_report.py"),
        "--input", str(norm),
        "--narrative-input", str(narr),
        "--json-output", str(out_dir / "report.json"),
        "--html-output", str(out_dir / "report.html"),
        "--checkpoint-status", "answered",
        "--store-name", store,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300)


def queue_rows(html: str):
    i = html.find("完整行动队列")
    if i < 0:
        return []
    seg = html[i: html.find("</table>", i)]
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", seg, re.S)
    parsed = []
    for r in rows[1:]:  # 首行是表头
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        if len(cells) >= 5:
            parsed.append(cells)
    return parsed


def main():
    local = "--local" in sys.argv
    norm, narr, store, label = load_fixture(local)
    exp = compute_expectations(norm)
    out_dir = Path(tempfile.mkdtemp(prefix="tmads-regression-"))

    first = run_analyze(norm, narr, store, out_dir)
    if first.returncode != 0:
        print(f"FAIL：诊断脚本运行失败\n{first.stderr[-2000:]}")
        sys.exit(1)
    html_files = [p for p in out_dir.glob("*.html")]
    html = html_files[0].read_text(encoding="utf-8") if html_files else ""
    report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    rows = queue_rows(html)

    second = run_analyze(norm, narr, store, out_dir)  # 同目录第二次，应被拒绝

    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    # 1 文件名规范化 + 无「店店铺」
    fname = html_files[0].name if html_files else ""
    check("文件名规范化《XX店铺天猫推广诊断报告-YYMMDD》",
          re.match(r"^[^\\/]+店铺天猫推广诊断报告-\d{6}\.html$", fname or ""), fname)
    check("店铺名归一化（无「店店铺」）", "店店铺" not in fname, fname)

    # 2 副标题三要素
    check("副标题含 诊断时间/诊断人/数据周期",
          all(k in html for k in ("诊断时间", "诊断人", "数据周期")))

    # 3 页脚可点击 Skill 地址
    check("页脚 Skill 地址可点击跳转",
          'href="https://github.com/sgskills/aibp' in html)

    # 4 三分钟版全店总花费数字
    t = exp["total_spend"]
    candidates = {f"{t:,.2f}", f"{int(round(t)):,}", f"{int(t):,}"}
    check("三分钟版含全店总花费数字", any(c in html for c in candidates),
          f"期望≈¥{t:,.2f}")

    # 5 队列全覆盖
    check("行动队列逐计划全覆盖", len(rows) == exp["plan_count"],
          f"队列 {len(rows)} / 应有 {exp['plan_count']}")

    # 6 队列首行 = 最大亏损计划
    first_plan_cell = rows[0][4] if rows else ""
    check("队列首行=全场最大亏损计划（减亏优先）",
          exp["worst_id"] in first_plan_cell,
          f"期望ID {exp['worst_id']}，实际首行 {first_plan_cell[:40]}")

    # 7 零成交高花费计划被点名
    if exp["has_big_zero"]:
        top5 = " ".join(r[4] for r in rows[:5])
        check("最高花费零成交计划在队列前 5 行", exp["top_zero_id"] in top5,
              f"期望ID {exp['top_zero_id']}")
        check("零成交计划带 P0 梯队标识", "P0 成熟零成交" in html)
    else:
        checks.append(("零成交高花费计划点名（本数据无此类计划）", True, "N/A"))
        checks.append(("P0 梯队标识（本数据无此类计划）", True, "N/A"))

    # 8 亏损行红底标记
    check("亏损行有红底标识（row-loss）", "row-loss" in html)

    # 9 经验沉淀与再建计划守则
    check("经验沉淀章节存在", "经验沉淀" in html)
    check("再建计划注意事项/守则存在", ("再建计划" in html) or ("守则" in html))

    # 10 队列默认排序说明
    check("队列表头标明减亏优先", "减亏优先" in html)

    # 11 拒绝覆盖
    check("同名文件拒绝覆盖（防误删）", second.returncode != 0,
          f"第二次运行退出码 {second.returncode}")

    # 12 actions 全覆盖
    actions = report.get("actions") or []
    check("报告 actions 逐计划全覆盖", len(actions) == exp["plan_count"],
          f"actions {len(actions)} / 应有 {exp['plan_count']}")

    print("=" * 64)
    print(f"sg-tmads-report 回归验收 ｜ 数据：{label} ｜ 计划数：{exp['plan_count']}")
    print("=" * 64)
    failed = 0
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        line = f"[{mark}] {name}"
        if detail and (not ok or "N/A" in detail):
            line += f" ｜ {detail}"
        print(line)
    print("-" * 64)
    print(f"结果：{len(checks) - failed}/{len(checks)} 通过 ｜ 输出目录 {out_dir}")
    if failed:
        print("状态：❌ 有退化，请修复后重跑")
        sys.exit(1)
    print("状态：✅ 全部通过")
    sys.exit(0)


if __name__ == "__main__":
    main()
