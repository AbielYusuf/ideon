"""Security and functionality tests for ideon-helper."""

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from pathlib import Path

from helper import (
    DEFAULT_PORT,
    IdeonHelperServer,
    ProjectProcessManager,
    ThreadingHTTPServer,
    build_child_environment,
    build_effective_path,
    make_request_handler,
    resolve_executable,
)


ACTUAL_PNPM = resolve_executable("pnpm")


class IdeonHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create temp config file
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.config_path = Path(cls.temp_dir.name) / "test_config.json"
        config_data = {
            "helper_token": "test-secret-token",
            "allowed_origins": ["http://localhost:3000"],
            "applications": [
                {
                    "id": "mock-app",
                    "name": "Mock Application",
                    "description": "For testing",
                    "executable": "cmd.exe",
                    "args": ["/c", "echo", "hello"],
                }
            ],
            "projects": [
                {
                    "id": "mock-proj",
                    "name": "Mock Project",
                    "description": "For testing",
                    "working_directory": cls.temp_dir.name,
                    "executable": "cmd.exe",
                    "args": ["/c", "ping", "127.0.0.1", "-n", "3"],
                    "local_url": "http://localhost:8080",
                }
            ],
        }
        with open(cls.config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f)

        cls.helper = IdeonHelperServer(config_file=cls.config_path)
        cls.port = 8999
        handler_cls = make_request_handler(cls.helper)
        cls.server = ThreadingHTTPServer(("127.0.0.1", cls.port), handler_cls)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp_dir.cleanup()

    def _request(self, method, path, headers=None, body=None):
        conn = HTTPConnection("127.0.0.1", self.port)
        default_headers = {
            "Host": f"127.0.0.1:{self.port}",
            "Origin": "http://localhost:3000",
        }
        if headers:
            default_headers.update(headers)
        conn.request(method, path, body=body, headers=default_headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, json.loads(data.decode("utf-8")) if data else {}

    def test_health_check(self):
        status, data = self._request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(data.get("status"), "ok")

    def test_reject_unauthorized_origin(self):
        # Cross origin attack simulation
        status, data = self._request(
            "GET",
            "/health",
            headers={"Origin": "https://malicious-site.com"},
        )
        self.assertEqual(status, 403)
        self.assertIn("Unauthorized Origin", data.get("error", ""))

    def test_reject_dns_rebinding_host(self):
        # Host header spoofing
        status, data = self._request(
            "GET",
            "/health",
            headers={"Host": "attacker.com"},
        )
        self.assertEqual(status, 403)
        self.assertIn("Invalid Host header", data.get("error", ""))

    def test_reject_post_without_token(self):
        # State-changing request without secret token
        status, data = self._request(
            "POST",
            "/applications/mock-app/launch",
        )
        self.assertEqual(status, 401)
        self.assertIn("Missing or invalid X-Helper-Token", data.get("error", ""))

    def test_launch_application_success(self):
        status, data = self._request(
            "POST",
            "/applications/mock-app/launch",
            headers={"X-Helper-Token": "test-secret-token"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(data.get("success"))

    def test_project_lifecycle(self):
        # 1. Initially stopped
        status, data = self._request("GET", "/projects/mock-proj/status")
        self.assertEqual(status, 200)
        self.assertEqual(data.get("status"), "stopped")

        # 2. Start project
        status, data = self._request(
            "POST",
            "/projects/mock-proj/start",
            headers={"X-Helper-Token": "test-secret-token"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(data.get("status"), "running")

        # 3. Prevent duplicate start
        status, data = self._request(
            "POST",
            "/projects/mock-proj/start",
            headers={"X-Helper-Token": "test-secret-token"},
        )
        self.assertEqual(status, 400)
        self.assertIn("already running", data.get("error", ""))

        # 4. Stop project
        status, data = self._request(
            "POST",
            "/projects/mock-proj/stop",
            headers={"X-Helper-Token": "test-secret-token"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(data.get("status"), "stopped")


class ExecutableResolutionTests(unittest.TestCase):
    """Windows executable/PATH resolution without relying on the real pnpm."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.shim_dir = self.root / "npm-global"
        self.shim_dir.mkdir()
        self.result_file = self.root / "result.txt"
        self.cmd_file = self.shim_dir / "pnpm.cmd"
        script_lines = [
            "@echo off",
            f'> "{self.result_file}" echo CWD=%CD%',
            f'>> "{self.result_file}" echo ARG1=%~1',
            f'>> "{self.result_file}" echo ARG2=%~2',
            f'>> "{self.result_file}" echo PATH=%PATH%',
            "exit /b 0",
        ]
        self.cmd_file.write_text(
            "\r\n".join(script_lines) + "\r\n", encoding="utf-8"
        )

        self.original_path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(self.shim_dir) + os.pathsep + self.original_path

    def tearDown(self):
        os.environ["PATH"] = self.original_path
        self.temp_dir.cleanup()

    def test_resolve_bare_name_to_cmd_shim(self):
        resolved = resolve_executable("pnpm", base_path=str(self.shim_dir))
        self.assertIsNotNone(resolved)
        self.assertEqual(
            os.path.normcase(resolved), os.path.normcase(str(self.cmd_file))
        )

    def test_resolve_explicit_cmd_extension(self):
        resolved = resolve_executable("pnpm.cmd", base_path=str(self.shim_dir))
        self.assertIsNotNone(resolved)
        self.assertEqual(
            os.path.normcase(resolved), os.path.normcase(str(self.cmd_file))
        )

    def test_resolve_absolute_cmd_path(self):
        resolved = resolve_executable(str(self.cmd_file))
        self.assertIsNotNone(resolved)
        self.assertEqual(
            os.path.normcase(resolved), os.path.normcase(str(self.cmd_file))
        )

    def test_resolve_absolute_path_without_extension(self):
        extensionless = self.shim_dir / "pnpm"
        self.assertFalse(extensionless.exists())
        resolved = resolve_executable(str(extensionless))
        self.assertIsNotNone(resolved)
        self.assertEqual(
            os.path.normcase(resolved), os.path.normcase(str(self.cmd_file))
        )

    def test_missing_executable_returns_none(self):
        self.assertIsNone(
            resolve_executable("ideon-definitely-missing-executable-12345")
        )

    def test_effective_path_and_child_environment_include_npm_locations(self):
        effective = build_effective_path(base_path=str(self.shim_dir))
        entries = {
            os.path.normcase(os.path.normpath(entry))
            for entry in effective.split(os.pathsep)
        }
        self.assertIn(os.path.normcase(os.path.normpath(str(self.shim_dir))), entries)

        appdata = os.environ.get("APPDATA")
        if appdata:
            npm_dir = Path(appdata) / "npm"
            if npm_dir.is_dir():
                self.assertIn(
                    os.path.normcase(os.path.normpath(str(npm_dir))), entries
                )

        child_path = build_child_environment()["PATH"]
        self.assertIn(
            os.path.normcase(os.path.normpath(str(self.shim_dir))),
            {
                os.path.normcase(os.path.normpath(entry))
                for entry in child_path.split(os.pathsep)
            },
        )

        if sys.platform == "win32":
            pathext = build_child_environment()["PATHEXT"].upper()
            self.assertIn(".CMD", pathext)
            self.assertIn(".BAT", pathext)

    def test_start_project_passes_args_cwd_and_augmented_path(self):
        work_dir = self.root / "working directory"
        work_dir.mkdir()
        manager = ProjectProcessManager()

        result = manager.start_project(
            project_id="fake-pnpm",
            executable="pnpm",
            args=["alpha", "two words"],
            working_directory=str(work_dir),
        )
        self.assertTrue(result.get("success"), result.get("error"))

        deadline = time.time() + 10
        content = ""
        while time.time() < deadline:
            if self.result_file.exists():
                content = self.result_file.read_text(
                    encoding="utf-8", errors="replace"
                )
                if "PATH=" in content:
                    break
            time.sleep(0.05)

        self.assertIn("CWD=", content)
        self.assertIn(f"CWD={work_dir}", content)
        self.assertIn("ARG1=alpha", content)
        self.assertIn("ARG2=two words", content)
        path_line = next(
            line for line in content.splitlines() if line.startswith("PATH=")
        )
        self.assertIn(
            str(self.shim_dir),
            path_line,
        )
        manager.get_status("fake-pnpm")

    def test_missing_executable_has_clear_project_error(self):
        manager = ProjectProcessManager()
        result = manager.start_project(
            project_id="missing-project",
            executable="ideon-definitely-missing-executable-12345",
            args=[],
            working_directory=self.temp_dir.name,
        )
        self.assertFalse(result.get("success"))
        self.assertIn("Executable not found", result.get("error", ""))
        self.assertIn(
            "ideon-definitely-missing-executable-12345", result.get("error", "")
        )

    @unittest.skipUnless(sys.platform == "win32", "Windows resolution test")
    def test_resolve_actual_npm_and_cmd(self):
        for name in ("npm", "cmd"):
            with self.subTest(executable=name):
                resolved = resolve_executable(name)
                self.assertIsNotNone(resolved, f"{name} should resolve")
                self.assertTrue(Path(resolved).exists())

    @unittest.skipUnless(
        sys.platform == "win32" and ACTUAL_PNPM is not None,
        "pnpm is not installed on this machine",
    )
    def test_resolve_actual_pnpm_and_absolute_path(self):
        # Empty base PATH simulates a helper started before npm global was added.
        by_name = resolve_executable("pnpm", base_path="")
        by_extension = resolve_executable("pnpm.cmd", base_path="")
        by_absolute = resolve_executable(ACTUAL_PNPM)

        self.assertIsNotNone(by_name)
        self.assertIsNotNone(by_extension)
        self.assertIsNotNone(by_absolute)
        self.assertTrue(Path(by_name).is_file())
        self.assertEqual(
            os.path.normcase(by_name), os.path.normcase(ACTUAL_PNPM)
        )
        self.assertEqual(
            os.path.normcase(by_extension), os.path.normcase(ACTUAL_PNPM)
        )
        self.assertEqual(
            os.path.normcase(by_absolute), os.path.normcase(ACTUAL_PNPM)
        )


class HelperConfigCrudTests(unittest.TestCase):
    """Create/edit/delete tests for application and project configuration."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.config_path = Path(cls.temp_dir.name) / "crud_config.json"
        config_data = {
            "helper_token": "crud-secret-token",
            "allowed_origins": ["http://localhost:3000"],
            "applications": [],
            "projects": [],
        }
        with open(cls.config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f)

        cls.helper = IdeonHelperServer(config_file=cls.config_path)
        cls.port = 8998
        handler_cls = make_request_handler(cls.helper)
        cls.server = ThreadingHTTPServer(("127.0.0.1", cls.port), handler_cls)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp_dir.cleanup()

    def _request(self, method, path, headers=None, body=None):
        conn = HTTPConnection("127.0.0.1", self.port)
        default_headers = {
            "Host": f"127.0.0.1:{self.port}",
            "Origin": "http://localhost:3000",
        }
        if headers:
            default_headers.update(headers)
        conn.request(method, path, body=body, headers=default_headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, json.loads(data.decode("utf-8")) if data else {}

    def _post(self, path, payload):
        return self._request(
            "POST",
            path,
            headers={
                "X-Helper-Token": "crud-secret-token",
                "Content-Type": "application/json",
            },
            body=json.dumps(payload),
        )

    def test_application_crud_and_persistence(self):
        status, created = self._post(
            "/applications",
            {
                "name": "Test Editor",
                "description": "Created by tests",
                "executable": "cmd.exe",
                "args": ["/c", "echo", "hello"],
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(created["id"], "test-editor")

        status, applications = self._request("GET", "/applications")
        self.assertEqual(status, 200)
        stored = next(app for app in applications if app["id"] == "test-editor")
        self.assertEqual(stored["executable"], "cmd.exe")
        self.assertEqual(stored["args"], ["/c", "echo", "hello"])

        status, updated = self._post(
            "/applications/test-editor/update",
            {
                "name": "Test Editor Updated",
                "description": "Updated by tests",
                "executable": "code.cmd",
                "args": ["--new-window"],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated["id"], "test-editor")

        reloaded = IdeonHelperServer(config_file=self.config_path)
        persisted = reloaded.get_application("test-editor")
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted["executable"], "code.cmd")
        self.assertEqual(persisted["args"], ["--new-window"])
        self.assertEqual(reloaded.config["helper_token"], "crud-secret-token")

        status, deleted = self._post("/applications/test-editor/delete", {})
        self.assertEqual(status, 200)
        self.assertTrue(deleted["success"])
        self.assertIsNone(
            IdeonHelperServer(config_file=self.config_path).get_application(
                "test-editor"
            )
        )

    def test_project_crud_and_persistence(self):
        status, created = self._post(
            "/projects",
            {
                "name": "Test Project",
                "description": "Created by tests",
                "working_directory": self.temp_dir.name,
                "executable": "cmd.exe",
                "args": ["/c", "echo", "ok"],
                "local_url": "http://localhost:4321",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(created["id"], "test-project")

        status, projects = self._request("GET", "/projects")
        self.assertEqual(status, 200)
        stored = next(p for p in projects if p["id"] == "test-project")
        self.assertEqual(stored["executable"], "cmd.exe")
        self.assertEqual(stored["args"], ["/c", "echo", "ok"])
        self.assertEqual(stored["local_url"], "http://localhost:4321")

        status, updated = self._post(
            "/projects/test-project/update",
            {
                "name": "Test Project Updated",
                "description": "Updated by tests",
                "working_directory": self.temp_dir.name,
                "executable": "cmd.exe",
                "args": ["/c", "echo", "updated"],
                "local_url": None,
            },
        )
        self.assertEqual(status, 200)

        reloaded = IdeonHelperServer(config_file=self.config_path)
        persisted = reloaded.get_project("test-project")
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted["args"], ["/c", "echo", "updated"])
        self.assertIsNone(persisted["local_url"])

        status, deleted = self._post("/projects/test-project/delete", {})
        self.assertEqual(status, 200)
        self.assertIsNone(
            IdeonHelperServer(config_file=self.config_path).get_project("test-project")
        )

    def test_invalid_payloads_are_rejected(self):
        status, data = self._post(
            "/applications",
            {"name": "Missing executable", "args": []},
        )
        self.assertEqual(status, 400)
        self.assertIn("executable", data.get("error", ""))

        status, data = self._post(
            "/projects",
            {
                "name": "Bad URL",
                "working_directory": self.temp_dir.name,
                "executable": "cmd.exe",
                "args": [],
                "local_url": "javascript:alert(1)",
            },
        )
        self.assertEqual(status, 400)
        self.assertIn("local_url", data.get("error", ""))

    def test_mutations_require_token(self):
        status, data = self._request(
            "POST",
            "/applications",
            headers={"Content-Type": "application/json"},
            body=json.dumps(
                {
                    "name": "No Token",
                    "description": "",
                    "executable": "cmd.exe",
                    "args": [],
                }
            ),
        )
        self.assertEqual(status, 401)
        self.assertIn("X-Helper-Token", data.get("error", ""))

    def test_duplicate_names_get_unique_ids(self):
        payload = {
            "name": "Duplicate Name",
            "description": "",
            "executable": "cmd.exe",
            "args": [],
        }
        status, first = self._post("/applications", payload)
        self.assertEqual(status, 201)
        status, second = self._post("/applications", payload)
        self.assertEqual(status, 201)
        self.assertNotEqual(first["id"], second["id"])

        self._post(f"/applications/{first['id']}/delete", {})
        self._post(f"/applications/{second['id']}/delete", {})


if __name__ == "__main__":
    unittest.main()
