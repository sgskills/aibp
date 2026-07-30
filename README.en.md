# ecommerce-skills

[简体中文](README.md) | English

Two focused AI Skills for e-commerce decision-making and commercial planning.

> **License: SGSkills Internal Use License 1.0 · Source Available — Not Open Source**

## Skills

| Skill | What it does | Explicit invocation |
| --- | --- | --- |
| `sg-mece` | Structures ambiguous, cross-functional e-commerce operations problems into evidence-backed actions. | `$sg-mece` |
| `sg-ceo-vision` | Finds commercial opportunities, prioritises them by evidence and value, and turns them into a 12-month path. | `$sg-ceo-vision` |

`sg-ceo-vision` runs independently by default. It does not automatically invoke, recommend, or depend on another Skill. Combine Skills only when the user explicitly asks for that.

## Build and install

Build the packages from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\build.ps1
```

The resulting packages are:

- `dist/sg-mece-2.0.0.zip`
- `dist/sg-ceo-vision-2.0.0.zip`
- `dist/ecommerce-skills-2.0.0.zip`

This iteration is local-only and does not create a v2.0.0 Release. The exact GitHub source paths for the two official Skills are:

- [sg-mece](https://github.com/sgskills/ecommerce-skills/tree/main/skills/sg-mece)
- [sg-ceo-vision](https://github.com/sgskills/ecommerce-skills/tree/main/skills/sg-ceo-vision)

### Codex

Extract an individual package and put its Skill directory in `~/.codex/skills/` (or the equivalent configured Skill directory). Invoke it explicitly with `$sg-mece` or `$sg-ceo-vision`.

### WorkBuddy

Both Skills use a platform-neutral Agent Skills structure, so WorkBuddy does not need platform-specific fields. Install the same extracted Skill directory in WorkBuddy's configured Skills directory and invoke it according to WorkBuddy's own Skill mechanism.

This is structural compatibility only. A real WorkBuddy run is still required before claiming production compatibility.

## Migration from v1.x

`sgs-mece` has moved to `sg-mece` in v2.0.0. There is no legacy compatibility shell: update folder names, explicit calls, and any local references. The existing `v1.4.0` Git tag remains the rollback point for the old name.

## Repository structure

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

## Validation

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\validate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\validator\test_validate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\build\test_build.ps1
```

Evaluation fixtures are in `tests/sg-mece/cases.json` and `tests/sg-ceo-vision/cases.json`.

## License

This repository is source available, not open source. Internal e-commerce use and internal modification are allowed under the license; redistribution, resale, white-labelling, paid-course reproduction, and offering it as a paid third-party service require written permission. See [LICENSE](./LICENSE).

---

作者： [诗光聊AI电商](微信公众号/视频号/抖音号) · [Github](https://github.com/sgskills) · [DOUYIN](https://v.douyin.com/O8hIsRzfjqQ/)

Built by  [@xstevenzhang](https://x.com/xstevenzhang)
