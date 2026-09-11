# AIBP Skill 目录

本目录始终采用 `skills/<slug>` 平铺结构。`core`、`ecommerce`、`tooling` 只是理解与路由标签，不是磁盘分类目录；`ecommerce` 同时覆盖中国市场与跨境市场。

| 分轨 | Skill | 用途 | 精确路径 |
| --- | --- | --- | --- |
| `core`（入口） | AIBP 总路由 | 在十项专业能力之间选择首选 Skill 和必要顺序 | [`sg-aibp`](sg-aibp/) |
| `core` | 黑猫 | 陌生主题的来路、同类坐标、圈内语言与认知地图 | [`sg-blackcat`](sg-blackcat/) |
| `core` | CEO视角 | 商业方向、资源取舍与未来 12 个月路径 | [`sg-ceo-vision`](sg-ceo-vision/) |
| `core` | 深度研究 | 复杂问题的多源查证、反证与可审计研究交付 | [`sg-research`](sg-research/) |
| `ecommerce` | 电商经营结构化拆解 | 跨模块经营问题拆解与验证优先级 | [`sg-mece`](sg-mece/) |
| `ecommerce` | 电商评价分析 | 电商评价五模块分析、隐藏商业机会和行动清单 | [`sg-review`](sg-review/) |
| `ecommerce` | 识物｜产品特征提取专家 | 产品图视觉指纹、身份锚点和防漂移约束 | [`sg-shiwu`](sg-shiwu/) |
| `ecommerce` | 竞品排名分析师 | 天猫榜单审计、跨期变化和机会假设 | [`sg-toplist`](sg-toplist/) |
| `ecommerce` | 电商标题优化师 | 国内货架电商商品标题生产与校验 | [`sg-title`](sg-title/) |
| `ecommerce` | 天猫推广诊断 | 推广报表审计、诊断与行动优先级 | [`sg-tmads-report`](sg-tmads-report/) |
| `tooling` | SG Skill 优化师 | 既有 Skill 的证据化优化与回归 | [`sg-skill-optimizer`](sg-skill-optimizer/) |

当前稳定版为 `3.1.0`；正式安装包已发布至 [AIBP v3.1.0 Release](https://github.com/sgskills/aibp/releases/tag/v3.1.0)。仓库包含十项专业功能 Skill 和一个总路由入口，全部包含 30 天惰性检查更新功能。仓库与安装包采用平台中立的 Agent Skill 结构；具体 Runtime 兼容性仍以实机验证为准。

现有及新增 Skill 统一使用[检查更新契约](../docs/update-check.md)：实际调用时惰性检查，仅提醒源码新版，不自动更新。维护者把新 Skill 放入 `skills/<slug>` 后，运行 `tools/sync-update-check.ps1` 自动生成入口和运行文件，再正常验证与构建；遗漏配置或模板漂移会直接失败。

---

敬请关注作者公众号「诗光聊AI电商」

作者中文Skill集合网址：https://sgskills.com
