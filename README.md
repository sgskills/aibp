# AIBP

简体中文 | [English](README.en.md)

**AIBP = AI Business Partner**。这是一个面向经营者、业务团队与 Skill/Agent 作者的 AI 商业伙伴能力仓库：把商业资料、经营问题、推广报表和 Skill 工程任务转化为有证据、有边界、可验证的结果。

当前稳定版本为 `3.0.0`，代码位于 `main`，并通过 GitHub Release 提供可校验安装包。`sg-aibp` 总路由仍在规划中；当前只提供四个独立 Skill，不提供尚未实现的总路由调用入口。

> **License: SGSkills Internal Use License 1.0 · Source Available — Not Open Source**

## 三条逻辑分轨

分轨只用于理解、README、合同和路由标签。所有 Skill 始终平铺在 `skills/<slug>`，不会建立 `skills/core`、`skills/commerce` 或 `skills/tooling` 分类目录。

| 分轨 | 面向谁 | 典型场景 | 得到什么 |
| --- | --- | --- | --- |
| `core` | 经营者与决策者 | 跨行业选择方向、配置资源、规划未来 12 个月 | 有证据的战略选择、条件性路径和停止条件 |
| `commerce` | 电商经营与投放团队 | 拆清跨模块经营问题，或审计天猫推广报表 | 可验证的问题树、数据审计、诊断和行动优先级 |
| `tooling` | Skill/Agent 作者与维护者 | 明确要诊断、测试、优化或打包 Skill/Agent | 证据化体检、待确认计划和真实回归结果 |

普通广告、商品、内容或经营“优化”不属于 `tooling`；只有目标本身是 Skill/Agent 时才使用 `sg-skill-optimizer`。

## 按场景选择

| 真实场景 | 推荐 Skill | 结果 |
| --- | --- | --- |
| “几个业务方向只能选一个，未来一年资源怎么配？” | `sg-ceo-vision` | CEO视角的方向选择、资源取舍与年度路径 |
| “店铺流量、转化和库存都异常，但不知道先查哪里。” | `sg-mece` | 电商经营结构化拆解与第一优先级验证 |
| “这份天猫推广 CSV 表头混乱，ROI 和盈亏能不能算？” | `sg-tmads-report` | 先审表、再诊断的可追溯报告 |
| “这个 Skill 触发不稳，想先体检再改并跑回归。” | `sg-skill-optimizer` | 证据、确认计划、修改记录与回归状态 |

## 能力矩阵

| 中文名称 | slug | 分轨 | 一句话结果 | 仓库精确路径 |
| --- | --- | --- | --- | --- |
| CEO视角 | `sg-ceo-vision` | `core` | 把商业资料转化为方向、资源与 12 个月路径 | `skills/sg-ceo-vision` |
| 电商经营结构化拆解 | `sg-mece` | `commerce` | 把模糊跨模块问题拆成可验证原因与行动 | `skills/sg-mece` |
| 天猫推广诊断 | `sg-tmads-report` | `commerce` | 把天猫推广报表转化为审计、诊断与优先级 | `skills/sg-tmads-report` |
| SG Skill 优化器 | `sg-skill-optimizer` | `tooling` | 对既有 Skill 做证据驱动优化与回归验证 | `skills/sg-skill-optimizer` |

四个 Skill 的在线详情路径：

- `https://github.com/sgskills/aibp/tree/main/skills/sg-ceo-vision`
- `https://github.com/sgskills/aibp/tree/main/skills/sg-mece`
- `https://github.com/sgskills/aibp/tree/main/skills/sg-tmads-report`
- `https://github.com/sgskills/aibp/tree/main/skills/sg-skill-optimizer`

正式版本与安装包下载页：`https://github.com/sgskills/aibp/releases/tag/v3.0.0`

## 构建与安装

### 直接下载安装包

- [CEO视角](https://github.com/sgskills/aibp/releases/download/v3.0.0/sg-ceo-vision-3.0.0.zip)
- [电商经营结构化拆解](https://github.com/sgskills/aibp/releases/download/v3.0.0/sg-mece-3.0.0.zip)
- [天猫推广诊断](https://github.com/sgskills/aibp/releases/download/v3.0.0/sg-tmads-report-3.0.0.zip)
- [SG Skill 优化器](https://github.com/sgskills/aibp/releases/download/v3.0.0/sg-skill-optimizer-3.0.0.zip)
- [AIBP 四项完整套装](https://github.com/sgskills/aibp/releases/download/v3.0.0/aibp-3.0.0.zip)
- [SHA256 校验清单](https://github.com/sgskills/aibp/releases/download/v3.0.0/SHA256SUMS.txt)

解压单包后，把其中的 `sg-*` 文件夹放入 Agent Runtime 已配置的 Skills 目录。仓库与安装包采用平台中立的 Agent Skill 结构；Codex、WorkBuddy 或其他 Runtime 仍需分别实机验证，不能据此宣称完美适配或生产兼容。

### 从源码构建

在仓库根目录构建：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\build.ps1
```

构建产物：

- `dist/sg-ceo-vision-3.0.0.zip`
- `dist/sg-mece-3.0.0.zip`
- `dist/sg-tmads-report-3.0.0.zip`
- `dist/sg-skill-optimizer-3.0.0.zip`
- `dist/aibp-3.0.0.zip`
- `dist/SHA256SUMS.txt`

## 仓库结构

```text
aibp/
├── skills/
│   ├── sg-ceo-vision/
│   ├── sg-mece/
│   ├── sg-skill-optimizer/
│   └── sg-tmads-report/
├── tests/
├── tools/
├── LICENSE
└── VERSION
```

未来增加到 10–20 个 Skill 时也继续平铺，只更新分轨导航与能力矩阵。

## 验证

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\validate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\validator\test_validate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\build\test_build.ps1
```

optimizer 保留 21 个 `unittest` 与 6 个可执行 Golden cases；tmads 的字段、隐私、scope 与原子写入回归位于 `tests/sg-tmads-report/`。

## 迁移与回退

- `v1.4.0` tag 与完整 Git 历史保留。
- dirty v2.0 迁移状态的本地 checkpoint 为 `cfcad564de627172e23c0e2d26b7d4e80d620510`。
- `sgs-mece` 自 v2.0 起迁移为 `sg-mece`，不提供旧名兼容壳。
- 迁移时使用的两个独立源目录仍在仓库外保留；本仓库只维护迁入后的副本。

## 使用许可

本仓库属于 Source Available，并非严格意义上的开源项目。许可范围内可用于自身经营，以及组织内部的 Skill/Agent 建设、测试与维护；公开再分发、转售、白标、复刻到付费课程或作为面向第三方的收费服务仍需书面授权。完整条款见 [LICENSE](./LICENSE)。本次发布不代表律师复核已经完成；开展商业授权或依赖本许可证采取法律行动前仍建议由执业律师复核。

---
作者： [诗光聊AI电商](微信公众号/视频号/抖音号) · [Github](https://github.com/sgskills) · [DOUYIN](https://v.douyin.com/O8hIsRzfjqQ/)

Built by  [@xstevenzhang](https://x.com/xstevenzhang)
