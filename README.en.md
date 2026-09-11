# AIBP

[简体中文](README.md) | English

[![Stable Release](https://img.shields.io/github/v/release/sgskills/aibp?label=stable)](https://github.com/sgskills/aibp/releases/latest)
[![Validate and build](https://github.com/sgskills/aibp/actions/workflows/validate.yml/badge.svg)](https://github.com/sgskills/aibp/actions/workflows/validate.yml)
[![License](https://img.shields.io/badge/license-Source%20Available-orange.svg)](LICENSE)

**AIBP means AI Business Partner.** This repository turns business materials, complex research questions, operating problems, advertising reports, and Skill/Agent engineering tasks into evidence-backed, bounded, verifiable outcomes for operators, business teams, researchers, and Skill authors.

The current stable version is `3.1.0`, with official installation packages published in the [GitHub Release](https://github.com/sgskills/aibp/releases/tag/v3.1.0). Version `3.1.0` provides ten specialist Skills plus the installable `sg-aibp` umbrella router. Every Skill includes a reminder-only 30-day lazy update check; it never downloads or installs an update.

> **License: SGSkills Internal Use License 1.0 · Source Available — Not Open Source**

## Three logical tracks

Tracks are labels used by the README, contracts, and future routing. Every Skill remains physically flat at `skills/<slug>`; there are no `skills/core`, `skills/ecommerce`, or `skills/tooling` installation layers. The `ecommerce` track covers both domestic and cross-border markets.

| Track | Audience | Typical scenario | Outcome |
| --- | --- | --- | --- |
| `core` | Operators, decision-makers, and researchers | Choose a direction, allocate resources, or verify a complex question across industries | Evidence-backed strategic choices or source-auditable research reports/task packs |
| `ecommerce` | Ecommerce operations and advertising teams | Structure a cross-functional operating problem or audit a Tmall advertising report | Testable issue trees, data audits, diagnoses, and action priorities |
| `tooling` | Skill/Agent authors and maintainers | Explicitly diagnose, test, optimize, or package a Skill/Agent | Evidence-based assessment, confirmed plan, and real regression results |

Ordinary optimization of ads, products, content, or operations is not a `tooling` request. `sg-skill-optimizer` applies only when the target itself is a Skill or Agent.

## AIBP umbrella router

Use `$sg-aibp` when the user does not know which capability to choose, the request spans multiple Skills, or sequencing matters. The router selects one primary Skill, explains why, and asks only for the minimum missing input; it does not replace specialist work.

Example: `Use $sg-aibp to decide which AIBP Skill fits my task and tell me the minimum input needed to begin.`

## Choose by scenario

| Real scenario | Skill | Outcome |
| --- | --- | --- |
| “I do not know which AIBP capability fits this task.” | `sg-aibp` | A primary Skill, rationale, minimum input, and any necessary sequence |
| “We can fund only one direction. How should we allocate the next year?” | `sg-ceo-vision` | CEO-level direction, resource trade-offs, and a conditional annual path |
| “Investigate this complex question and compare independent sources, counterevidence, and conflicts.” | `sg-research` | A research report with nearby citations and uncertainty, or an executable task pack when offline |
| “Help me enter an unfamiliar technology field and understand its history and insider language.” | `sg-blackcat` | A navigable knowledge map, key coordinates, and field context |
| “Traffic, conversion, and inventory all changed; where do we investigate first?” | `sg-mece` | Structured ecommerce diagnosis and the first evidence-backed test |
| “Analyze these product reviews for needs, scenarios, audiences, and hidden opportunities.” | `sg-review` | A five-module review analysis with evidence boundaries and testable actions |
| “Extract stable product identity features from these images.” | `sg-shiwu` | A visual fingerprint, identity anchor, and anti-drift constraints |
| “Analyze four weeks of Tmall product rankings.” | `sg-toplist` | Traceable ranking changes, opportunity hypotheses, and validation actions |
| “Optimize this Tmall product title from verified product facts.” | `sg-title` | A truthful, compliant, reviewable product title |
| “This Tmall advertising CSV is messy. Can ROI and contribution profit be trusted?” | `sg-tmads-report` | Audit-first, traceable advertising diagnosis |
| “This Skill triggers unreliably. Assess it, propose changes, and run regression.” | `sg-skill-optimizer` | Evidence, confirmation checkpoint, change log, and regression state |

## Capability matrix

| Display name | Slug | Track | Result | Exact repository path |
| --- | --- | --- | --- | --- |
| AIBP 总路由 | `sg-aibp` | `core` (entry) | Selects a primary Skill and necessary sequence across ten specialist capabilities | `skills/sg-aibp` |
| CEO视角 | `sg-ceo-vision` | `core` | Turns business materials into direction, resources, and a 12-month path | `skills/sg-ceo-vision` |
| 深度研究 | `sg-research` | `core` | Turns complex questions into source-auditable reports or executable research task packs | `skills/sg-research` |
| 黑猫 | `sg-blackcat` | `core` | Turns an unfamiliar topic into a knowledge map that supports deeper exploration | `skills/sg-blackcat` |
| 电商经营结构化拆解 | `sg-mece` | `ecommerce` | Turns ambiguous cross-functional issues into testable causes and actions | `skills/sg-mece` |
| 电商评价分析 | `sg-review` | `ecommerce` | Turns ecommerce reviews into five-module analysis, opportunities, and actions | `skills/sg-review` |
| 识物｜产品特征提取专家 | `sg-shiwu` | `ecommerce` | Turns product images into visual fingerprints, identity anchors, and anti-drift constraints | `skills/sg-shiwu` |
| 竞品排名分析师 | `sg-toplist` | `ecommerce` | Turns Tmall product rankings into traceable changes and opportunity hypotheses | `skills/sg-toplist` |
| 电商标题优化师 | `sg-title` | `ecommerce` | Creates or improves truthful product titles for domestic marketplace platforms | `skills/sg-title` |
| 天猫推广诊断 | `sg-tmads-report` | `ecommerce` | Turns Tmall advertising reports into an audit, diagnosis, and priorities | `skills/sg-tmads-report` |
| SG Skill 优化师 | `sg-skill-optimizer` | `tooling` | Improves existing Skills with evidence and regression validation | `skills/sg-skill-optimizer` |

Live detail paths for the ten specialist Skills and the router:

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

Stable release and package downloads: [Latest stable release](https://github.com/sgskills/aibp/releases/latest).

## Build and install

### Download installation packages

`v3.1.0` is formally released, and these fixed links download its packages directly. See [Releases](https://github.com/sgskills/aibp/releases) for other published versions. Every official `3.1.0` package includes the reminder-only 30-day update check, and earlier releases remain available for rollback.

- [CEO Vision](https://github.com/sgskills/aibp/releases/download/v3.1.0/sg-ceo-vision-3.1.0.zip)
- [AIBP umbrella router](https://github.com/sgskills/aibp/releases/download/v3.1.0/sg-aibp-3.1.0.zip)
- [Black Cat knowledge map](https://github.com/sgskills/aibp/releases/download/v3.1.0/sg-blackcat-3.1.0.zip)
- [Deep Research](https://github.com/sgskills/aibp/releases/download/v3.1.0/sg-research-3.1.0.zip)
- [Ecommerce Review Analysis](https://github.com/sgskills/aibp/releases/download/v3.1.0/sg-review-3.1.0.zip)
- [Product Feature Extractor](https://github.com/sgskills/aibp/releases/download/v3.1.0/sg-shiwu-3.1.0.zip)
- [Structured Ecommerce Diagnosis](https://github.com/sgskills/aibp/releases/download/v3.1.0/sg-mece-3.1.0.zip)
- [Competitor Ranking Analyst](https://github.com/sgskills/aibp/releases/download/v3.1.0/sg-toplist-3.1.0.zip)
- [Ecommerce Title Optimizer](https://github.com/sgskills/aibp/releases/download/v3.1.0/sg-title-3.1.0.zip)
- [Tmall Advertising Diagnosis](https://github.com/sgskills/aibp/releases/download/v3.1.0/sg-tmads-report-3.1.0.zip)
- [SG Skill Optimizer](https://github.com/sgskills/aibp/releases/download/v3.1.0/sg-skill-optimizer-3.1.0.zip)
- [Complete ten-specialist plus router AIBP bundle](https://github.com/sgskills/aibp/releases/download/v3.1.0/aibp-3.1.0.zip)
- [SHA256 checksum manifest](https://github.com/sgskills/aibp/releases/download/v3.1.0/SHA256SUMS.txt)

Extract a single package and place its `sg-*` folder in the Agent runtime's configured Skills directory. The repository uses a platform-neutral Agent Skill structure. Codex, WorkBuddy, and other runtimes still require separate real-world validation; this structure alone is not a claim of perfect or production compatibility.

### Build from source

Build from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\build.ps1
```

Build artifacts:

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

### 30-day update check

A Skill checks on its first actual invocation, then attempts at most once every 30×24 hours. Skills installed at the same version share the check record. Only a newer source version in the official GitHub repository produces a notice at the end of the current response. Nothing is downloaded or updated automatically.

The check uses PowerShell on Windows and `sh` with `curl` on macOS/Linux. Offline operation, timeouts, invalid responses, and unwritable caches do not block the main task; a failed check also waits until the next 30-day period. Skip the check when the user forbids networking or file writes, or the Agent cannot execute commands. The host must still follow the check entry in `SKILL.md`; script compatibility does not establish compatibility with every Agent runtime.

A notice refers to a source version and does not promise matching published installation packages. See [the update-check contract](docs/update-check.md) for behavior, cache locations, and validation.

## Repository layout

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

The physical layout remains flat as the portfolio grows. After adding or changing a Skill, or changing the repository version, prepare the update files before the normal validation and build steps:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\sync-update-check.ps1
```

This command discovers `skills/*/SKILL.md` automatically, without a slug list. Missing scripts, version files, managed entries, or template drift cause validation and builds to fail; neither command silently repairs them.

## Validation

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\validate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\validator\test_validate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\build\test_build.ps1
python -B -m unittest discover -s .\tests\update-check -p "test_*.py"
```

The optimizer retains 21 `unittest` methods and six executable Golden cases. Tmall report regression tests cover field validation, privacy allowlisting, scope, and atomic writes.

See [AGENTS.md](AGENTS.md) for all required pre-commit checks. Update-check CI runs on Windows, macOS, and Linux; only the actual run for a commit establishes its result.

## Migration and rollback

- The `v1.4.0` tag and full Git history remain available.
- The local checkpoint for the dirty v2.0 state is `cfcad564de627172e23c0e2d26b7d4e80d620510`.
- `sgs-mece` moved to `sg-mece` in v2.0; there is no legacy compatibility shell.
- Independent development sources remain outside this repository. This repository is the single release source of truth; source changes enter it through a reviewed manifest/hash import, not automatic two-way overwrite.

## License

This repository is source available, not open source. The license permits use for the user's own operations and internal Skill/Agent development, testing, and maintenance. Public redistribution, resale, white-labelling, paid-course reproduction, or paid third-party services still require written permission. See [LICENSE](./LICENSE). This release does not imply that legal review is complete; counsel review is still recommended before commercial licensing or legal reliance on this license.

---
作者： [诗光聊AI电商](微信公众号/视频号/抖音号) · [Github](https://github.com/sgskills) · [DOUYIN](https://v.douyin.com/O8hIsRzfjqQ/)

Follow the author's WeChat official account: 「诗光聊AI电商」

Chinese Skill collection: https://sgskills.com

Built by  [@xstevenzhang](https://x.com/xstevenzhang)
