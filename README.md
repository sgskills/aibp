# AIBP

简体中文 | [English](README.en.md)

[![Stable Release](https://img.shields.io/github/v/release/sgskills/aibp?label=stable)](https://github.com/sgskills/aibp/releases/latest)
[![Validate and build](https://github.com/sgskills/aibp/actions/workflows/validate.yml/badge.svg)](https://github.com/sgskills/aibp/actions/workflows/validate.yml)
[![License](https://img.shields.io/badge/license-Source%20Available-orange.svg)](LICENSE)

**AIBP = AI Business Partner**。这是一个面向经营者、业务团队与 Skill/Agent 作者的 AI 商业伙伴能力仓库：把商业资料、复杂研究、经营问题、推广报表和 Skill 工程任务转化为有证据、有边界、可验证的结果。

当前源码候选版本为 `3.1.0`，稳定安装包以正式 Release 为准。`3.1.0` 提供十项专业功能 Skill，并正式加入可安装的 `sg-aibp` 总路由入口；仓库因此包含十项专业能力和一个路由 Skill。全部 Skill 都使用 30 天惰性检查更新：只提醒源码新版，不自动下载或更新。

> **License: SGSkills Internal Use License 1.0 · Source Available — Not Open Source**

## 三条逻辑分轨

分轨只用于理解、README、合同和路由标签。所有 Skill 始终平铺在 `skills/<slug>`，不会建立 `skills/core`、`skills/ecommerce` 或 `skills/tooling` 分类目录。`ecommerce` 同时覆盖中国市场与跨境市场，不等于“只做跨境”。

| 分轨 | 面向谁 | 典型场景 | 得到什么 |
| --- | --- | --- | --- |
| `core` | 经营者、决策者与研究人员 | 跨行业选择方向、配置资源，或核验复杂问题 | 有证据的战略选择，或来源可审计的研究报告/任务包 |
| `ecommerce` | 电商经营与投放团队 | 拆清跨模块经营问题，或审计天猫推广报表 | 可验证的问题树、数据审计、诊断和行动优先级 |
| `tooling` | Skill/Agent 作者与维护者 | 明确要诊断、测试、优化或打包 Skill/Agent | 证据化体检、待确认计划和真实回归结果 |

普通广告、商品、内容或经营“优化”不属于 `tooling`；只有目标本身是 Skill/Agent 时才使用 `sg-skill-optimizer`。

## AIBP 总路由

不知道该选哪项能力、目标横跨多个 Skill，或需要判断先后顺序时，使用 `$sg-aibp`。总路由只选择首选 Skill、说明依据和开始所需的最小输入，不替代专业 Skill 完成业务分析。

示例：`使用 $sg-aibp 判断我当前应该调用哪个 AIBP Skill，并告诉我开始所需的最小输入。`

## 按场景选择

| 真实场景 | 推荐 Skill | 结果 |
| --- | --- | --- |
| “我不知道这个任务该用哪项 AIBP 能力。” | `sg-aibp` | 首选 Skill、选择理由、最小输入和必要顺序 |
| “几个业务方向只能选一个，未来一年资源怎么配？” | `sg-ceo-vision` | CEO视角的方向选择、资源取舍与年度路径 |
| “请查清这个复杂问题，比较多方来源、反证和冲突后给结论。” | `sg-research` | 带就近引用、不确定性和来源清单的研究报告；离线时给可执行任务包 |
| “带我系统进入一个陌生技术圈，讲清来路和圈内语言。” | `sg-blackcat` | 可继续深挖的认知地图、关键坐标与圈内语境 |
| “店铺流量、转化和库存都异常，但不知道先查哪里。” | `sg-mece` | 电商经营结构化拆解与第一优先级验证 |
| “分析这些商品评价，找需求、场景、人群和隐藏机会。” | `sg-review` | 五模块评价分析、证据边界和可验证行动 |
| “从产品图提取稳定外观特征，为后续生图锁定身份。” | `sg-shiwu` | 产品视觉指纹、身份锚点和防漂移约束 |
| “分析连续四周的天猫商品榜单变化。” | `sg-toplist` | 可追溯榜单变化、机会假设与验证动作 |
| “根据商品事实优化天猫商品标题。” | `sg-title` | 真实、合规、可复核的推荐标题 |
| “这份天猫推广 CSV 表头混乱，ROI 和盈亏能不能算？” | `sg-tmads-report` | 先审表、再诊断的可追溯报告 |
| “这个 Skill 触发不稳，想先体检再改并跑回归。” | `sg-skill-optimizer` | 证据、确认计划、修改记录与回归状态 |

## 能力矩阵

| 中文名称 | slug | 分轨 | 一句话结果 | 仓库精确路径 |
| --- | --- | --- | --- | --- |
| AIBP 总路由 | `sg-aibp` | `core`（入口） | 在十项专业能力之间选择首选 Skill 和必要顺序 | `skills/sg-aibp` |
| CEO视角 | `sg-ceo-vision` | `core` | 把商业资料转化为方向、资源与 12 个月路径 | `skills/sg-ceo-vision` |
| 深度研究 | `sg-research` | `core` | 把复杂问题转化为证据可审计的报告或可执行研究任务包 | `skills/sg-research` |
| 黑猫 | `sg-blackcat` | `core` | 把陌生主题转化为可继续深挖的认知地图 | `skills/sg-blackcat` |
| 电商经营结构化拆解 | `sg-mece` | `ecommerce` | 把模糊跨模块问题拆成可验证原因与行动 | `skills/sg-mece` |
| 电商评价分析 | `sg-review` | `ecommerce` | 把电商评价转成五模块报告、机会和行动 | `skills/sg-review` |
| 识物｜产品特征提取专家 | `sg-shiwu` | `ecommerce` | 把产品图转成视觉指纹、身份锚点和防漂移约束 | `skills/sg-shiwu` |
| 竞品排名分析师 | `sg-toplist` | `ecommerce` | 把天猫商品榜单转成可追溯变化与机会假设 | `skills/sg-toplist` |
| 电商标题优化师 | `sg-title` | `ecommerce` | 为国内货架电商生成或优化真实合规标题 | `skills/sg-title` |
| 天猫推广诊断 | `sg-tmads-report` | `ecommerce` | 把天猫推广报表转化为审计、诊断与优先级 | `skills/sg-tmads-report` |
| SG Skill 优化师 | `sg-skill-optimizer` | `tooling` | 对既有 Skill 做证据驱动优化与回归验证 | `skills/sg-skill-optimizer` |

十项专业能力及总路由的在线详情路径：

- `https://github.com/sgskills/aibp/tree/main/skills/sg-aibp`
- `https://github.com/sgskills/aibp/tree/main/skills/sg-blackcat`
- `https://github.com/sgskills/aibp/tree/main/skills/sg-ceo-vision`
- `https://github.com/sgskills/aibp/tree/main/skills/sg-mece`
- `https://github.com/sgskills/aibp/tree/main/skills/sg-research`
- `https://github.com/sgskills/aibp/tree/main/skills/sg-review`
- `https://github.com/sgskills/aibp/tree/main/skills/sg-shiwu`
- `https://github.com/sgskills/aibp/tree/main/skills/sg-tmads-report`
- `https://github.com/sgskills/aibp/tree/main/skills/sg-skill-optimizer`
- `https://github.com/sgskills/aibp/tree/main/skills/sg-title`
- `https://github.com/sgskills/aibp/tree/main/skills/sg-toplist`

正式版本与安装包下载页：[最新稳定版](https://github.com/sgskills/aibp/releases/latest)。

## 构建与安装

### 直接下载安装包

`v3.1.0` 正式发布后，以下固定链接下载对应安装包；发布前请使用源码构建，已发布稳定版以 [Releases](https://github.com/sgskills/aibp/releases) 为准。所有 `3.1.0` 候选包均包含 30 天惰性检查更新功能，旧版本继续保留供回退。

- [AIBP 总路由](https://github.com/sgskills/aibp/releases/download/v3.1.0/sg-aibp-3.1.0.zip)
- [黑猫](https://github.com/sgskills/aibp/releases/download/v3.1.0/sg-blackcat-3.1.0.zip)
- [CEO视角](https://github.com/sgskills/aibp/releases/download/v3.1.0/sg-ceo-vision-3.1.0.zip)
- [深度研究](https://github.com/sgskills/aibp/releases/download/v3.1.0/sg-research-3.1.0.zip)
- [电商评价分析](https://github.com/sgskills/aibp/releases/download/v3.1.0/sg-review-3.1.0.zip)
- [识物｜产品特征提取专家](https://github.com/sgskills/aibp/releases/download/v3.1.0/sg-shiwu-3.1.0.zip)
- [电商经营结构化拆解](https://github.com/sgskills/aibp/releases/download/v3.1.0/sg-mece-3.1.0.zip)
- [竞品排名分析师](https://github.com/sgskills/aibp/releases/download/v3.1.0/sg-toplist-3.1.0.zip)
- [电商标题优化师](https://github.com/sgskills/aibp/releases/download/v3.1.0/sg-title-3.1.0.zip)
- [天猫推广诊断](https://github.com/sgskills/aibp/releases/download/v3.1.0/sg-tmads-report-3.1.0.zip)
- [SG Skill 优化师](https://github.com/sgskills/aibp/releases/download/v3.1.0/sg-skill-optimizer-3.1.0.zip)
- [AIBP 十项专业能力 + 总路由完整套装](https://github.com/sgskills/aibp/releases/download/v3.1.0/aibp-3.1.0.zip)
- [SHA256 校验清单](https://github.com/sgskills/aibp/releases/download/v3.1.0/SHA256SUMS.txt)

解压单包后，把其中的 `sg-*` 文件夹放入 Agent Runtime 已配置的 Skills 目录。仓库与安装包采用平台中立的 Agent Skill 结构；Codex、WorkBuddy 或其他 Runtime 仍需分别实机验证，不能据此宣称完美适配或生产兼容。

### 从源码构建

在仓库根目录构建：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\build.ps1
```

构建产物：

- `dist/sg-aibp-3.1.0.zip`
- `dist/sg-blackcat-3.1.0.zip`
- `dist/sg-ceo-vision-3.1.0.zip`
- `dist/sg-mece-3.1.0.zip`
- `dist/sg-research-3.1.0.zip`
- `dist/sg-review-3.1.0.zip`
- `dist/sg-shiwu-3.1.0.zip`
- `dist/sg-skill-optimizer-3.1.0.zip`
- `dist/sg-title-3.1.0.zip`
- `dist/sg-tmads-report-3.1.0.zip`
- `dist/sg-toplist-3.1.0.zip`
- `dist/aibp-3.1.0.zip`
- `dist/SHA256SUMS.txt`

### 30 天检查更新

实际使用 Skill 时，首次检查一次，之后每 30×24 小时最多尝试一次；同一安装版本的所有 Skill 共用检查记录。只在 GitHub 官方仓库的源码版本高于本地时，在当前结果末尾提醒，不自动下载或更新。

Windows 使用 PowerShell；macOS/Linux 使用 `sh` 和 `curl`。断网、超时、非法响应或缓存不可写时，主任务正常继续；检查失败也会等待下一个 30 天周期。用户要求禁止联网、零写入或当前 Agent 没有执行工具时跳过检查。宿主仍须实际遵循 `SKILL.md` 的检查入口，兼容性不等同于已验证所有 Agent Runtime。

提醒指向源码版本，不表示已经发布同版本安装包。行为、缓存与验证契约见 [检查更新说明](docs/update-check.md)。

## 仓库结构

```text
aibp/
├── skills/
│   ├── README.md
│   ├── sg-aibp/
│   ├── sg-blackcat/
│   ├── sg-ceo-vision/
│   ├── sg-mece/
│   ├── sg-research/
│   ├── sg-review/
│   ├── sg-shiwu/
│   ├── sg-skill-optimizer/
│   ├── sg-title/
│   ├── sg-tmads-report/
│   └── sg-toplist/
├── docs/superpowers/
├── tests/
├── tools/
├── LICENSE
└── VERSION
```

未来继续增加 Skill 时也保持平铺，并更新总路由、分轨导航与能力矩阵。新增或调整 Skill、升级仓库版本后，在正常构建前统一准备检查文件：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\sync-update-check.ps1
```

该命令自动发现 `skills/*/SKILL.md`，无需维护名称清单。提交前运行全部验证，再构建。缺少检查脚本、版本文件、受管入口或生成副本不一致时，验证和构建直接失败，不会代替维护者补齐。

## 验证

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\validate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\validator\test_validate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\build\test_build.ps1
python -B -m unittest discover -s .\tests\update-check -p "test_*.py"
```

optimizer 保留 21 个 `unittest` 与 6 个可执行 Golden cases；tmads 的字段、隐私、scope 与原子写入回归位于 `tests/sg-tmads-report/`。

全部提交前检查以 [AGENTS.md](AGENTS.md) 为准。检查更新 CI 分别在 Windows、macOS 和 Linux 执行；通过结果以对应提交的实际运行记录为准。

## 迁移与回退

- `v1.4.0` tag 与完整 Git 历史保留。
- dirty v2.0 迁移状态的本地 checkpoint 为 `cfcad564de627172e23c0e2d26b7d4e80d620510`。
- `sgs-mece` 自 v2.0 起迁移为 `sg-mece`，不提供旧名兼容壳。
- 独立开发来源继续保留在仓库外；本仓库是唯一发布真源，来源变更通过清单与哈希审计后选择性迁入，不做自动双向覆盖。

## 使用许可

本仓库属于 Source Available，并非严格意义上的开源项目。许可范围内可用于自身经营，以及组织内部的 Skill/Agent 建设、测试与维护；公开再分发、转售、白标、复刻到付费课程或作为面向第三方的收费服务仍需书面授权。完整条款见 [LICENSE](./LICENSE)。本次发布不代表律师复核已经完成；开展商业授权或依赖本许可证采取法律行动前仍建议由执业律师复核。

---
作者： [诗光聊AI电商](微信公众号/视频号/抖音号) · [Github](https://github.com/sgskills) · [DOUYIN](https://v.douyin.com/O8hIsRzfjqQ/)

敬请关注作者公众号「诗光聊AI电商」

作者中文Skill集合网址：https://sgskills.com

Built by  [@xstevenzhang](https://x.com/xstevenzhang)
