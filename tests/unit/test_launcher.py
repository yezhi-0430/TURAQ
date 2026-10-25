"""Launcher tests never start or stop real desktop services."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def clean_test_database():
    yield


def test_only_this_checkout_services_are_owned():
    from scripts.launch_turaq import owned_service

    root = Path("C:/Work/TURAQ Project")
    backend = (
        '"C:\\Work\\TURAQ Project\\.venv\\Scripts\\python.exe" -m uvicorn app.main:app --port 8888'
    )
    frontend = (
        'node "C:\\Work\\TURAQ Project\\frontend\\node_modules\\.bin\\..\\vite\\bin\\vite.js"'
    )
    assert owned_service(backend, "backend", root)
    assert owned_service(frontend, "frontend", root)
    assert not owned_service(backend.replace("TURAQ Project", "Another Project"), "backend", root)
    assert not owned_service("python -m uvicorn app.main:app --port 8888", "backend", root)
    assert not owned_service("node something.js", "frontend", root)


def test_local_environment_does_not_rewrite_or_expose_secrets(monkeypatch):
    from scripts.launch_turaq import local_environment

    monkeypatch.setenv("DASHSCOPE_API_KEY", "private-test-value")
    env = local_environment()
    assert env["SITE_BASE_URL"] == "http://localhost:3000"
    assert env["AUTH_COOKIE_SECURE"] == "false"
    assert env["API_PROXY_TARGET"] == "http://127.0.0.1:8888"
    assert env["DASHSCOPE_API_KEY"] == "private-test-value"


def test_port_conflict_never_kills_unrelated_process():
    from scripts.launch_turaq import check_owner

    with pytest.raises(RuntimeError, match="8888"):
        check_owner({"pid": 12, "command": "unrelated.exe"}, "backend", Path("C:/Work"))


def test_launcher_batch_paths_are_relative_to_script_location():
    content = Path("start.bat").read_text(encoding="utf-8")
    assert "%~dp0" in content
    assert "launch_turaq.py" in content
    assert "ANTHROPIC_API_KEY" not in content
    assert "--port 8000" not in content


def test_launcher_generates_settings_key_once(tmp_path, monkeypatch):
    from scripts import launch_turaq as launcher

    (tmp_path / ".env").write_text(
        "MODEL_PROVIDER=fake\nSETTINGS_ENCRYPTION_KEY=\n", encoding="utf-8"
    )
    monkeypatch.setattr(launcher, "ROOT", tmp_path)

    launcher.ensure_settings_key()
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    key = next(
        line.split("=", 1)[1]
        for line in text.splitlines()
        if line.startswith("SETTINGS_ENCRYPTION_KEY=")
    )
    assert len(key) == 44

    launcher.ensure_settings_key()
    assert (tmp_path / ".env").read_text(encoding="utf-8") == text


def test_launcher_appends_settings_key_when_missing(tmp_path, monkeypatch):
    from scripts import launch_turaq as launcher

    (tmp_path / ".env").write_text("MODEL_PROVIDER=fake\n", encoding="utf-8")
    monkeypatch.setattr(launcher, "ROOT", tmp_path)

    launcher.ensure_settings_key()
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "SETTINGS_ENCRYPTION_KEY=" in text
    assert text.startswith("MODEL_PROVIDER=fake\n")


def test_backend_loads_project_env_before_import_without_passing_file_to_frontend(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from scripts import launch_turaq as launcher

    (tmp_path / ".env").write_text("TURAQ_TRACE_ENABLED=1\n", encoding="utf-8")
    vite = tmp_path / "frontend/node_modules/vite/bin/vite.js"
    vite.parent.mkdir(parents=True)
    vite.touch()
    logs = tmp_path / "logs"
    logs.mkdir()
    commands = []
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.setattr(launcher, "LOGS", logs)
    monkeypatch.setattr(launcher, "port_processes", lambda: [])
    monkeypatch.setattr(launcher, "prepare_database", lambda: None)
    monkeypatch.setattr(launcher.shutil, "which", lambda _: "node.exe")
    monkeypatch.setattr(launcher, "ready", lambda _: True)
    monkeypatch.setattr(launcher, "read_url", lambda _: b'{"csrf_token":"test"}')

    def spawn(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(pid=123, poll=lambda: None)

    monkeypatch.setattr(launcher.subprocess, "Popen", spawn)
    launcher.run(no_browser=True)
    assert commands[0][commands[0].index("--env-file") + 1] == str(tmp_path / ".env")
    assert "--env-file" not in commands[1]


def test_uvicorn_env_file_enables_optional_adapter_without_importing_database(tmp_path):
    import os
    import subprocess
    import sys

    env_file = tmp_path / ".env"
    env_file.write_text(
        "TURAQ_TRACE_ENABLED=1\nLANGFUSE_BASE_URL=https://example.invalid\n"
        "LANGFUSE_PUBLIC_KEY=pk-lf-offline\nLANGFUSE_SECRET_KEY=sk-lf-offline\n",
        encoding="utf-8",
    )
    environment = {
        k: v
        for k, v in os.environ.items()
        if k != "TURAQ_TRACE_ENABLED" and not k.startswith("LANGFUSE_")
    }
    code = """
import sys,uvicorn
uvicorn.Config('test:app',env_file=sys.argv[1])
from app import observability
assert observability._exporter is not None
assert 'app.database' not in sys.modules
assert 'langfuse' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(env_file)],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
