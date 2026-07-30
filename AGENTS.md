# AIBP repository rules

## Purpose

- AIBP is a Source Available repository of platform-neutral Agent Skills.
- All Skills stay flat under `skills/<slug>`; `core`, `commerce`, and `tooling` are documentation and routing labels only.
- `VERSION` is the authoritative repository version.

## Required checks

Run these from the repository root before committing:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\validate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\validator\test_validate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\build\test_build.ps1
python -B -m unittest discover -s .\skills\sg-skill-optimizer\tests -p "test_*.py"
python -B .\skills\sg-skill-optimizer\scripts\run_eval.py
python -B .\skills\sg-skill-optimizer\scripts\health_check.py .\skills\sg-skill-optimizer
python -B .\skills\sg-skill-optimizer\scripts\audit_description.py .\skills
python -B -m unittest discover -s .\tests\sg-tmads-report -p "test_*.py"
```

## Packaging

- Do not edit `dist/` artifacts manually; rebuild them with `tools/build.ps1`.
- Validator and build logic must dynamically enumerate valid `skills/*/SKILL.md` directories. Do not hard-code the current Skill count or slugs.
- A release must include one ZIP per dynamically discovered Skill, one AIBP bundle, and `SHA256SUMS.txt`.

## Boundaries

- Preserve the restrictive Source Available intent in `LICENSE`; do not describe the project as open source.
- Keep the exact author block already present in README files. Do not infer additional authors, sources, courses, or contributors.
- Do not claim perfect compatibility with Codex, WorkBuddy, or another runtime without real installation validation.
- Never commit secrets, tokens, local absolute paths, caches, temporary output, or `.work/`.

## Current status

- `3.0.1` is the current stable release; `VERSION` remains the source of truth for later versions.
- `sg-aibp` is planned and must not be linked or advertised as an existing router until implemented.
