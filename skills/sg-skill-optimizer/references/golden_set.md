# sg-skill-optimizer 可执行 Golden Set

本文件说明评测契约；真实输入和机器断言位于 `tests/fixtures/`，执行器为 `scripts/run_eval.py`。

## 状态定义

| 状态 | 含义 | 能否宣称已验证 |
|---|---|---|
| `MISSING` | 没有 Golden Set | 否 |
| `SPEC_ONLY` | 只有文字案例 | 否 |
| `EXECUTABLE` | fixture 与 runner 已存在，本轮未运行 | 否 |
| `VERIFIED` | 本轮经授权执行，且全部机器断言通过 | 是 |

## 运行

```powershell
python scripts/run_eval.py
python scripts/run_eval.py --format json
python -m unittest discover -s tests -v
```

任何案例失败时，runner 返回非零退出码。禁止只看 `golden_set.md` 文件存在就给评测能力满分。验证目标 Skill 自己的 runner 前，必须先检查代码并取得确认；`health_check.py` 只有同时收到 `--verify-eval --allow-target-code` 才执行目标代码。

## 案例契约

每个 `tests/fixtures/<id>/case.json` 包含：

- `id`：稳定案例编号；
- `target`：相对案例目录的目标 Skill；
- `skillsRoot`：仅环境级触发审计使用，可省略；
- `expected`：机器断言。

支持的断言：

- `blocked`；
- `minScore` / `maxScore`；
- `blockerContains`；
- `evaluationState`；
- `crossSkillStatus`；
- `dimensionMax`。

## 当前覆盖

1. `healthy-minimal-skill`：健康但未工具化的只读 Skill，不应出现红线，且应保持在 70–80 分，避免把“无红线”误报成“完整成熟”；
2. `unconfirmed-overwrite`：无确认覆盖原文件，必须 BLOCKED；
3. `prose-only-golden`：只有文字案例，必须为 `SPEC_ONLY`；
4. `bad-frontmatter`：非法 frontmatter，必须 BLOCKED；
5. `missing-output-contract`：无模板和格式约束，输出稳定性必须低分；
6. `real-trigger-overlap`：两个高度相似 description，必须报告候选冲突。

## 新增回归

### 更新检查能力场景（与脚本 Golden Set 分开）

`tests/update-check-capability.json` 是 7 个模型工作流场景：AIBP 缺契约、私有离线、其他仓库来源未知、自动更新越界、新 Skill 假绿灯、无执行却声称通过、完整证据健康对照。

复验时先隐藏 `expected`，仅向执行者提供请求、材料及本 Skill，再保存真实输出，对照适用性、规则代码、授权边界和接入计划。它不是 `run_eval.py` 的脚本 fixture，不得将文件存在或静态词语命中算作行为通过；未作场景复验记 MANUAL/未运行。运行时的 30 天判断与跨平台功能仍以目标本身真实回归为准。

发现漏报或误报时：

1. 先新增能复现问题的 fixture 与断言；
2. 运行 runner，确认新案例失败；
3. 修改实现；
4. 重跑全部案例；
5. 把修复原因记录到 `SKILL.patch.md`。

不要修改期望值去迎合错误实现；只有需求本身改变时才更新断言。
