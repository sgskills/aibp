# ecommerce-skills

简体中文 | [English](README.en.md)

面向电商经营与商业决策的两个 AI Skill。

> **License: SGSkills Internal Use License 1.0 · Source Available — Not Open Source**

## Skills

| Skill | 作用 | 显式调用 |
| --- | --- | --- |
| `sg-mece` | 把边界不清、跨模块的电商运营问题，拆成可验证的结构与行动。 | `$sg-mece` |
| `sg-ceo-vision` | 从经营资料中识别商业机会，按价值与证据排序，并形成 12 个月路径。 | `$sg-ceo-vision` |

`sg-ceo-vision` 默认独立运行；不会自动调用、推荐或依赖其他 Skill。只有用户明确提出时，才与其他 Skill 结合。

## 构建与安装

在仓库根目录构建安装包：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\build.ps1
```

构建产物：

- `dist/sg-mece-2.0.0.zip`
- `dist/sg-ceo-vision-2.0.0.zip`
- `dist/ecommerce-skills-2.0.0.zip`

本轮仅做本地构建，尚未创建 v2.0.0 Release；GitHub 中两个正式 Skill 的准确来源路径为：

- [sg-mece](https://github.com/sgskills/ecommerce-skills/tree/main/skills/sg-mece)
- [sg-ceo-vision](https://github.com/sgskills/ecommerce-skills/tree/main/skills/sg-ceo-vision)

### Codex

解压单个安装包，将其中的 Skill 文件夹放入 `~/.codex/skills/`（或你的已配置 Skills 目录），再用 `$sg-mece` 或 `$sg-ceo-vision` 显式调用。

### WorkBuddy

两个 Skill 都使用平台中立的 Agent Skills 结构，WorkBuddy 不需要专属字段。把同一个解压后的 Skill 文件夹安装到 WorkBuddy 已配置的 Skills 目录，并按 WorkBuddy 自己的 Skill 调用方式使用即可。

这里仅完成了结构兼容；在宣称生产可用前，仍需在真实 WorkBuddy 环境完成实机验证。

## 从 v1.x 迁移

`sgs-mece` 已在 v2.0.0 迁移为 `sg-mece`。本次不保留旧名兼容壳：请同步更新本地文件夹名、显式调用和引用。已有 `v1.4.0` Git tag 保留，仍可作为旧名称版本的回退点。

## 仓库结构

```text
ecommerce-skills/
├── skills/
│   ├── sg-mece/
│   └── sg-ceo-vision/
├── tests/
│   ├── sg-mece/cases.json
│   └── sg-ceo-vision/cases.json
├── tools/
├── LICENSE
└── VERSION
```

## 验证

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\validate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\validator\test_validate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\build\test_build.ps1
```

评测样例位于 `tests/sg-mece/cases.json` 与 `tests/sg-ceo-vision/cases.json`。

## 使用许可

本仓库属于 Source Available，并非开源项目。许可范围内可用于自身电商经营并做内部修改；公开再分发、转售、白标、复刻到付费课程，或作为面向第三方的收费服务，均需书面授权。完整条款见 [LICENSE](./LICENSE)。

---

作者： [诗光聊AI电商](微信公众号/视频号/抖音号) · [Github](https://github.com/sgskills) · [DOUYIN](https://v.douyin.com/O8hIsRzfjqQ/)

Built by  [@xstevenzhang](https://x.com/xstevenzhang)
