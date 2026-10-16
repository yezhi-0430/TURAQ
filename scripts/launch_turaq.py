"""Windows local launcher with owned-process checks and hidden, logged services."""

import argparse
import contextlib
import json
import ntpath
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / ".local-backups" / "launcher"
PORTS = {"backend": 8888, "frontend": 3000}
HIDDEN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def say(message):
    print(message, flush=True)


def owned_service(command, kind, root=ROOT):
    tokens = [part.strip('"') for part in re.findall(r'"[^"]*"|\S+', command or "")]
    normalized = {ntpath.normcase(ntpath.normpath(part)) for part in tokens}
    if kind == "backend":
        executable = ntpath.normcase(ntpath.normpath(str(root / ".venv/Scripts/python.exe")))
        return executable in normalized and "uvicorn" in tokens and "app.main:app" in tokens
    script = ntpath.normcase(ntpath.normpath(str(root / "frontend/node_modules/vite/bin/vite.js")))
    return script in normalized


def check_owner(info, kind, root=ROOT):
    if info and not owned_service(info["command"], kind, root):
        raise RuntimeError(
            f"端口 {PORTS[kind]} 被其他程序占用（PID {info['pid']}），请先释放端口。"
        )


def local_environment():
    env = os.environ.copy()
    env.update(
        SITE_BASE_URL="http://localhost:3000",
        AUTH_COOKIE_SECURE="false",
        API_PROXY_TARGET="http://127.0.0.1:8888",
        PYTHONUTF8="1",
    )
    return env


def port_processes():
    script = """
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding
    $rows = @(Get-NetTCPConnection -LocalPort 3000,8888 -State Listen -ErrorAction Ignore |
        Select-Object LocalPort,OwningProcess -Unique | ForEach-Object {
        $proc = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $_.OwningProcess)
        [PSCustomObject]@{port=$_.LocalPort;pid=$_.OwningProcess;command=$proc.CommandLine}
    })
    ConvertTo-Json -InputObject $rows -Compress
    """
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        timeout=20,
        creationflags=HIDDEN,
        check=True,
    )
    return json.loads(result.stdout.decode("utf-8-sig").strip() or "[]")


def read_url(url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=2) as response:
        return response.read()


def ready(kind):
    try:
        if kind == "backend":
            api = json.loads(read_url("http://127.0.0.1:8888/openapi.json"))
            return "/api/v1/risk/events" in api.get("paths", {})
        return b"TURAQ" in read_url("http://localhost:3000")
    except (OSError, ValueError):
        return False


def stop_owned(rows):
    current = {row["pid"]: row for row in port_processes()}
    for row in rows:
        kind = next(k for k, port in PORTS.items() if row["port"] == port)
        check_owner(row, kind)
        live = current.get(row["pid"])
        if not live:
            continue
        check_owner(live, kind)
        subprocess.run(
            ["taskkill.exe", "/PID", str(row["pid"]), "/T", "/F"],
            capture_output=True,
            timeout=20,
            creationflags=HIDDEN,
            check=True,
        )
        say(f"已停止 {kind}（端口 {row['port']}）。")


def prepare_database():
    from sqlalchemy import inspect

    from app.database import engine, settings
    from app.risk_schema import upgrade_risk_tables

    try:
        with engine.connect() as connection:
            tables = set(inspect(connection).get_table_names())
        if not {"users", "stocks", "watchlists"} <= tables:
            raise RuntimeError(
                "数据库账号/自选表尚未初始化，请先按 docs/auth-local-acceptance.md 配置。"
            )
        if {"risk_analyses", "risk_events", "risk_tasks", "risk_task_items"} <= tables:
            say("数据库连接正常，风险表已就绪。")
            return
        pg_dump = shutil.which("pg_dump")
        if not pg_dump:
            candidates = sorted(
                Path(os.environ.get("ProgramFiles", "C:/Program Files")).glob(
                    "PostgreSQL/*/bin/pg_dump.exe"
                ),
                reverse=True,
            )
            pg_dump = str(candidates[0]) if candidates else None
        if not pg_dump:
            raise RuntimeError("风险表尚未初始化，且未找到 pg_dump，请安装 PostgreSQL 客户端。")
        backup = LOGS / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-before-risk.dump")
        env = os.environ.copy()
        env["PGPASSWORD"] = settings.database_password.get_secret_value()
        env["PGCONNECT_TIMEOUT"] = "5"
        say("首次启用风险工作台：正在备份数据库…")
        with (LOGS / "schema.log").open("ab") as log:
            subprocess.run(
                [
                    pg_dump,
                    "-h",
                    settings.database_host,
                    "-p",
                    str(settings.database_port),
                    "-U",
                    settings.database_user,
                    "-d",
                    settings.database_name,
                    "-Fc",
                    "-f",
                    str(backup),
                ],
                env=env,
                stderr=log,
                stdout=log,
                timeout=120,
                check=True,
                creationflags=HIDDEN,
            )
        upgrade_risk_tables(engine)
        say(f"风险表已创建，备份：{backup.name}")
    finally:
        engine.dispose()


@contextlib.contextmanager
def launch_lock():
    import msvcrt

    with (LOGS / "launcher.lock").open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError("另一个启动或停止操作正在进行，请稍候。") from exc
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def run(stop=False, no_browser=False):
    rows = port_processes()
    for row in rows:
        kind = next(k for k, port in PORTS.items() if row["port"] == port)
        check_owner(row, kind)
    if stop:
        stop_owned(rows)
        say("TURAQ 前后端均已停止。" if rows else "当前没有运行中的 TURAQ 服务。")
        return
    if not (ROOT / ".env").is_file():
        raise RuntimeError("缺少 .env，请参照 .env.example 配置数据库与模型。")
    node = shutil.which("node")
    vite = ROOT / "frontend/node_modules/vite/bin/vite.js"
    if not node or not vite.is_file():
        raise RuntimeError(
            "未找到 Node.js 或前端依赖，请安装 Node.js 并在 frontend 运行 npm install。"
        )
    prepare_database()
    commands = {
        "backend": [
            str(ROOT / ".venv/Scripts/python.exe"),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8888",
            "--reload",
        ],
        "frontend": [node, str(vite), "--host", "localhost", "--port", "3000", "--strictPort"],
    }
    children = []
    try:
        for kind, command in commands.items():
            running = [row for row in rows if row["port"] == PORTS[kind]]
            if running and ready(kind):
                say(f"{kind} 已运行，复用端口 {PORTS[kind]}。")
                continue
            if running:
                say(f"{kind} 服务未就绪，重启本项目的旧进程。")
                stop_owned(running)
            with (LOGS / f"{kind}.log").open("ab") as log:
                child = subprocess.Popen(
                    command,
                    cwd=ROOT if kind == "backend" else ROOT / "frontend",
                    env=local_environment(),
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    creationflags=HIDDEN,
                    close_fds=True,
                )
            children.append(child)
            say(f"正在启动 {kind}…")
            deadline = time.monotonic() + 45
            while not ready(kind):
                if child.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError(f"{kind} 启动失败，请查看 {LOGS / (kind + '.log')}。")
                time.sleep(0.4)
            say(f"{kind} 已就绪（端口 {PORTS[kind]}）。")
        session = json.loads(read_url("http://localhost:3000/api/v1/auth/session"))
        if "csrf_token" not in session:
            raise RuntimeError("前端 API 代理未就绪，请查看 frontend.log。")
        say("启动成功：http://localhost:3000")
        if not no_browser:
            webbrowser.open("http://localhost:3000")
    except Exception:
        for child in reversed(children):
            if child.poll() is None:
                subprocess.run(
                    ["taskkill.exe", "/PID", str(child.pid), "/T", "/F"],
                    capture_output=True,
                    timeout=20,
                    creationflags=HIDDEN,
                )
        raise


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="TURAQ 本地一键启动/停止")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    LOGS.mkdir(parents=True, exist_ok=True)
    try:
        if os.name != "nt":
            raise RuntimeError("此一键启动入口用于 Windows。")
        with launch_lock():
            run(args.stop, args.no_browser)
    except Exception as exc:
        say(
            str(exc)
            if isinstance(exc, RuntimeError)
            else f"启动未完成（{type(exc).__name__}），请检查数据库连接、依赖及日志。"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
