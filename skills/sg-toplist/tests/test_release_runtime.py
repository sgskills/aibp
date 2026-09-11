"""通过真实子进程故障验证启动器，不替换业务计算对象。"""
from __future__ import annotations
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_analysis import run_checked

class RuntimeTests(unittest.TestCase):
    def test_missing_executable_fails_with_no_advice(self) -> None:
        result, code = run_checked([str(ROOT / "missing-interpreter")], timeout=1)
        self.assertNotEqual(code, 0)
        self.assertEqual(result["runtime_error"]["code"], "START_FAILED")
        self.assertTrue(all(x is None for x in result["actions"].values()))

    def test_nonzero_exit_is_not_accepted_as_successful_json(self) -> None:
        result, code = run_checked([sys.executable, "-B", "-c", "import sys;sys.stdout.write('{}');sys.stderr.write('failure');sys.exit(7)"], timeout=5)
        self.assertNotEqual(code, 0)
        self.assertEqual(result["runtime_error"]["exit_code"], 7)

    def test_explicit_business_rejection_preserves_structured_audit(self) -> None:
        payload = {
            "status": "rejected",
            "audit": {"status": "blocking", "issues": [{"code": "BAD_INPUT"}]},
            "facts": [],
            "opportunities": [],
            "actions": {"product_selection": None, "product_development": None, "main_promotion": None},
        }
        code = "import json,sys;print(json.dumps(" + repr(payload) + "));sys.exit(2)"
        result, exit_code = run_checked(
            [sys.executable, "-B", "-c", code],
            timeout=5,
            result_exit_codes=frozenset({2}),
        )
        self.assertEqual(exit_code, 2)
        self.assertEqual(result["audit"]["issues"][0]["code"], "BAD_INPUT")
        self.assertNotIn("runtime_error", result)

    def test_business_exit_code_cannot_mask_success_status(self) -> None:
        payload = {
            "status": "analyzed",
            "audit": {},
            "facts": [],
            "opportunities": [],
            "actions": {},
        }
        code = "import json,sys;print(json.dumps(" + repr(payload) + "));sys.exit(2)"
        result, exit_code = run_checked(
            [sys.executable, "-B", "-c", code],
            timeout=5,
            result_exit_codes=frozenset({2}),
        )
        self.assertEqual(exit_code, 3)
        self.assertEqual(result["runtime_error"]["code"], "EXIT_STATUS_MISMATCH")

    def test_invalid_json_and_missing_contract_are_rejected(self) -> None:
        for output in ("broken-json", "{}", "[]", '{"status":"analyzed"}'):
            result, code = run_checked([sys.executable, "-B", "-c", f"import sys;sys.stdout.write({output!r})"], timeout=5)
            with self.subTest(output=output):
                self.assertNotEqual(code, 0)
                self.assertEqual(result["facts"], [])

    def test_timeout_is_explicit_and_does_not_refresh_results(self) -> None:
        result, code = run_checked([sys.executable, "-B", "-c", "import time;time.sleep(3)"], timeout=0.05)
        self.assertNotEqual(code, 0)
        self.assertEqual(result["runtime_error"]["code"], "TIMEOUT")

if __name__ == "__main__":
    unittest.main()
