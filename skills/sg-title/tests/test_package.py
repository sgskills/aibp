from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


class PackageContractTests(unittest.TestCase):
    def test_frontmatter_has_only_required_three_keys(self) -> None:
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        frontmatter = text.split("---", 2)[1]
        keys = [
            match.group(1)
            for line in frontmatter.splitlines()
            if (match := re.match(r"^([a-z_]+):", line))
        ]
        self.assertEqual(["name", "description", "license"], keys)
        self.assertIn("国内货架电商", frontmatter)
        self.assertIn("不用于公众号", frontmatter)

    def test_openai_yaml_quotes_all_strings_and_mentions_skill(self) -> None:
        lines = (SKILL_ROOT / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        ).splitlines()
        string_lines = [line.strip() for line in lines if ": " in line]
        self.assertTrue(all(re.search(r': "[^"].*"$', line) for line in string_lines))
        text = "\n".join(lines)
        self.assertIn('display_name: "电商标题优化师"', text)
        self.assertIn("$sg-title", text)
        short = re.search(r'short_description: "(.*)"', text).group(1)
        self.assertGreaterEqual(len(short), 25)
        self.assertLessEqual(len(short), 64)

    def test_root_contains_only_allowed_entries(self) -> None:
        allowed = {"SKILL.md", "agents", "references", "scripts", "tests"}
        self.assertEqual(allowed, {path.name for path in SKILL_ROOT.iterdir()})

    def test_production_profiles_are_only_four_supported_platforms(self) -> None:
        data = json.loads(
            (SKILL_ROOT / "references" / "platform-profiles.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            {"tmall", "jd", "pinduoduo", "douyin"}, set(data["platforms"])
        )
        tmall = data["platforms"]["tmall"]
        self.assertEqual("advisory", tmall["length"]["enforcement"])
        self.assertEqual("hard", tmall["operating_defaults"]["length"]["enforcement"])
        self.assertEqual(
            "owner_operating_default",
            tmall["operating_defaults"]["length"]["source"],
        )
        self.assertTrue(
            all(
                profile["status"] == "requires_live_confirmation"
                for profile in data["platforms"].values()
            )
        )


if __name__ == "__main__":
    unittest.main()
