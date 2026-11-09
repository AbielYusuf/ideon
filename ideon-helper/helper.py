"""Lightweight, secure, loopback-only local process runner for Ideon Quick Access."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

CONFIG_PATH = Path(__file__).resolve().with_name("config.json")
DEFAULT_PORT = 8001
DEFAULT_HOST = "127.0.0.1"
MAX_JSON_BODY_BYTES = 64 * 1024
LOCAL_URL_PATTERN = re.compile(r"^https?://[^\s]+$")


class ConfigValidationError(ValueError):
    """Raised when a configuration payload is invalid."""


def _clean_string(value: Any, field: str, *, required: bool = True) -> str:
    if not isinstance(value, str):
        raise ConfigValidationError(f"'{field}' must be a string.")
    cleaned = value.strip()
    if required and not cleaned:
        raise ConfigValidationError(f"'{field}' is required.")
    if "\x00" in cleaned or "\n" in cleaned or "\r" in cleaned:
        raise ConfigValidationError(f"'{field}' contains invalid characters.")
    return cleaned


def _clean_args(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ConfigValidationError("'args' must be a list of strings.")
    return [item.strip() for item in value if item.strip()]


def _clean_optional_local_url(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ConfigValidationError("'local_url' must be a string or null.")
    cleaned = value.strip()
    if cleaned and not LOCAL_URL_PATTERN.match(cleaned):
        raise ConfigValidationError("'local_url' must start with http:// or https://.")
    return cleaned or None


def _slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:48]
    return slug or fallback


def _unique_id(existing: list[dict[str, Any]], base: str) -> str:
    used = {item.get("id") for item in existing}
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _windows_executable_extensions() -> list[str]:
    """Return PATHEXT entries, always including .cmd and .bat on Windows."""
    if sys.platform != "win32":
        return []

    configured = [
        extension.strip().lower()
        for extension in os.environ.get("PATHEXT", "").split(os.pathsep)
        if extension.strip()
    ]
    for required in (".com", ".exe", ".bat", ".cmd"):
        if required not in configured:
            configured.append(required)

    return configured


def _windows_extra_path_dirs() -> list[str]:
    """Common Windows locations for global npm/pnpm and Node executables."""
    if sys.platform != "win32":
        return []

    candidates: list[str] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(os.path.join(appdata, "npm"))

    pnpm_home = os.environ.get("PNPM_HOME")
    if pnpm_home:
        candidates.append(pnpm_home)

    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(os.path.join(local_appdata, "pnpm"))

    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        program_files = os.environ.get(variable)
        if program_files:
            candidates.append(os.path.join(program_files, "nodejs"))

    directories: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        expanded = os.path.expandvars(os.path.expanduser(candidate))
        key = os.path.normcase(os.path.normpath(expanded))
        if key in seen or not os.path.isdir(expanded):
            continue
        seen.add(key)
        directories.append(expanded)

    return directories


def build_effective_path(base_path: str | None = None) -> str:
    """Build a PATH containing npm/Node locations even if the helper's is stale."""
    raw_path = os.environ.get("PATH", "") if base_path is None else base_path
    entries = [
        entry.strip().strip('"')
        for entry in raw_path.split(os.pathsep)
        if entry.strip().strip('"')
    ]
    entries.extend(_windows_extra_path_dirs())

    deduplicated: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        expanded = os.path.expandvars(os.path.expanduser(entry))
        key = os.path.normcase(os.path.normpath(expanded))
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(expanded)

    return os.pathsep.join(deduplicated)


def _candidate_filenames(name: str) -> list[str]:
    if sys.platform != "win32":
        return [name]

    extensions = _windows_executable_extensions()
    if any(name.lower().endswith(extension) for extension in extensions):
        return [name]

    return [name] + [f"{name}{extension}" for extension in extensions]


def _is_executable_file(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.X_OK)


def resolve_executable(
    executable: str, base_path: str | None = None
) -> str | None:
    """Resolve a bare name, relative path, or absolute path to an executable.

    On Windows this also checks PATHEXT so a configured ``pnpm`` resolves to
    ``pnpm.cmd``. The helper's PATH is augmented with common npm/Node folders
    without relying on a possibly stale environment inherited at startup.
    """
    name = executable.strip()
    if not name:
        return None

    effective_path = build_effective_path(base_path)
    resolved = shutil.which(name, path=effective_path)
    if resolved:
        return os.path.abspath(resolved)

    if os.path.dirname(name):
        for candidate in _candidate_filenames(name):
            if _is_executable_file(candidate):
                return os.path.abspath(candidate)
        return None

    for directory in effective_path.split(os.pathsep):
        for candidate in _candidate_filenames(name):
            full_path = os.path.join(directory, candidate)
            if _is_executable_file(full_path):
                return os.path.abspath(full_path)

    return None


def build_child_environment() -> dict[str, str]:
    """Return an environment that lets child processes find npm/pnpm shims."""
    environment = os.environ.copy()
    environment["PATH"] = build_effective_path()
    if sys.platform == "win32":
        environment["PATHEXT"] = os.pathsep.join(
            extension.upper() for extension in _windows_executable_extensions()
        )
    return environment



class ProjectProcessManager:
    """Thread-safe manager for predefined project subprocesses."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # project_id -> subprocess.Popen
        self._processes: dict[str, subprocess.Popen] = {}
        # project_id -> list of recent stdout/stderr lines
        self._logs: dict[str, list[str]] = {}

    def get_status(self, project_id: str) -> dict[str, Any]:
        with self._lock:
            proc = self._processes.get(project_id)
            if proc is None:
                return {"status": "stopped", "pid": None}

            poll_result = proc.poll()
            if poll_result is None:
                return {"status": "running", "pid": proc.pid}
            else:
                del self._processes[project_id]
                status_code = "error" if poll_result != 0 else "stopped"
                return {"status": status_code, "pid": None, "exit_code": poll_result}

    def start_project(
        self,
        project_id: str,
        executable: str,
        args: list[str],
        working_directory: str,
    ) -> dict[str, Any]:
        with self._lock:
            existing = self._processes.get(project_id)
            if existing is not None and existing.poll() is None:
                return {
                    "success": False,
                    "error": f"Project '{project_id}' is already running (PID: {existing.pid}).",
                    "status": "running",
                    "pid": existing.pid,
                }

            # Validate working directory
            work_path = Path(working_directory).resolve()
            if not work_path.is_dir():
                return {
                    "success": False,
                    "error": f"Configured working directory does not exist: {working_directory}",
                    "status": "error",
                }

            # Check executable availability. Resolve bare names such as "pnpm"
            # to Windows .cmd/.bat shims and include npm global directories in
            # PATH even if this long-running helper inherited a stale PATH.
            resolved_exec = resolve_executable(executable)
            if not resolved_exec:
                return {
                    "success": False,
                    "error": (
                        f"Executable not found: {executable}. Checked PATH and "
                        "common Windows npm/Node locations."
                    ),
                    "status": "error",
                }

            cmd = [resolved_exec] + args
            child_environment = build_child_environment()

            try:
                # On Windows, start subprocess in a new process group
                creation_flags = 0
                if sys.platform == "win32":
                    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

                proc = subprocess.Popen(
                    cmd,
                    cwd=str(work_path),
                    env=child_environment,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creation_flags,
                )
                self._processes[project_id] = proc
                return {
                    "success": True,
                    "status": "running",
                    "pid": proc.pid,
                    "message": f"Project '{project_id}' started successfully.",
                }
            except Exception as exc:
                return {
                    "success": False,
                    "error": f"Failed to start process: {exc}",
                    "status": "error",
                }

    def stop_project(self, project_id: str) -> dict[str, Any]:
        with self._lock:
            proc = self._processes.get(project_id)
            if proc is None or proc.poll() is not None:
                if project_id in self._processes:
                    del self._processes[project_id]
                return {
                    "success": False,
                    "error": f"Project '{project_id}' is not currently running.",
                    "status": "stopped",
                }

            try:
                # Terminate on Windows
                if sys.platform == "win32":
                    # Use taskkill /F /T to terminate child processes spawned by shell scripts or npm
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        capture_output=True,
                    )
                else:
                    proc.terminate()

                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            finally:
                if project_id in self._processes:
                    del self._processes[project_id]

            return {
                "success": True,
                "status": "stopped",
                "message": f"Project '{project_id}' stopped.",
            }


class IdeonHelperServer:
    def __init__(self, config_file: Path = CONFIG_PATH) -> None:
        self.config_file = config_file
        self._config_lock = threading.RLock()
        self.config = self.load_config()
        self.process_manager = ProjectProcessManager()

    def load_config(self) -> dict[str, Any]:
        if not self.config_file.exists():
            return {
                "helper_token": "ideon-local-secure-token-2026",
                "allowed_origins": ["http://localhost:3000", "http://127.0.0.1:3000"],
                "applications": [],
                "projects": [],
            }
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            if not isinstance(config, dict):
                raise ValueError("config root must be an object")
            config.setdefault("applications", [])
            config.setdefault("projects", [])
            return config
        except Exception as exc:
            print(f"[Helper] Warning: Could not read config file: {exc}")
            return {}

    def _save_config(self) -> None:
        """Persist configuration atomically, preserving unrelated keys."""
        with self._config_lock:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.config_file.with_name(
                f"{self.config_file.name}.tmp"
            )
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
                f.write("\n")
            os.replace(temp_path, self.config_file)

    def get_application(self, app_id: str) -> dict[str, Any] | None:
        with self._config_lock:
            for app in self.config.get("applications", []):
                if app.get("id") == app_id:
                    return dict(app)
        return None

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self._config_lock:
            for project in self.config.get("projects", []):
                if project.get("id") == project_id:
                    return dict(project)
        return None

    def list_applications(self) -> list[dict[str, Any]]:
        with self._config_lock:
            return [dict(app) for app in self.config.get("applications", [])]

    def list_projects(self) -> list[dict[str, Any]]:
        with self._config_lock:
            return [dict(project) for project in self.config.get("projects", [])]

    @staticmethod
    def _clean_application(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": _clean_string(payload.get("name"), "name"),
            "description": _clean_string(
                payload.get("description", ""), "description", required=False
            ),
            "executable": _clean_string(payload.get("executable"), "executable"),
            "args": _clean_args(payload.get("args")),
        }

    @staticmethod
    def _clean_project(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": _clean_string(payload.get("name"), "name"),
            "description": _clean_string(
                payload.get("description", ""), "description", required=False
            ),
            "working_directory": _clean_string(
                payload.get("working_directory"), "working_directory"
            ),
            "executable": _clean_string(payload.get("executable"), "executable"),
            "args": _clean_args(payload.get("args")),
            "local_url": _clean_optional_local_url(payload.get("local_url")),
        }

    def create_application(self, payload: dict[str, Any]) -> dict[str, Any]:
        cleaned = self._clean_application(payload)
        with self._config_lock:
            applications = self.config.setdefault("applications", [])
            application = {
                "id": _unique_id(applications, _slugify(cleaned["name"], "application")),
                **cleaned,
            }
            applications.append(application)
            self._save_config()
            return dict(application)

    def update_application(
        self, app_id: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        cleaned = self._clean_application(payload)
        with self._config_lock:
            applications = self.config.setdefault("applications", [])
            for index, application in enumerate(applications):
                if application.get("id") == app_id:
                    updated = {"id": app_id, **cleaned}
                    applications[index] = updated
                    self._save_config()
                    return dict(updated)
        return None

    def delete_application(self, app_id: str) -> bool:
        with self._config_lock:
            applications = self.config.setdefault("applications", [])
            for index, application in enumerate(applications):
                if application.get("id") == app_id:
                    del applications[index]
                    self._save_config()
                    return True
        return False

    def create_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        cleaned = self._clean_project(payload)
        with self._config_lock:
            projects = self.config.setdefault("projects", [])
            project = {
                "id": _unique_id(projects, _slugify(cleaned["name"], "project")),
                **cleaned,
            }
            projects.append(project)
            self._save_config()
            return dict(project)

    def update_project(
        self, project_id: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        cleaned = self._clean_project(payload)
        with self._config_lock:
            status = self.process_manager.get_status(project_id)
            if status.get("status") == "running":
                raise ConfigValidationError(
                    "Stop the project before editing its configuration."
                )
            projects = self.config.setdefault("projects", [])
            for index, project in enumerate(projects):
                if project.get("id") == project_id:
                    updated = {"id": project_id, **cleaned}
                    projects[index] = updated
                    self._save_config()
                    return dict(updated)
        return None

    def delete_project(self, project_id: str) -> bool:
        with self._config_lock:
            projects = self.config.setdefault("projects", [])
            for index, project in enumerate(projects):
                if project.get("id") == project_id:
                    self.process_manager.stop_project(project_id)
                    del projects[index]
                    self._save_config()
                    return True
        return False


def make_request_handler(helper: IdeonHelperServer):
    class HelperRequestHandler(BaseHTTPRequestHandler):
        def _send_json(self, status_code: int, data: Any):
            origin = self.headers.get("Origin", "")
            allowed_origins = helper.config.get("allowed_origins", [])

            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")

            if origin in allowed_origins:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Credentials", "true")
                self.send_header(
                    "Access-Control-Allow-Methods", "GET, POST, OPTIONS"
                )
                self.send_header(
                    "Access-Control-Allow-Headers",
                    "Content-Type, X-Helper-Token",
                )

            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

        def _validate_security(self, require_token: bool = False) -> bool:
            # 1. Host header validation (DNS rebinding mitigation)
            host = self.headers.get("Host", "")
            allowed_hosts = [
                f"127.0.0.1:{DEFAULT_PORT}",
                f"localhost:{DEFAULT_PORT}",
                "127.0.0.1",
                "localhost",
            ]
            if not any(host.startswith(h) for h in allowed_hosts):
                self._send_json(
                    HTTPStatus.FORBIDDEN,
                    {"error": f"Invalid Host header: {host}"},
                )
                return False

            # 2. Origin validation for cross-origin requests
            origin = self.headers.get("Origin")
            allowed_origins = helper.config.get("allowed_origins", [])
            if origin and origin not in allowed_origins:
                self._send_json(
                    HTTPStatus.FORBIDDEN,
                    {"error": f"Unauthorized Origin: {origin}"},
                )
                return False

            # 3. Secret token validation for state-changing requests
            if require_token:
                expected_token = helper.config.get("helper_token")
                provided_token = self.headers.get("X-Helper-Token")
                if expected_token and provided_token != expected_token:
                    self._send_json(
                        HTTPStatus.UNAUTHORIZED,
                        {"error": "Missing or invalid X-Helper-Token header."},
                    )
                    return False

            return True

        def _read_json_body(self) -> dict[str, Any] | None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "Invalid Content-Length header."},
                )
                return None

            if length > MAX_JSON_BODY_BYTES:
                self._send_json(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    {"error": "Request body is too large."},
                )
                return None

            if length <= 0:
                return {}

            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "Request body must be valid JSON."},
                )
                return None

            if not isinstance(payload, dict):
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "Request body must be a JSON object."},
                )
                return None

            return payload

        def do_OPTIONS(self):
            origin = self.headers.get("Origin", "")
            allowed_origins = helper.config.get("allowed_origins", [])

            self.send_response(HTTPStatus.NO_CONTENT)
            if origin in allowed_origins:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Credentials", "true")
                self.send_header(
                    "Access-Control-Allow-Methods", "GET, POST, OPTIONS"
                )
                self.send_header(
                    "Access-Control-Allow-Headers",
                    "Content-Type, X-Helper-Token",
                )
            self.end_headers()

        def do_GET(self):
            if not self._validate_security(require_token=False):
                return

            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/")

            if path == "/health" or path == "":
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "service": "Ideon Local Helper",
                        "loopback_only": True,
                    },
                )
                return

            if path == "/applications":
                apps = [
                    {
                        "id": app["id"],
                        "name": app.get("name", ""),
                        "description": app.get("description", ""),
                        "executable": app.get("executable", ""),
                        "args": list(app.get("args", [])),
                    }
                    for app in helper.list_applications()
                ]
                self._send_json(HTTPStatus.OK, apps)
                return

            if path == "/projects":
                projects = []
                for p in helper.list_projects():
                    status_info = helper.process_manager.get_status(p["id"])
                    projects.append(
                        {
                            "id": p["id"],
                            "name": p.get("name", ""),
                            "description": p.get("description", ""),
                            "working_directory": p.get("working_directory", ""),
                            "executable": p.get("executable", ""),
                            "args": list(p.get("args", [])),
                            "development_command": f"{p.get('executable', '')} {' '.join(p.get('args', []))}".strip(),
                            "local_url": p.get("local_url"),
                            "status": status_info["status"],
                            "pid": status_info.get("pid"),
                        }
                    )
                self._send_json(HTTPStatus.OK, projects)
                return

            if path.startswith("/projects/") and path.endswith("/status"):
                parts = path.split("/")
                if len(parts) == 4:
                    project_id = parts[2]
                    project = helper.get_project(project_id)
                    if not project:
                        self._send_json(
                            HTTPStatus.NOT_FOUND,
                            {"error": f"Project '{project_id}' not found."},
                        )
                        return
                    status_info = helper.process_manager.get_status(project_id)
                    self._send_json(
                        HTTPStatus.OK,
                        {"id": project_id, **status_info},
                    )
                    return

            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Endpoint not found."})

        def do_POST(self):
            if not self._validate_security(require_token=True):
                return

            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/")

            if path == "/applications":
                payload = self._read_json_body()
                if payload is None:
                    return
                try:
                    application = helper.create_application(payload)
                except ConfigValidationError as exc:
                    self._send_json(
                        HTTPStatus.BAD_REQUEST, {"error": str(exc)}
                    )
                    return
                self._send_json(HTTPStatus.CREATED, application)
                return

            if path == "/projects":
                payload = self._read_json_body()
                if payload is None:
                    return
                try:
                    project = helper.create_project(payload)
                except ConfigValidationError as exc:
                    self._send_json(
                        HTTPStatus.BAD_REQUEST, {"error": str(exc)}
                    )
                    return
                self._send_json(HTTPStatus.CREATED, project)
                return

            parts = path.split("/")
            if (
                len(parts) == 4
                and parts[1] in ("applications", "projects")
                and parts[3] in ("update", "delete")
            ):
                kind, item_id, action = parts[1], parts[2], parts[3]

                if kind == "applications":
                    if action == "delete":
                        if helper.delete_application(item_id):
                            self._send_json(
                                HTTPStatus.OK,
                                {"success": True, "id": item_id},
                            )
                        else:
                            self._send_json(
                                HTTPStatus.NOT_FOUND,
                                {"error": f"Application '{item_id}' not found."},
                            )
                        return

                    payload = self._read_json_body()
                    if payload is None:
                        return
                    try:
                        application = helper.update_application(item_id, payload)
                    except ConfigValidationError as exc:
                        self._send_json(
                            HTTPStatus.BAD_REQUEST, {"error": str(exc)}
                        )
                        return
                    if application is None:
                        self._send_json(
                            HTTPStatus.NOT_FOUND,
                            {"error": f"Application '{item_id}' not found."},
                        )
                    else:
                        self._send_json(HTTPStatus.OK, application)
                    return

                if action == "delete":
                    if helper.delete_project(item_id):
                        self._send_json(
                            HTTPStatus.OK, {"success": True, "id": item_id}
                        )
                    else:
                        self._send_json(
                            HTTPStatus.NOT_FOUND,
                            {"error": f"Project '{item_id}' not found."},
                        )
                    return

                payload = self._read_json_body()
                if payload is None:
                    return
                try:
                    project = helper.update_project(item_id, payload)
                except ConfigValidationError as exc:
                    self._send_json(
                        HTTPStatus.BAD_REQUEST, {"error": str(exc)}
                    )
                    return
                if project is None:
                    self._send_json(
                        HTTPStatus.NOT_FOUND,
                        {"error": f"Project '{item_id}' not found."},
                    )
                else:
                    self._send_json(HTTPStatus.OK, project)
                return

            if path.startswith("/applications/") and path.endswith("/launch"):
                parts = path.split("/")
                if len(parts) == 4:
                    app_id = parts[2]
                    app = helper.get_application(app_id)
                    if not app:
                        self._send_json(
                            HTTPStatus.NOT_FOUND,
                            {"error": f"Application '{app_id}' not configured."},
                        )
                        return

                    executable = app.get("executable")
                    args = app.get("args", [])
                    if not isinstance(args, list):
                        args = []

                    resolved_exec = (
                        resolve_executable(executable)
                        if isinstance(executable, str)
                        else None
                    )
                    if not resolved_exec:
                        self._send_json(
                            HTTPStatus.BAD_REQUEST,
                            {
                                "success": False,
                                "error": (
                                    f"Executable not found: {executable}. "
                                    "Checked PATH and common Windows npm/Node "
                                    "locations."
                                ),
                            },
                        )
                        return

                    child_environment = build_child_environment()
                    try:
                        # Launch application safely, without a general shell.
                        if (
                            sys.platform == "win32"
                            and not args
                            and isinstance(executable, str)
                            and Path(executable).exists()
                        ):
                            os.startfile(executable)
                        else:
                            subprocess.Popen(
                                [resolved_exec] + args,
                                env=child_environment,
                                shell=False,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                            )

                        self._send_json(
                            HTTPStatus.OK,
                            {
                                "success": True,
                                "message": f"Application '{app['name']}' launched.",
                            },
                        )
                    except Exception as exc:
                        self._send_json(
                            HTTPStatus.INTERNAL_SERVER_ERROR,
                            {"success": False, "error": f"Could not launch app: {exc}"},
                        )
                    return

            if path.startswith("/projects/") and path.endswith("/start"):
                parts = path.split("/")
                if len(parts) == 4:
                    project_id = parts[2]
                    project = helper.get_project(project_id)
                    if not project:
                        self._send_json(
                            HTTPStatus.NOT_FOUND,
                            {"error": f"Project '{project_id}' not found."},
                        )
                        return

                    result = helper.process_manager.start_project(
                        project_id=project_id,
                        executable=project.get("executable", ""),
                        args=project.get("args", []),
                        working_directory=project.get("working_directory", "."),
                    )
                    status_code = (
                        HTTPStatus.OK
                        if result.get("success")
                        else HTTPStatus.BAD_REQUEST
                    )
                    self._send_json(status_code, result)
                    return

            if path.startswith("/projects/") and path.endswith("/stop"):
                parts = path.split("/")
                if len(parts) == 4:
                    project_id = parts[2]
                    project = helper.get_project(project_id)
                    if not project:
                        self._send_json(
                            HTTPStatus.NOT_FOUND,
                            {"error": f"Project '{project_id}' not found."},
                        )
                        return

                    result = helper.process_manager.stop_project(project_id)
                    status_code = (
                        HTTPStatus.OK
                        if result.get("success")
                        else HTTPStatus.BAD_REQUEST
                    )
                    self._send_json(status_code, result)
                    return

            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Endpoint not found."})

        def log_message(self, format: str, *args: Any) -> None:
            # Suppress normal stdout spam
            pass

    return HelperRequestHandler


def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
    # Enforce loopback-only binding
    if host not in ("127.0.0.1", "localhost"):
        raise ValueError("Ideon Helper must only bind to 127.0.0.1 for security.")

    helper = IdeonHelperServer()
    handler_cls = make_request_handler(helper)
    server = ThreadingHTTPServer((host, port), handler_cls)
    print(f"[Ideon Helper] Running securely on http://{host}:{port} (Loopback only)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Ideon Helper] Shutting down.")
        server.server_close()


if __name__ == "__main__":
    run_server()
