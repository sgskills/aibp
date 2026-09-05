"""Real-process Windows integration tests for the generated Skill entry contract.

The updater's cross-platform behavior has its own suite. These tests exercise the
PowerShell repository tools in isolated repository-local fixtures; no validators,
generators or build gates are mocked.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import uuid


REPO = Path(__file__).resolve().parents[2]
START = "<!-- AIBP-UPDATE-CHECK:START -->"
END = "<!-- AIBP-UPDATE-CHECK:END -->"
ENTRY = re.compile(re.escape(START) + r"[\s\S]*?" + re.escape(END))
RUNTIME_FILES = ("check-update.ps1", "check-update.sh", "update-version.txt")
ROOT_FILES = (
    "README.md", "README.en.md", "AGENTS.md", "LICENSE", "VERSION",
    "CHANGELOG.md", ".gitignore",
)


def snapshot(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and ".work" not in path.relative_to(root).parts
    }


class EntryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.powershell = shutil.which("powershell.exe")
        if cls.powershell is None:
            raise RuntimeError("Entry integration tests require Windows PowerShell; run the runtime suite on Unix.")
        version = (REPO / "VERSION").read_text(encoding="utf-8").strip()
        if re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version) is None:
            raise RuntimeError("Invalid VERSION cannot select a fixture directory.")
        gate_root = REPO / ".work" / version / "gate-tests"
        gate_root.mkdir(parents=True, exist_ok=True)
        cls.workspace = tempfile.TemporaryDirectory(prefix="entry-", dir=gate_root)
        cls.addClassCleanup(cls.workspace.cleanup)
        cls.run_root = Path(cls.workspace.name)
        cls.base = cls.run_root / "base"
        cls.base.mkdir()
        for filename in ROOT_FILES:
            shutil.copy2(REPO / filename, cls.base / filename)
        for dirname in ("skills", "tools", "tests", ".github"):
            shutil.copytree(
                REPO / dirname, cls.base / dirname,
                ignore=shutil.ignore_patterns("__pycache__", "fixtures-local"),
            )
        cls.version = version
        cls.environment = os.environ.copy()
        # Python launched by PowerShell 7 otherwise passes its incompatible
        # module directories through to the Windows PowerShell 5.1 child.
        for key in list(cls.environment):
            if key.casefold() == "psmodulepath":
                del cls.environment[key]
        temp_root = cls.run_root / "tmp"
        temp_root.mkdir()
        cls.environment.update(TEMP=str(temp_root), TMP=str(temp_root), TMPDIR=str(temp_root))
        # A partially implemented source tree need not have generated copies yet.
        # Only this private baseline fixture is populated by the explicit tool.
        result = cls.invoke(cls.base, "tools/sync-update-check.ps1")
        if result.returncode:
            raise RuntimeError("Fixture sync failed:\n" + result.stdout + result.stderr)

    @classmethod
    def invoke(cls, root: Path, script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [cls.powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
             str(root / script), "-RepoRoot", str(root)],
            cwd=root, env=cls.environment, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=90, check=False,
        )

    def setUp(self) -> None:
        self.root = self.run_root / self.id().rsplit(".", 1)[-1]
        shutil.copytree(self.base, self.root)
        self.skills = sorted(path.parent for path in (self.root / "skills").glob("*/SKILL.md"))
        self.assertTrue(self.skills, "Fixture must discover at least one Skill.")

    def validate(self, code: str | None = None) -> None:
        result = self.invoke(self.root, "tools/validate.ps1")
        output = result.stdout + result.stderr
        if code is None:
            self.assertEqual(result.returncode, 0, output)
            self.assertIn("VALIDATION PASS", output)
        else:
            self.assertNotEqual(result.returncode, 0, output)
            self.assertIn(f"[{code}]", output)

    def sync(self) -> None:
        result = self.invoke(self.root, "tools/sync-update-check.ps1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def assert_skill_contract(self, skill: Path) -> None:
        text = (skill / "SKILL.md").read_text(encoding="utf-8-sig")
        template = (self.root / "tools/update-check/skill-entry.md").read_text(encoding="utf-8-sig").strip()
        self.assertEqual(text.count(START), 1)
        self.assertEqual(text.count(END), 1)
        self.assertEqual(ENTRY.search(text).group(), template)
        for filename in RUNTIME_FILES[:2]:
            self.assertEqual(
                (skill / "scripts" / filename).read_bytes(),
                (self.root / "tools/update-check" / filename).read_bytes(),
            )
        self.assertEqual((skill / "scripts/update-version.txt").read_bytes(), (self.version + "\n").encode())

    def test_every_discovered_skill_has_an_exact_runtime_and_entry_contract(self) -> None:
        for skill in self.skills:
            with self.subTest(skill=skill.name):
                self.assert_skill_contract(skill)
        self.validate()

    def add_probe_skill(self, body: str) -> tuple[Path, str]:
        slug = "sg-entry-probe-" + uuid.uuid4().hex[:8]
        skill = self.root / "skills" / slug
        (skill / "agents").mkdir(parents=True)
        (skill / "scripts").mkdir()
        frontmatter = (
            f"---\nname: {slug}\ndescription: |\n"
            "  Converts a bounded sample into a verifiable result.\n"
            "  Use when testing repository extension; not for unrelated business tasks.\n"
            "license: SGSkills Internal Use License 1.0\n---\n\n# Entry Probe\n\n"
        )
        (skill / "SKILL.md").write_bytes((frontmatter + body).replace("\n", "\r\n").encode())
        (skill / "agents/openai.yaml").write_text(
            f'interface:\n  display_name: "Entry Probe"\n  short_description: "Checks extension"\n'
            f'  default_prompt: "Use ${slug} for the fixture."\n', encoding="utf-8",
        )
        user_script = skill / "scripts/user-tool.txt"
        user_script.write_bytes(b"user-owned script content\r\n")
        cases = self.root / "tests" / slug
        cases.mkdir()
        (cases / "cases.json").write_text('[{"id":"entry-probe"}]', encoding="utf-8")
        for filename in ("README.md", "README.en.md"):
            readme = self.root / filename
            readme.write_text(
                readme.read_text(encoding="utf-8")
                + f"\n- skills/{slug}\n- https://github.com/sgskills/aibp/tree/main/skills/{slug}\n",
                encoding="utf-8",
            )
        return skill, frontmatter

    def test_sync_discovers_a_new_skill_is_idempotent_and_preserves_user_content(self) -> None:
        body = "## Existing instructions\nKeep this user-owned sentence unchanged: alpha + beta.\n"
        skill, frontmatter = self.add_probe_skill(body)
        self.validate("UPDATE_FILE_MISSING")
        self.sync()
        self.assert_skill_contract(skill)
        self.validate()
        actual = (skill / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(actual.startswith(frontmatter))
        self.assertIn(body, actual)
        self.assertEqual((skill / "scripts/user-tool.txt").read_bytes(), b"user-owned script content\r\n")
        first = snapshot(self.root)
        self.sync()
        self.assertEqual(snapshot(self.root), first, "Repeated sync must be byte-idempotent.")

    def test_missing_runtime_files_fail_without_automatic_repair(self) -> None:
        for filename in RUNTIME_FILES:
            with self.subTest(filename=filename):
                path = self.skills[0] / "scripts" / filename
                original = path.read_bytes()
                path.unlink()
                self.validate("UPDATE_FILE_MISSING")
                self.assertFalse(path.exists())
                path.write_bytes(original)

    def test_missing_duplicate_broken_or_drifted_entry_blocks_fail(self) -> None:
        path = self.skills[0] / "SKILL.md"
        original = path.read_text(encoding="utf-8-sig")
        block = ENTRY.search(original).group()
        variants = (
            (original.replace(block, ""), "UPDATE_ENTRY_MISSING"),
            (original + "\n" + block, "UPDATE_ENTRY_INVALID"),
            (original.replace(END, ""), "UPDATE_ENTRY_INVALID"),
            (original.replace(block, END + "\n" + START), "UPDATE_ENTRY_INVALID"),
            (original.replace("scripts/check-update.ps1", "scripts/not-the-updater.ps1"), "UPDATE_ENTRY_DRIFT"),
            (original.replace(block, "```markdown\n" + block + "\n```"), "UPDATE_ENTRY_IN_FENCE"),
            (original.replace(block, "~~~~\n" + block + "\n~~~~"), "UPDATE_ENTRY_IN_FENCE"),
        )
        for content, code in variants:
            with self.subTest(code=code):
                path.write_text(content, encoding="utf-8")
                self.validate(code)
        path.write_text(original, encoding="utf-8")

    def test_runtime_copy_template_and_version_drift_fail(self) -> None:
        for filename in RUNTIME_FILES[:2]:
            with self.subTest(filename=filename):
                path = self.skills[0] / "scripts" / filename
                original = path.read_bytes()
                path.write_bytes(original + b"\n# unauthorized copy drift\n")
                self.validate("UPDATE_TEMPLATE_DRIFT")
                path.write_bytes(original)
        version_path = self.skills[0] / "scripts/update-version.txt"
        for value in (b"0.0.0\n", (self.version + "\r\n").encode(), b"\xef\xbb\xbf" + (self.version + "\n").encode()):
            with self.subTest(value=value):
                version_path.write_bytes(value)
                self.validate("UPDATE_VERSION_MISMATCH")
        version_path.write_bytes((self.version + "\n").encode())
        template = self.root / "tools/update-check/check-update.sh"
        original = template.read_bytes()
        template.write_bytes(original + b"\n# new canonical template not synced\n")
        self.validate("UPDATE_TEMPLATE_DRIFT")
        template.unlink()
        self.validate("UPDATE_TEMPLATE_MISSING")

    def test_entry_accepts_crlf_but_runtime_files_remain_exact_copies(self) -> None:
        path = self.skills[0] / "SKILL.md"
        text = path.read_text(encoding="utf-8-sig")
        path.write_bytes(text.replace("\n", "\r\n").encode())
        self.validate()
        runtime = self.skills[0] / "scripts/check-update.sh"
        runtime.write_bytes(b"\xef\xbb\xbf" + runtime.read_bytes())
        self.validate("UPDATE_TEMPLATE_DRIFT")

    def test_build_failure_preserves_dist_and_never_repairs_sources(self) -> None:
        (self.skills[0] / "scripts/check-update.sh").unlink()
        dist = self.root / "dist"
        dist.mkdir()
        sentinel = dist / "keep-existing-artifact.txt"
        sentinel.write_bytes(b"existing artifact must survive validation failure\n")
        before = snapshot(self.root)
        result = self.invoke(self.root, "tools/build.ps1")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("[UPDATE_FILE_MISSING]", result.stdout + result.stderr)
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(list(dist.iterdir()), [sentinel])

    def test_invalid_entry_template_cannot_pass_via_matching_copies(self) -> None:
        template = self.root / "tools/update-check/skill-entry.md"
        original = template.read_text(encoding="utf-8-sig")
        for content in ("", START + "\nNo executable entry.\n" + END, original + "\n" + START):
            with self.subTest(content=content):
                template.write_text(content, encoding="utf-8")
                self.validate("UPDATE_TEMPLATE_INVALID")

    def test_sync_places_entry_after_fenced_examples_before_real_instructions(self) -> None:
        example = "```markdown\n## Example heading\nOnly an example.\n```\n"
        body = example + "\n## Real instructions\nKeep the business task here.\n"
        skill, frontmatter = self.add_probe_skill(body)
        self.sync()
        text = (skill / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith(frontmatter))
        self.assertIn(example, text)
        self.assertGreater(text.index(START), text.index("\n```\n"))
        self.assertLess(text.index(END), text.index("## Real instructions"))
        self.assert_skill_contract(skill)
        self.validate()

    def test_sync_refuses_an_unclosed_fence_without_partial_writes(self) -> None:
        self.add_probe_skill("```markdown\n## Unclosed example\n")
        before = snapshot(self.root)
        result = self.invoke(self.root, "tools/sync-update-check.ps1")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(snapshot(self.root), before)

    def test_sync_refuses_a_skills_root_junction_without_writing_its_target(self) -> None:
        skills_root = self.root / "skills"
        target = self.run_root / ("junction-target-" + uuid.uuid4().hex)
        skills_root.rename(target)
        command = shutil.which("cmd.exe")
        self.assertIsNotNone(command)
        created = subprocess.run(
            [command, "/d", "/c", "mklink", "/J", str(skills_root), str(target)],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8",
            errors="replace", check=False, timeout=10,
        )
        self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
        try:
            before = snapshot(target)
            result = self.invoke(self.root, "tools/sync-update-check.ps1")
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(snapshot(target), before)
        finally:
            # rmdir removes this owned junction itself, never recursively its target.
            skills_root.rmdir()


if __name__ == "__main__":
    unittest.main()
