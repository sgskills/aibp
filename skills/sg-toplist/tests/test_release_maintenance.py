"""30天惰性检查必须处理到期、变更和坏状态，不发生默认写入。"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from maintenance_check import maintenance_status, skill_fingerprint

class MaintenanceTests(unittest.TestCase):
    def test_first_use_is_due_without_creating_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            result = maintenance_status(ROOT, state)
            self.assertTrue(result["check_due"])
            self.assertFalse(state.exists())
            self.assertEqual(result["remote_update_status"], "unverified_not_configured")

    def test_exact_30_day_boundary_is_due(self) -> None:
        now = datetime(2026, 9, 7, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            for age, due in ((29, False), (30, True), (45, True)):
                state.write_text(json.dumps({"schema_version": 1, "last_checked_at": (now - timedelta(days=age)).isoformat(), "skill_fingerprint": skill_fingerprint(ROOT), "check_scope": "local_golden_and_syntax"}), encoding="utf-8")
                original = state.read_bytes()
                with self.subTest(age=age):
                    self.assertEqual(maintenance_status(ROOT, state, now=now)["check_due"], due)
                    self.assertEqual(state.read_bytes(), original)

    def test_changed_rules_invalidate_even_a_recent_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            state.write_text(json.dumps({"schema_version": 1, "last_checked_at": datetime.now(timezone.utc).isoformat(), "skill_fingerprint": "0" * 64, "check_scope": "local_golden_and_syntax"}), encoding="utf-8")
            result = maintenance_status(ROOT, state)
            self.assertTrue(result["check_due"])
            self.assertEqual(result["reason"], "skill_changed")

    def test_corrupt_naive_future_or_wrong_schema_state_never_suppresses_check(self) -> None:
        now = datetime(2026, 9, 7, tzinfo=timezone.utc)
        bad_values = ["not json", "[]", json.dumps({"schema_version": 99}), json.dumps({"schema_version": 1, "last_checked_at": "2026-09-07", "skill_fingerprint": skill_fingerprint(ROOT)}), json.dumps({"schema_version": 1, "last_checked_at": (now + timedelta(days=1)).isoformat(), "skill_fingerprint": skill_fingerprint(ROOT), "check_scope": "local_golden_and_syntax"})]
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            for value in bad_values:
                state.write_text(value, encoding="utf-8")
                with self.subTest(value=value):
                    self.assertTrue(maintenance_status(ROOT, state, now=now)["check_due"])
                    self.assertEqual(state.read_text(encoding="utf-8"), value)

if __name__ == "__main__":
    unittest.main()
