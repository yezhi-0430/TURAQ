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
