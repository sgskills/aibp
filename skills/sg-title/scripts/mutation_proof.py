#!/usr/bin/env python3
"""在指定工作目录复制 Skill、逐项破坏六个安全控制，并证明回归由绿转红。"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


MUTATIONS = {
    "missing_provenance": ("scripts/title_guard.py", 'for field in ("title_core_terms", "keyword_sources"):', "for field in ():"),
    "high_risk_fallback": ("scripts/title_guard.py", 'risk_hits = {term: kind for term, kind in RISK_SIGNALS.items() if term in title}', "risk_hits = {}"),
    "unicode_whitespace": ("scripts/title_guard.py", "whitespace_count = sum(char.isspace() for char in title)", 'whitespace_count = title.count(" ")'),
    "expired_rule": ("scripts/platform_guard.py", "review_due = today >= review", "review_due = False"),
    "cross_profile": ("scripts/title_guard.py", 'if str(actual or "") != str(expected):\n            return False', "if False:\n            return False"),
    "mixed_route": ("scripts/title_guard.py", 'title_task = any(term in text for term in ("商品标题", "电商标题", "$sg-title"))', "title_task = False"),
}


def run_suite(root: Path) -> dict:
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"],
        cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    combined = completed.stdout + completed.stderr
    summaries = [line for line in combined.splitlines()
                 if line.startswith("Ran ") or line == "OK" or line.startswith("FAILED ")]
    return {"returncode": completed.returncode, "summary": summaries[-3:]}


def copy_skill(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--skill-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    run_dir = args.work_dir.resolve() / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)

    baseline = run_suite(args.skill_root)
    results = {}
    for name, (relative, old, new) in MUTATIONS.items():
        mutant = run_dir / name
        copy_skill(args.skill_root, mutant)
        target = mutant / relative
        content = target.read_text(encoding="utf-8")
        count = content.count(old)
        if count != 1:
            results[name] = {"mutation_applied": False, "matches": count, "returncode": None}
            continue
        target.write_text(content.replace(old, new, 1), encoding="utf-8")
        outcome = run_suite(mutant)
        outcome["mutation_applied"] = True
        outcome["detected"] = outcome["returncode"] != 0
        results[name] = outcome

    restored = run_suite(args.skill_root)
    passed = (baseline["returncode"] == 0 and restored["returncode"] == 0
              and all(item.get("mutation_applied") and item.get("detected") for item in results.values()))
    proof = {"suite": "sg-title-six-control-mutation-proof", "work_dir": str(run_dir),
             "baseline_green": baseline, "mutants": results, "restored_green": restored,
             "proof_passed": passed}
    print(json.dumps(proof, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
