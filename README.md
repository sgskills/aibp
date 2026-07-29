# ecommerce-skills

简体中文 | [English](README.en.md)

面向电商卖家与运营团队的 AI Skills 仓库。首版只发布一个经过验证的 Skill；未来的 Skill 完成后再逐个加入，不提前创建空目录。

> **License: SGSkills Internal Use License 1.0 · Source Available — Not Open Source**

## 当前 Skill

### sgs-mece｜电商运营问题结构化拆解顾问

用于边界不清、跨流量/转化/选品/内容/用户/利润/卖点/工作流多个模块的模糊运营问题。它负责把问题定义清楚、区分事实与假设、形成验证顺序，不替代推广投放、选品、评价分析等专业 Skill。

适合：

- 多个指标同时变化，不知道先查哪里；
- 问题横跨多个运营模块；
- 现有描述过于模糊，无法直接形成行动；
- 需要在有限数据下设计可逆验证。

不适合：

- 已经定义清楚且存在对应专业 Skill 的单一领域问题；
- 单纯润色、内容改写或泛化问答；
- 与电商经营无关的任务。

## 安装与调用

先运行构建脚本：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\build.ps1
```

### Codex

将 `dist/sgs-mece-1.4.0.zip` 解压，把其中的 `sgs-mece` 目录放入用户级 `~/.agents/skills/`，或项目级 `.agents/skills/`。

- 显式调用：`$sgs-mece`
- 也可直接描述边界不清、跨模块的电商运营问题，让 Codex 按 description 判断是否触发。

### Kimi Code

将同一个 `sgs-mece` 目录放入 `~/.config/agents/skills/`。

- 显式调用：`/skill:sgs-mece`
- Kimi Code 可读取相同的 `SKILL.md` 与 `references/`。

首版仅完成 Kimi Code 的结构兼容检查；正式发布前仍需在装有 Kimi Code 的环境运行真实案例。

## 仓库结构

```text
ecommerce-skills/
├── skills/
│   └── sgs-mece/
│       ├── SKILL.md
│       ├── agents/openai.yaml
│       └── references/
├── tests/
├── tools/
├── .github/workflows/
├── LICENSE
├── VERSION
└── README.md / README.en.md
```

`tools/build.ps1` 会扫描真实存在的 Skill 目录，生成单 Skill 安装包和整套安装包；不会为未来 Skill 创建空壳。

## 验证

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\validate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\validator\test_validate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\build\test_build.ps1
```

评测基准位于 `tests/sgs-mece/cases.json`，覆盖触发、反触发、数据冲突、不可逆决策、缺失数据和专业 Skill 让位边界。

## 使用许可

本仓库源码公开，但不是 OSI 定义的开源项目。个人与企业可免费用于自身电商经营，并可内部修改；未经书面授权，不得公开再分发、转售、白标、打包为产品或服务，也不得复制进付费课程。完整条款以 [LICENSE](./LICENSE) 为准。

---

作者： [诗光聊AI电商](微信公众号/视频号/抖音号) · [Github](https://github.com/sgskills) · [DOUYIN](https://v.douyin.com/O8hIsRzfjqQ/)

Built by  [@xstevenzhang](https://x.com/xstevenzhang)
