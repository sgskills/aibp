"""Real runtime subprocess regressions; only the clock and transport are injected.

Runs Windows PowerShell 5.1 on Windows, POSIX sh/curl on Linux and macOS.
Every process gets isolated cache/home/temp paths below .work/3.1.0/runtime-tests.
"""
from __future__ import annotations

import concurrent.futures
import contextlib
import hashlib
import http.server
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest


ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads((Path(__file__).with_name("cases.json")).read_text(encoding="utf-8"))
NOW = CASES["now_seconds"]
INTERVAL = CASES["interval_seconds"]
WORK = ROOT / ".work" / "3.1.0" / "runtime-tests"


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        WORK.mkdir(parents=True, exist_ok=True)
        cls.windows = os.name == "nt" and not os.environ.get("AIBP_TEST_SH")
        cls.program = os.environ.get("AIBP_TEST_SH") or shutil.which("powershell" if cls.windows else "sh")
        if not cls.program:
            raise RuntimeError("Required native runtime not found")
        if not cls.windows and not shutil.which("curl"):
            raise RuntimeError("curl is required by the native Unix runtime")
        print(f"Native platform={platform.system()} runtime={cls.program}", flush=True)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="运行 空格-", dir=WORK)
        self.base = Path(self.directory.name)
        self.package = self.base / "independent Skill 空格" / "scripts"
        self.package.mkdir(parents=True)
        self.cache = self.base / "cache 空格"
        self.cache.mkdir()
        self.version = "3.1.0"
        self.version_file = self.package / "update-version.txt"
        self.version_file.write_text(self.version + "\n", encoding="ascii")
        self.extension = "ps1" if self.windows else "sh"
        self.script = self.package / ("check-update." + self.extension)
        shutil.copyfile(ROOT / "tools" / "update-check" / self.script.name, self.script)
        self.response = self.base / "response.txt"
        self.response.write_text("3.1.1\n", encoding="ascii")
        self.env = os.environ.copy()
        for key in ("HOME", "LOCALAPPDATA", "XDG_CACHE_HOME", "TEMP", "TMP", "TMPDIR"):
            location = self.base / key
            location.mkdir()
            self.env[key] = str(location)
        self.before = self.package_hashes()

    def tearDown(self):
        self.directory.cleanup()

    def package_hashes(self):
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.package.iterdir() if p.is_file()}

    def notice(self, remote="3.1.1", local=None):
        return f"AIBP 源码有新版本 v{remote}（当前 v{local or self.version}）：https://github.com/sgskills/aibp\n"

    def runtime_path(self, path):
        path = Path(path)
        if os.name == "nt" and not self.windows:
            return "/" + path.drive[0].lower() + path.as_posix()[2:]
        return str(path)

    def arguments(self, *, now=NOW, response=True, url=None, cache=True):
        if self.windows:
            command = [self.program, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(self.script)]
            names = ("-NowSeconds", "-CacheRoot", "-ResponseFile", "-TestUrl")
        else:
            command = [self.program, self.runtime_path(self.script)]
            if os.name == "nt":
                command = [self.program, "-c", 'PATH=/usr/bin:/mingw64/bin:$PATH; export PATH; exec sh "$@"', "aibp-tests", self.runtime_path(self.script)]
            names = ("--now-seconds", "--cache-root", "--response-file", "--test-url")
        if now is not None:
            command += [names[0], str(now)]
        if cache:
            command += [names[1], self.runtime_path(self.cache)]
        if response:
            command += [names[2], self.runtime_path(self.response)]
        if url:
            command += [names[3], url]
        return command

    def run_check(self, **kwargs):
        started = time.monotonic()
        process_env = self.env.copy()
        if os.name == "nt" and not self.windows:
            for key in ("HOME", "LOCALAPPDATA", "XDG_CACHE_HOME", "TMPDIR"):
                if key in process_env:
                    process_env[key] = self.runtime_path(process_env[key])
        result = subprocess.run(self.arguments(**kwargs), cwd=self.base, env=process_env,
                                capture_output=True, encoding="utf-8", errors="strict", timeout=12)
        result.elapsed = time.monotonic() - started
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertLess(result.elapsed, 12)
        return result

    def attempt_path(self, local=None, cache=None):
        return (cache or self.cache) / (local or self.version) / "last-attempt.txt"

    def set_previous(self, value):
        path = self.attempt_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(value), encoding="ascii")

    @contextlib.contextmanager
    def server(self, mode="ok", body=None):
        if body is None:
            body = self.response.read_bytes()
        hits = []
        stop = threading.Event()

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(handler):
                hits.append(handler.path)
                try:
                    if mode == "hang-headers":
                        stop.wait(8)
                        return
                    if mode == "error":
                        handler.send_response(503)
                    elif mode == "redirect":
                        handler.send_response(302)
                        handler.send_header("Location", "/must-not-follow")
                    else:
                        handler.send_response(200)
                    if mode not in ("hang-body", "large-stream"):
                        handler.send_header("Content-Length", str(len(body)))
                    handler.end_headers()
                    if mode == "hang-body":
                        handler.wfile.write(b"3.")
                        handler.wfile.flush()
                        stop.wait(8)
                    elif mode == "large-stream":
                        handler.wfile.write(b"4.0.0" + b"x" * 8192)
                    else:
                        handler.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args):
                pass

        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{httpd.server_port}/VERSION", hits
        finally:
            stop.set()
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_shared_version_vectors(self):
        for case in CASES["version_cases"]:
            with self.subTest(case=case["id"]):
                self.cache = self.base / ("vector-" + case["id"])
                self.version_file.write_text(case["local"] + "\n", encoding="ascii")
                self.response.write_bytes(case["response"].encode("utf-8"))
                result = self.run_check()
                expected = self.notice(case["response"].strip(), case["local"]) if case["notice"] else ""
                self.assertEqual(result.stdout, expected)
                self.assertEqual(self.attempt_path(case["local"]).read_text(), str(NOW))

    def test_first_call_and_no_package_mutation(self):
        self.assertEqual(self.run_check().stdout, self.notice())
        self.assertEqual(self.package_hashes(), self.before)
        self.assertEqual(self.attempt_path().read_text(), str(NOW))

    def test_before_interval_has_zero_network_requests(self):
        self.set_previous(NOW - INTERVAL + 1)
        with self.server() as (url, hits):
            self.assertEqual(self.run_check(response=False, url=url).stdout, "")
            self.assertEqual(hits, [])
        self.assertEqual(self.attempt_path().read_text(), str(NOW - INTERVAL + 1))

    def test_exact_interval_sends_one_request(self):
        self.set_previous(NOW - INTERVAL)
        with self.server() as (url, hits):
            self.assertEqual(self.run_check(response=False, url=url).stdout, self.notice())
            self.assertEqual(hits, ["/VERSION"])
        self.assertEqual(self.attempt_path().read_text(), str(NOW))

    def test_corrupt_and_future_cache_repair_without_network(self):
        for value in ("broken", "", "999999999999999999999", str(NOW + 1), "-1", "01", "1\n", "1\0", " 1"):
            with self.subTest(value=value):
                self.set_previous(value)
                with self.server() as (url, hits):
                    self.assertEqual(self.run_check(response=False, url=url).stdout, "")
                    self.assertEqual(hits, [])
                self.assertEqual(self.attempt_path().read_text(), str(NOW))

    def test_http_error_cools_down_and_does_not_remind(self):
        with self.server(mode="error") as (url, hits):
            self.assertEqual(self.run_check(response=False, url=url).stdout, "")
            self.assertEqual(self.run_check(response=False, url=url, now=NOW + 1).stdout, "")
            self.assertEqual(hits, ["/VERSION"])

    def test_network_refused_cools_down(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.assertEqual(self.run_check(response=False, url=f"http://127.0.0.1:{port}/VERSION").stdout, "")
        self.assertEqual(self.run_check(now=NOW + 1).stdout, "")
        self.assertEqual(self.attempt_path().read_text(), str(NOW))

    def test_hanging_headers_has_process_deadline(self):
        with self.server(mode="hang-headers") as (url, hits):
            result = self.run_check(response=False, url=url)
            self.assertEqual(result.stdout, "")
            self.assertEqual(hits, ["/VERSION"])
            self.assertLess(result.elapsed, 10)
        self.assertEqual(self.attempt_path().read_text(), str(NOW))

    def test_hanging_body_has_process_deadline(self):
        with self.server(mode="hang-body") as (url, hits):
            result = self.run_check(response=False, url=url)
            self.assertEqual(result.stdout, "")
            self.assertEqual(hits, ["/VERSION"])
            self.assertLess(result.elapsed, 10)

    def test_redirect_does_not_follow_or_remind(self):
        with self.server(mode="redirect") as (url, hits):
            self.assertEqual(self.run_check(response=False, url=url).stdout, "")
            self.assertEqual(hits, ["/VERSION"])

    def test_oversized_http_response_is_rejected(self):
        for mode in ("ok", "large-stream"):
            self.cache = self.base / ("large-" + mode)
            with self.server(mode=mode, body=b"4.0.0" + b"x" * 8192) as (url, hits):
                self.assertEqual(self.run_check(response=False, url=url).stdout, "")
                self.assertEqual(hits, ["/VERSION"])

    def test_invalid_test_urls_are_rejected_without_cache(self):
        urls = ["https://example.com/VERSION", "http://localhost:8000/VERSION", "http://127.0.0.1.evil:80/VERSION",
                "http://127.0.0.1:65536/VERSION", "http://127.0.0.1:80/x#fragment", "http://127.0.0.1:80/\n"]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.run_check(url=url).stdout, "")
                self.assertFalse(self.attempt_path().exists())

    def test_invalid_local_version_does_not_touch_cache(self):
        self.version_file.write_text("3.0.7; command", encoding="ascii")
        self.assertEqual(self.run_check().stdout, "")
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_invalid_clock_is_silent(self):
        for now in ("-1", "garbage", "9999999999999", "01"):
            self.assertEqual(self.run_check(now=now).stdout, "")
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_native_clock_without_injection(self):
        before = int(time.time())
        self.assertEqual(self.run_check(now=None).stdout, self.notice())
        after = int(time.time())
        recorded = int(self.attempt_path().read_text())
        self.assertGreaterEqual(recorded, before)
        self.assertLessEqual(recorded, after)

    def test_same_version_skills_share_cache(self):
        self.assertEqual(self.run_check().stdout, self.notice())
        original = self.package
        second = self.base / "another Skill" / "scripts"
        shutil.copytree(original, second)
        self.script = second / self.script.name
        self.assertEqual(self.run_check(now=NOW + 1).stdout, "")

    def test_different_install_versions_are_isolated(self):
        self.assertEqual(self.run_check().stdout, self.notice())
        self.version_file.write_text("3.0.7\n", encoding="ascii")
        self.assertEqual(self.run_check().stdout, self.notice(local="3.0.7"))
        self.assertTrue(self.attempt_path("3.0.7").exists())
        self.assertTrue(self.attempt_path("3.1.0").exists())

    def test_concurrent_invocations_make_one_request(self):
        with self.server() as (url, hits):
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                results = list(pool.map(lambda _: self.run_check(response=False, url=url), range(5)))
            self.assertEqual(hits, ["/VERSION"])
            self.assertEqual(sum(r.stdout == self.notice() for r in results), 1)
            self.assertTrue(all(r.stdout in ("", self.notice()) for r in results))

    def test_stale_lock_is_recovered(self):
        lock = self.attempt_path().parent / "attempt.lock"
        lock.parent.mkdir(parents=True)
        if self.windows:
            lock.write_text("abandoned OS lock file", encoding="ascii")
        else:
            lock.mkdir()
            (lock / "owner").write_text(f"99999999 {int(time.time()) - 60}", encoding="ascii")
        self.assertEqual(self.run_check().stdout, self.notice())

    def test_abandoned_recovery_or_unowned_lock_is_recovered(self):
        for recovery in (False, True):
            with self.subTest(recovery=recovery):
                self.cache = self.base / ("unowned-" + str(recovery))
                lock = self.attempt_path().parent / "attempt.lock"
                lock.parent.mkdir(parents=True)
                if self.windows:
                    lock.write_text("abandoned", encoding="ascii")
                else:
                    lock.mkdir()
                    if recovery:
                        guard = lock / "recovery"
                        guard.mkdir()
                        os.utime(guard, (time.time() - 60, time.time() - 60))
                    os.utime(lock, (time.time() - 60, time.time() - 60))
                self.assertEqual(self.run_check().stdout, self.notice())

    def test_blocked_cache_sends_no_request(self):
        # A file cannot be used as a directory on either OS, including privileged CI.
        self.cache = self.base / "not a writable directory"
        self.cache.write_text("preserve", encoding="ascii")
        with self.server() as (url, hits):
            self.assertEqual(self.run_check(response=False, url=url).stdout, "")
            self.assertEqual(hits, [])
        self.assertEqual(self.cache.read_text(), "preserve")

    def test_readonly_attempt_cannot_trigger_network(self):
        self.set_previous(NOW - INTERVAL)
        attempt = self.attempt_path()
        # On Unix an unwritable directory is the relevant boundary for atomic rename;
        # Windows also denies replacement of a read-only destination file.
        target = attempt if self.windows else attempt.parent
        target.chmod(0o444 if self.windows else 0o555)
        try:
            if not self.windows and (os.name == "nt" or os.geteuid() == 0):
                # Root/MSYS can bypass POSIX bits: use an unreplaceable destination directory.
                target.chmod(0o755)
                attempt.unlink()
                attempt.mkdir()
            with self.server() as (url, hits):
                self.assertEqual(self.run_check(response=False, url=url).stdout, "")
                self.assertEqual(hits, [])
        finally:
            target.chmod(0o755 if target.is_dir() else 0o644)

    def test_default_cache_stays_inside_redirected_user_directories(self):
        self.assertEqual(self.run_check(cache=False).stdout, self.notice())
        if self.windows:
            expected = Path(self.env["LOCALAPPDATA"]) / "SGSkills" / "aibp"
        elif platform.system() == "Darwin":
            expected = Path(self.env["HOME"]) / "Library" / "Caches" / "SGSkills" / "aibp"
        else:
            expected = Path(self.env["XDG_CACHE_HOME"]) / "sgskills" / "aibp"
        self.assertEqual(self.attempt_path(cache=expected).read_text(), str(NOW))
        self.assertEqual(self.package_hashes(), self.before)

    def test_unix_home_fallback_or_windows_missing_cache_root(self):
        if self.windows:
            self.env.pop("LOCALAPPDATA", None)
            self.assertEqual(self.run_check(cache=False).stdout, "")
        else:
            self.env.pop("XDG_CACHE_HOME", None)
            self.assertEqual(self.run_check(cache=False).stdout, self.notice())
            suffix = ("Library", "Caches", "SGSkills", "aibp") if platform.system() == "Darwin" else (".cache", "sgskills", "aibp")
            expected = Path(self.env["HOME"]).joinpath(*suffix)
            self.assertTrue(self.attempt_path(cache=expected).is_file())

    def test_only_cache_state_is_created(self):
        files_before = {p.relative_to(self.base) for p in self.base.rglob("*") if p.is_file()}
        self.assertEqual(self.run_check().stdout, self.notice())
        files_after = {p.relative_to(self.base) for p in self.base.rglob("*") if p.is_file()}
        for path in files_after - files_before:
            self.assertEqual(path.parts[0], self.cache.name)
            self.assertIn(path.name, ("last-attempt.txt", "attempt.lock"))
        self.assertEqual(self.package_hashes(), self.before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
