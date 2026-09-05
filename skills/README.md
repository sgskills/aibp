# AIBP Skill 目录

本目录始终采用 `skills/<slug>` 平铺结构。`core`、`ecommerce`、`tooling` 只是理解与路由标签，不是磁盘分类目录；`ecommerce` 同时覆盖中国市场与跨境市场。

| 分轨 | Skill | 用途 | 精确路径 |
| --- | --- | --- | --- |
| `core` | CEO视角 | 商业方向、资源取舍与未来 12 个月路径 | [`sg-ceo-vision`](sg-ceo-vision/) |
| `ecommerce` | 电商经营结构化拆解 | 跨模块经营问题拆解与验证优先级 | [`sg-mece`](sg-mece/) |
| `ecommerce` | 天猫推广诊断 | 推广报表审计、诊断与行动优先级 | [`sg-tmads-report`](sg-tmads-report/) |
| `tooling` | SG Skill 优化师 | 既有 Skill 的证据化优化与回归 | [`sg-skill-optimizer`](sg-skill-optimizer/) |

当前源码版本为 `3.0.7`，已发布的稳定安装包为 `3.0.6`，可从 [AIBP Latest Release](https://github.com/sgskills/aibp/releases/latest) 下载。获取 `3.0.7` 的 30 天检查更新功能，请从当前源码构建。仓库与安装包采用平台中立的 Agent Skill 结构；具体 Runtime 兼容性仍以实机验证为准。

现有及新增 Skill 统一使用[检查更新契约](../docs/update-check.md)：实际调用时惰性检查，仅提醒源码新版，不自动更新。维护者把新 Skill 放入 `skills/<slug>` 后，运行 `tools/sync-update-check.ps1` 自动生成入口和运行文件，再正常验证与构建；遗漏配置或模板漂移会直接失败。
