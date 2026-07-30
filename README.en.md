# AIBP

[简体中文](README.md) | English

[![Stable Release](https://img.shields.io/github/v/release/sgskills/aibp?label=stable)](https://github.com/sgskills/aibp/releases/latest)
[![Validate and build](https://github.com/sgskills/aibp/actions/workflows/validate.yml/badge.svg)](https://github.com/sgskills/aibp/actions/workflows/validate.yml)
[![License](https://img.shields.io/badge/license-Source%20Available-orange.svg)](LICENSE)

**AIBP means AI Business Partner.** This repository turns business materials, operating problems, advertising reports, and Skill/Agent engineering tasks into evidence-backed, bounded, verifiable outcomes for operators, business teams, and Skill authors.

The current stable version is `3.0.1`. Its code is on `main`, with verifiable installation packages distributed through a GitHub Release. The `sg-aibp` umbrella router remains planned; the current release provides four independent Skills and does not advertise a router that does not yet exist.

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

| Display name | Slug | Track | Result | Exact repository path |
| --- | --- | --- | --- | --- |
| CEO视角 | `sg-ceo-vision` | `core` | Turns business materials into direction, resources, and a 12-month path | `skills/sg-ceo-vision` |
| 电商经营结构化拆解 | `sg-mece` | `commerce` | Turns ambiguous cross-functional issues into testable causes and actions | `skills/sg-mece` |
| 天猫推广诊断 | `sg-tmads-report` | `commerce` | Turns Tmall advertising reports into an audit, diagnosis, and priorities | `skills/sg-tmads-report` |
| SG Skill 优化器 | `sg-skill-optimizer` | `tooling` | Improves existing Skills with evidence and regression validation | `skills/sg-skill-optimizer` |

Live detail paths for the four Skills:

- `https://github.com/sgskills/aibp/tree/main/skills/sg-ceo-vision`
- `https://github.com/sgskills/aibp/tree/main/skills/sg-mece`
- `https://github.com/sgskills/aibp/tree/main/skills/sg-tmads-report`
- `https://github.com/sgskills/aibp/tree/main/skills/sg-skill-optimizer`

Stable release and package downloads: `https://github.com/sgskills/aibp/releases/tag/v3.0.1`

## Build and install

### Download installation packages

- [CEO Vision](https://github.com/sgskills/aibp/releases/download/v3.0.1/sg-ceo-vision-3.0.1.zip)
- [Structured Ecommerce Diagnosis](https://github.com/sgskills/aibp/releases/download/v3.0.1/sg-mece-3.0.1.zip)
- [Tmall Advertising Diagnosis](https://github.com/sgskills/aibp/releases/download/v3.0.1/sg-tmads-report-3.0.1.zip)
- [SG Skill Optimizer](https://github.com/sgskills/aibp/releases/download/v3.0.1/sg-skill-optimizer-3.0.1.zip)
- [Complete AIBP bundle](https://github.com/sgskills/aibp/releases/download/v3.0.1/aibp-3.0.1.zip)
- [SHA256 checksum manifest](https://github.com/sgskills/aibp/releases/download/v3.0.1/SHA256SUMS.txt)

Extract a single package and place its `sg-*` folder in the Agent runtime's configured Skills directory. The repository uses a platform-neutral Agent Skill structure. Codex, WorkBuddy, and other runtimes still require separate real-world validation; this structure alone is not a claim of perfect or production compatibility.

### Build from source

Build from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\build.ps1
```

Build artifacts:

- `dist/sg-ceo-vision-3.0.1.zip`
- `dist/sg-mece-3.0.1.zip`
- `dist/sg-tmads-report-3.0.1.zip`
- `dist/sg-skill-optimizer-3.0.1.zip`
- `dist/aibp-3.0.1.zip`
- `dist/SHA256SUMS.txt`

## Repository layout

```text
aibp/
├── skills/
│   ├── README.md
│   ├── sg-ceo-vision/
│   ├── sg-mece/
│   ├── sg-skill-optimizer/
│   └── sg-tmads-report/
├── docs/superpowers/
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
- The two independent source directories used during migration remain outside this repository; only their imported copies are maintained here.

## License

This repository is source available, not open source. The license permits use for the user's own operations and internal Skill/Agent development, testing, and maintenance. Public redistribution, resale, white-labelling, paid-course reproduction, or paid third-party services still require written permission. See [LICENSE](./LICENSE). This release does not imply that legal review is complete; counsel review is still recommended before commercial licensing or legal reliance on this license.

---
作者： [诗光聊AI电商](微信公众号/视频号/抖音号) · [Github](https://github.com/sgskills) · [DOUYIN](https://v.douyin.com/O8hIsRzfjqQ/)

Built by  [@xstevenzhang](https://x.com/xstevenzhang)
