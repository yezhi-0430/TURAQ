"""Owned loopback OpenViking supervisor; every model request is rejected locally."""

import argparse
import hashlib
import hmac
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".local-backups/context-store"
RUNTIME = ROOT / ".local-backups/openviking-runtime/Scripts/python.exe"
CONFIG = WORK / "ov.conf"
IDENTITY = hashlib.sha256(str(ROOT.resolve()).encode()).hexdigest()
HIDDEN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def service_config(work, root_key, gateway_key):
    endpoint = "http://127.0.0.1:1935/v1"
    return dict(
        storage=dict(workspace=str(work / "storage")),
        server=dict(
            host="127.0.0.1", port=1934, root_api_key=root_key, auth_mode="api_key", cors_origins=[]
        ),
        embedding=dict(
            max_concurrent=1,
            max_retries=0,
            dense=dict(
                provider="openai",
                model="text-embedding-v4",
                api_base=endpoint,
                api_key=gateway_key,
                dimension=1024,
                batch_size=1,
            ),
        ),
        vlm=dict(
            provider="openai",
            model="disabled",
            api_base=endpoint,
            api_key=gateway_key,
            max_tokens=1,
            max_retries=0,
            timeout=2,
            max_concurrent=1,
        ),
        grep=dict(engine="fs"),
        default_search_mode="fast",
        enable_watch_scheduler=False,
        memory=dict(session_skill_extraction_enabled=False),
        telemetry=dict(tracer=dict(enabled=False)),
        output_language_override="zh-CN",
    )


def configure_environment(path, root_key):
    replacements = {
        "OPENVIKING_ENABLED": "true",
        "OPENVIKING_URL": "http://127.0.0.1:1934",
        "OPENVIKING_ROOT_KEY": root_key,
    }
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    result = [line for line in lines if line.split("=", 1)[0].strip() not in replacements]
    result.extend(f"{key}={value}" for key, value in replacements.items())
    temporary = path.with_name(path.name + ".context-tmp")
    temporary.write_text("\n".join(result) + "\n", encoding="utf-8")
    temporary.replace(path)


def request(method, path, **kwargs):
    with httpx.Client(trust_env=False, timeout=2, follow_redirects=False) as client:
        return client.request(method, "http://127.0.0.1:1935" + path, **kwargs)


def status():
    try:
        response = request("GET", "/health")
        data = response.json()
        if response.status_code != 200 or data.get("identity") != IDENTITY:
            raise RuntimeError("上下文端口由其他服务占用")
        return data
    except httpx.HTTPError:
        return None


def free_port(port):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", port))


def native_environment():
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().endswith("_PROXY")
        and key.upper() not in {"DASHSCOPE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
    }
    # Also suppress Windows system proxy fallback for the local-only SDK clients.
    environment.update(
        NO_PROXY="127.0.0.1,localhost,::1", OPENVIKING_CONFIG_FILE=str(CONFIG), PYTHONUTF8="1"
    )
    return environment


def serve():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    safe = service_config(
        WORK, config["server"]["root_api_key"], config["embedding"]["dense"]["api_key"]
    )
    if config != safe:
        raise RuntimeError("专用服务配置与文件模式不一致，拒绝启动")
    control_key = (WORK / "control.key").read_text(encoding="utf-8")
    stop = threading.Event()
    denied = 0
    child = None

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status_code, data):
            content = json.dumps(data).encode()
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(content)
            self.close_connection = True

        def do_GET(self):
            target = urlsplit(self.path)
            if target.path != "/health":
                self.reply(404, {"error": "not_found"})
                return
            ready = False
            if child is not None and child.poll() is None:
                try:
                    with httpx.Client(trust_env=False, timeout=1) as client:
                        ready = client.get("http://127.0.0.1:1934/ready").status_code == 200
                except httpx.HTTPError:
                    pass
            data = dict(
                identity=IDENTITY,
                ready=ready,
                provider_calls=0,
                rejected_model_requests=denied,
                mode="native_files",
            )
            nonce = parse_qs(target.query).get("nonce", [""])[0]
            if nonce and len(nonce) <= 64 and ready:
                data["proof"] = hmac.new(
                    config["server"]["root_api_key"].encode(),
                    (nonce + ":native_files").encode(),
                    hashlib.sha256,
                ).hexdigest()
            self.reply(200, data)

        def do_POST(self):
            nonlocal denied
            if self.path == "/shutdown" and hmac.compare_digest(
                self.headers.get("X-Control-Key", ""), control_key
            ):
                self.reply(200, {"state": "stopping"})
                stop.set()
            else:
                denied += 1
                self.reply(403, {"error": "Model calls are disabled in native file mode"})

    free_port(1934)
    server = ThreadingHTTPServer(("127.0.0.1", 1935), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    environment = native_environment()
    try:
        with (WORK / "native.log").open("a", encoding="utf-8") as log:
            child = subprocess.Popen(
                [
                    str(RUNTIME),
                    "-c",
                    "from openviking_cli.server_bootstrap import main; main()",
                    "--config",
                    str(CONFIG),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "1934",
                ],
                cwd=WORK,
                env=environment,
                stdout=log,
                stderr=log,
                stdin=subprocess.DEVNULL,
                creationflags=HIDDEN,
            )
            while not stop.wait(0.25):
                if child.poll() is not None:
                    break
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        server.shutdown()
        server.server_close()


def start():
    current = status()
    if current:
        if not current["ready"]:
            raise RuntimeError("上下文服务尚未就绪")
    else:
        if not RUNTIME.exists():
            raise RuntimeError("缺少隔离安装的 OpenViking 0.5.2")
        version = subprocess.run(
            [
                str(RUNTIME),
                "-c",
                "from importlib.metadata import version; print(version('openviking'))",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=HIDDEN,
        )
        if version.returncode or version.stdout.strip() != "0.5.2":
            raise RuntimeError("上下文服务需要 OpenViking 0.5.2")
        free_port(1934)
        free_port(1935)
        WORK.mkdir(parents=True, exist_ok=True)
        if not CONFIG.exists():
            CONFIG.write_text(
                json.dumps(
                    service_config(WORK, secrets.token_urlsafe(32), secrets.token_urlsafe(32))
                ),
                encoding="utf-8",
            )
        if not (WORK / "control.key").exists():
            (WORK / "control.key").write_text(secrets.token_urlsafe(32), encoding="utf-8")
        with (WORK / "supervisor.log").open("a", encoding="utf-8") as log:
            subprocess.Popen(
                [sys.executable, "-X", "utf8", str(Path(__file__).resolve()), "--serve"],
                cwd=ROOT,
                stdout=log,
                stderr=log,
                stdin=subprocess.DEVNULL,
                creationflags=HIDDEN,
            )
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            current = status()
            if current and current["ready"]:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("上下文服务启动超时，请检查本地日志")
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    env_path = ROOT / ".env"
    if env_path.exists():
        backup = WORK / f"env-before-{time.time_ns()}.backup"
        backup.write_bytes(env_path.read_bytes())
    configure_environment(env_path, config["server"]["root_api_key"])
    print("上下文服务已启动并启用：仅本机文件模式，云模型调用关闭。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.serve:
        serve()
    elif args.status:
        print(json.dumps(status() or {"ready": False}, ensure_ascii=False))
    elif args.stop:
        if status():
            token = (WORK / "control.key").read_text(encoding="utf-8")
            request("POST", "/shutdown", headers={"X-Control-Key": token}).raise_for_status()
        print("上下文服务已请求停止；应用会自动回退。")
    else:
        start()


if __name__ == "__main__":
    main()
