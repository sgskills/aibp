# AIBP repository rules

## Purpose

- AIBP is a Source Available repository of platform-neutral Agent Skills.
- All Skills stay flat under `skills/<slug>`; `core`, `ecommerce`, and `tooling` are documentation and routing labels only.
- `ecommerce` covers both domestic and cross-border ecommerce; it is not a physical installation directory.
- `VERSION` is the authoritative repository version.

## Required checks

Run these from the repository root before committing. Keep local temporary output inside `.work/3.0.7/`; configure the test process's temporary directory there before running the commands. Use an available Python 3 runtime without recording machine-specific paths in the repository.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\validate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\validator\test_validate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\build\test_build.ps1
python -B -m unittest discover -s .\skills\sg-skill-optimizer\tests -p "test_*.py"
python -B .\skills\sg-skill-optimizer\scripts\run_eval.py
python -B .\skills\sg-skill-optimizer\scripts\health_check.py .\skills\sg-skill-optimizer
python -B .\skills\sg-skill-optimizer\scripts\audit_description.py .\skills
python -B -m unittest discover -s .\tests\sg-tmads-report -p "test_*.py"
python -B .\skills\sg-tmads-report\tests\run_regression.py
python -B -m unittest discover -s .\tests\update-check -p "test_*.py"
```

Check every native command's exit code; a later successful command must never mask an earlier failure. Set `PYTHONUTF8=1` when running the Tmall report regression on Windows. Update-check behavior must also pass the macOS/Linux CI jobs before syncing the candidate to `main`.

## Packaging

- Do not edit `dist/` artifacts manually; rebuild them with `tools/build.ps1`.
- Validator and build logic must dynamically enumerate valid `skills/*/SKILL.md` directories. Do not hard-code the current Skill count or slugs.
- A release must include one ZIP per dynamically discovered Skill, one AIBP bundle, and `SHA256SUMS.txt`.
- After adding/changing Skills or updating `VERSION`, run `powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\sync-update-check.ps1` to generate the managed update entry and runtime files for every discovered Skill. Validate and build must fail on missing or drifted files, entries, or versions; they must not silently generate or repair them.
- Each single-Skill ZIP must contain `scripts/check-update.ps1`, `scripts/check-update.sh`, and `scripts/update-version.txt` and work without repository-level files. Runtime templates live under `tools/update-check/`; update templates first, then regenerate copies.
- Build checks must prove a newly discovered Skill fails when its update contract is incomplete and joins every expected output when complete. Retain red-to-green evidence and deterministic package checks.

## Update-check contract

- Read only `https://raw.githubusercontent.com/sgskills/aibp/main/VERSION`; accept a standard numeric `X.Y.Z` and notify only when it is newer than the installed version. The notice describes source availability, not a published Release.
- Run only on actual Skill invocation: first attempt immediately, then at most once every 2,592,000 seconds, including failed attempts. Skills at the same installed version share the cache.
- Respect no-network/no-write requests and missing execution capability. Network, cache, and tool failures must not block the main task. Never download, install, execute an update, or interpret a routine reply as update authorization.
- Keep update checks platform-neutral with PowerShell 5.1 or `sh`/`curl`, with a five-second network budget. Behavior tests isolate time and the transport boundary; do not replace date decisions, version comparison, validation, or builds with mocks.

## Boundaries

- Preserve the restrictive Source Available intent in `LICENSE`; do not describe the project as open source.
- Keep the exact author block already present in README files. Do not infer additional authors, sources, courses, or contributors.
- Prefer personified, professional-role wording for human-facing Chinese Skill names when it expresses the capability naturally; `sg-skill-optimizer` is displayed as `SG Skill 优化师`, not `SG Skill 优化器`.
- Do not claim perfect compatibility with Codex, WorkBuddy, or another runtime without real installation validation.
- Never commit secrets, tokens, local absolute paths, caches, temporary output, or `.work/`.

## Current status

- `3.0.7` is the current source and stable Release version. The official download links point to its four standalone packages, bundle and SHA256 manifest. Earlier releases remain available for rollback. `VERSION` remains the source of truth; future publication still requires user authorization.
- `sg-aibp` is planned and must not be linked or advertised as an existing router until implemented.
