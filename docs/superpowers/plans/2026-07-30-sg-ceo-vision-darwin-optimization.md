# sg-ceo-vision Darwin Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise `sg-ceo-vision` from the 81.2 single-scenario baseline to a verified score of at least 90 without changing its business scope or automatic-Skill boundary.

**Architecture:** Keep `SKILL.md` as the only runtime behavior file. Add contract assertions to the repository validator and use the existing evaluator JSON plus three real prompt comparisons to prove the new gates change output quality.

**Tech Stack:** Markdown Agent Skill, PowerShell validator and tests, JSON evaluation fixtures.

---

### Task 1: Add a failing contract test for the new decision safeguards

**Files:**
- Modify: `tests/validator/test_validate.ps1`
- Modify: `tools/validate.ps1`

- [x] **Step 1: Extend the validator self-test fixture with a copy of `sg-ceo-vision/SKILL.md` that omits the required safeguard marker.**

Require the invalid fixture to produce `CEO_VISION_CONTRACT`, then restore the source fixture and require zero issues. Print `CEO_VISION_CONTRACT_RED_GREEN PASS`.

- [x] **Step 2: Run the test before implementation.**

Run: `& .\tests\validator\test_validate.ps1`

Expected: FAIL because `CEO_VISION_CONTRACT_RED_GREEN PASS` is absent.

- [x] **Step 3: Add the minimal validator rule.**

Require `SKILL.md` to contain these exact control surfaces:

```text
## 🔴 STOP / CHECKPOINT：重大不可逆决策
## 失败恢复表
结论｜证据状态｜来源位置｜会改变结论的条件
## 禁止误判清单
```

Do not weaken existing migration, metadata, reference, evaluation, or legacy-prefix rules.

- [x] **Step 4: Re-run the validator test.**

Run: `& .\tests\validator\test_validate.ps1`

Expected: the existing legacy red-to-green evidence and the new contract red-to-green evidence both pass.

### Task 2: Add behavior coverage for the three failure-sensitive scenarios

**Files:**
- Modify: `tests/sg-ceo-vision/cases.json`

- [x] **Step 1: Add three named expected-output contracts without removing any existing case.**

Add coverage for: unreadable or incomplete materials, conflicting metrics, and an irreversible action missing loss limits. Each expected list must require a stop/fallback outcome rather than a fabricated business conclusion.

- [x] **Step 2: Validate the fixture is valid JSON and retains all original categories.**

Run:

```powershell
$utf8 = [System.Text.Encoding]::UTF8
ConvertFrom-Json -InputObject ([System.IO.File]::ReadAllText((Resolve-Path .\tests\sg-ceo-vision\cases.json), $utf8)) | Measure-Object
& .\tools\validate.ps1 -RepoRoot .
```

Expected: valid JSON, at least nine CEO Vision cases, `VALIDATION PASS`.

### Task 3: Implement the minimal Skill upgrade

**Files:**
- Modify: `skills/sg-ceo-vision/SKILL.md`

- [x] **Step 1: Add the required STOP / CHECKPOINT section immediately before the existing irreversible-decision guidance.**

The section must state that, before maximum acceptable loss, cash ceiling, and exit cost are known, the Skill must not recommend scaling spend, stocking up, signing a long contract, clearing inventory, or stopping a primary channel. It may only give a missing-data list and a reversible next action.

- [x] **Step 2: Add one compact failure-recovery table.**

Rows: unreadable materials, conflicting metrics, and priority-changing data missing. Columns: stop, still deliver, recovery condition.

- [x] **Step 3: Replace the loose evidence-ledger instruction with the four-field format and add a compact prohibited-misjudgments list.**

The list must cover payment ROI, high click-through rate, single-table extrapolation, invented benchmarks, and automatic Skill chaining.

- [x] **Step 4: Keep the document below 150% of its 4,419-byte baseline and preserve all existing headings, HTML rules, independent-operation rules, and external-action restrictions.**

### Task 4: Run regression and Darwin outcome evaluation

**Files:**
- Verify: `tools/validate.ps1`
- Verify: `tests/validator/test_validate.ps1`
- Verify: `tests/build/test_build.ps1`
- Verify: `skills/sg-ceo-vision/SKILL.md`

- [x] **Step 1: Run all repository checks.**

Run:

```powershell
& .\tools\validate.ps1 -RepoRoot .
& .\tests\validator\test_validate.ps1
& .\tests\build\test_build.ps1
```

Expected: all commands exit 0; both red-to-green markers are printed.

- [x] **Step 2: Run three with-Skill versus baseline comparisons and obtain two independent blind judgments.**

Scenarios: opportunity scan, insufficient evidence, and irreversible investment. Score dimension 8 from the judged outputs; do not claim a full test if any scenario is omitted.

- [x] **Step 3: Score all nine Darwin dimensions.**

Keep the change only if the weighted total is strictly above 81.2 and at least 90. If it is lower, revert only this round’s `SKILL.md`, test, and validator changes; preserve the pre-existing dual-Skill migration worktree.

## Execution constraints

- Only modify `skills/sg-ceo-vision/SKILL.md`, `tests/sg-ceo-vision/cases.json`, `tests/validator/test_validate.ps1`, `tools/validate.ps1`, and this plan/spec documentation.
- Do not delete tests, add dependencies, alter the CEO Vision business scope, create a compatibility chain, publish externally, or make a Git commit from this dirty worktree.
- Record each completed task in `.work/PROGRESS.md`; record repeated blockers in `.work/BLOCKED.md`.

## Completion conditions

- The optimized Skill scores at least 90/100 across all nine Darwin dimensions, with three real comparison scenarios and two independent judges.
- All three repository commands exit 0, both red-to-green markers are present, existing boundaries remain intact, and no pre-existing migration changes are overwritten.
