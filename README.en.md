# ecommerce-skills

[简体中文](README.md) | English

An AI Skills repository for e-commerce sellers and operations teams. The initial release contains one validated Skill. Future Skills will be added only when they are ready, without creating empty placeholder directories.

> **License: SGSkills Internal Use License 1.0 · Source Available — Not Open Source**

## Current Skill

### sgs-mece | Structured Problem Decomposition Advisor for E-commerce Operations

Use this Skill for ambiguous operational problems whose boundaries are unclear or that span multiple areas such as traffic, conversion, product selection, content, customers, profitability, selling points, and workflows. It clarifies the problem, separates facts from assumptions, and establishes a validation sequence. It does not replace specialist Skills for advertising, product selection, review analysis, or other focused domains.

Best suited for:

- Multiple metrics changing at the same time with no clear starting point;
- Problems spanning several operational areas;
- Descriptions too ambiguous to turn directly into action;
- Designing reversible validation steps with limited data.

Not suited for:

- A clearly defined single-domain problem when a corresponding specialist Skill exists;
- Simple polishing, rewriting, or general-purpose questions;
- Tasks unrelated to e-commerce operations.

## Build, Install, and Invoke

Run the build script first:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\build.ps1
```

### Codex

Extract `dist/sgs-mece-1.4.0.zip`, then place the included `sgs-mece` directory in the user-level `~/.agents/skills/` directory or the project-level `.agents/skills/` directory.

- Explicit invocation: `$sgs-mece`
- You can also describe an ambiguous, cross-functional e-commerce operations problem and let Codex decide whether to invoke the Skill from its description.

### Kimi Code

Place the same `sgs-mece` directory in `~/.config/agents/skills/`.

- Explicit invocation: `/skill:sgs-mece`
- Kimi Code can read the same `SKILL.md` and `references/` directory.

The initial release has passed a structural compatibility check for Kimi Code. A real-case run in an environment with Kimi Code installed is still required before public release.

## Repository Structure

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

`tools/build.ps1` scans only Skill directories that actually exist. It creates both individual Skill packages and a complete suite package without generating placeholders for future Skills.

## Validation

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\validate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\validator\test_validate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\build\test_build.ps1
```

The evaluation fixtures are stored in `tests/sgs-mece/cases.json`. They cover invocation, non-invocation, conflicting data, irreversible decisions, missing data, and deferral to specialist Skills.

## License

The source code in this repository is publicly available, but this is not an open-source project as defined by the OSI. Individuals and businesses may use it free of charge for their own e-commerce operations and may modify it internally. Without written permission, you may not redistribute, resell, white-label, package it as a product or service, or reproduce it in a paid course. See [LICENSE](./LICENSE) for the complete terms.

---

作者： [诗光聊AI电商](微信公众号/视频号/抖音号) · [Github](https://github.com/sgskills) · [DOUYIN](https://v.douyin.com/O8hIsRzfjqQ/)

Built by  [@xstevenzhang](https://x.com/xstevenzhang)
