# AIBP

[简体中文](README.md) | English

**AIBP means AI Business Partner.** This repository turns business materials, operating problems, advertising reports, and Skill/Agent engineering tasks into evidence-backed, bounded, verifiable outcomes for operators, business teams, and Skill authors.

This is a local review candidate, version `3.0.0-rc.1`. No remote release, tag, or Release has been created. The `sg-aibp` umbrella router is planned only; this iteration does not create an invocation or installation link for it.

> **License: SGSkills Internal Use License 1.0 · Source Available — Not Open Source**

## Three logical tracks

Tracks are labels used by the README, contracts, and future routing. Every Skill remains physically flat at `skills/<slug>`; there are no `skills/core`, `skills/commerce`, or `skills/tooling` installation layers.

| Track | Audience | Typical scenario | Outcome |
| --- | --- | --- | --- |
| `core` | Operators and decision-makers | Choose a direction, allocate resources, and plan the next 12 months across industries | Evidence-backed strategic choices, conditional paths, and stop conditions |
| `commerce` | Ecommerce operations and advertising teams | Structure a cross-functional operating problem or audit a Tmall advertising report | Testable issue trees, data audits, diagnoses, and action priorities |
| `tooling` | Skill/Agent authors and maintainers | Explicitly diagnose, test, optimize, or package a Skill/Agent | Evidence-based assessment, confirmed plan, and real regression results |

Ordinary optimization of ads, products, content, or operations is not a `tooling` request. `sg-skill-optimizer` applies only when the target itself is a Skill or Agent.

## Choose by scenario

| Real scenario | Skill | Outcome |
| --- | --- | --- |
| “We can fund only one direction. How should we allocate the next year?” | `sg-ceo-vision` | CEO-level direction, resource trade-offs, and a conditional annual path |
| “Traffic, conversion, and inventory all changed; where do we investigate first?” | `sg-mece` | Structured ecommerce diagnosis and the first evidence-backed test |
| “This Tmall advertising CSV is messy. Can ROI and contribution profit be trusted?” | `sg-tmads-report` | Audit-first, traceable advertising diagnosis |
| “This Skill triggers unreliably. Assess it, propose changes, and run regression.” | `sg-skill-optimizer` | Evidence, confirmation checkpoint, change log, and regression state |

## Capability matrix

| Display name | Slug | Track | Result | Exact local path |
| --- | --- | --- | --- | --- |
| CEO视角 | `sg-ceo-vision` | `core` | Turns business materials into direction, resources, and a 12-month path | `skills/sg-ceo-vision` |
| 电商经营结构化拆解 | `sg-mece` | `commerce` | Turns ambiguous cross-functional issues into testable causes and actions | `skills/sg-mece` |
| 天猫推广诊断 | `sg-tmads-report` | `commerce` | Turns Tmall advertising reports into an audit, diagnosis, and priorities | `skills/sg-tmads-report` |
| SG Skill 优化器 | `sg-skill-optimizer` | `tooling` | Improves existing Skills with evidence and regression validation | `skills/sg-skill-optimizer` |

Planned exact detail paths after the future repository is enabled:

- `https://github.com/sgskills/aibp/tree/main/skills/sg-ceo-vision`
- `https://github.com/sgskills/aibp/tree/main/skills/sg-mece`
- `https://github.com/sgskills/aibp/tree/main/skills/sg-tmads-report`
- `https://github.com/sgskills/aibp/tree/main/skills/sg-skill-optimizer`

These are target paths, not a claim that the remote pages already exist. The local origin remains unchanged, and this iteration does not rename or publish anything remotely.

## Build and install

Build from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\build.ps1
```

Candidate artifacts:

- `dist/sg-ceo-vision-3.0.0-rc.1.zip`
- `dist/sg-mece-3.0.0-rc.1.zip`
- `dist/sg-tmads-report-3.0.0-rc.1.zip`
- `dist/sg-skill-optimizer-3.0.0-rc.1.zip`
- `dist/aibp-3.0.0-rc.1.zip`
- `dist/SHA256SUMS.txt`

Extract a single package and place its `sg-*` folder in the Agent runtime's configured Skills directory. The repository uses a platform-neutral Agent Skill structure. Codex, WorkBuddy, and other runtimes still require separate real-world validation; this structure alone is not a claim of perfect or production compatibility.

## Repository layout

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

The physical layout remains flat even when the portfolio grows to 10–20 Skills.

## Validation

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\validate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\validator\test_validate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\build\test_build.ps1
```

The optimizer retains 21 `unittest` methods and six executable Golden cases. Tmall report regression tests cover field validation, privacy allowlisting, scope, and atomic writes.

## Migration and rollback

- The `v1.4.0` tag and full Git history remain available.
- The local checkpoint for the dirty v2.0 state is `cfcad564de627172e23c0e2d26b7d4e80d620510`.
- `sgs-mece` moved to `sg-mece` in v2.0; there is no legacy compatibility shell.
- The independent sources at `E:\+Skills\sg-tmads-report` and `E:\+Skills\sg-skill-optimizer` are neither modified nor deleted by this repository.

## License

This repository is source available, not open source. The license permits use for the user's own operations and internal Skill/Agent development, testing, and maintenance. Public redistribution, resale, white-labelling, paid-course reproduction, or paid third-party services still require written permission. See [LICENSE](./LICENSE); counsel review remains necessary before any public release.

---
作者： [诗光聊AI电商](微信公众号/视频号/抖音号) · [Github](https://github.com/sgskills) · [DOUYIN](https://v.douyin.com/O8hIsRzfjqQ/)

Built by  [@xstevenzhang](https://x.com/xstevenzhang)
