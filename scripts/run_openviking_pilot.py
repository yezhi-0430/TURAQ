"""Run the isolated public-report pilot. No provider calls without --live."""

import argparse
import json
import os
import re
import secrets
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.openviking_gateway import ModelGate, serve_gate
from app.openviking_pilot import (
    PilotClient,
    allowed_resources,
    bind_content,
    lexical_find,
    prepare_resources,
    read_memory,
    resolve_hits,
    retrieval_coverage,
    verify_content,
)
from app.report_evidence_eval import load_corpus

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".local-backups/openviking-pilot-2026-10-24"
OUTPUT = ROOT / "evaluations/turaq/openviking/results/pilot-2026-10-24.json"


def save(report):
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def wait_task(client, result, *, seconds=120):
    task_id = result.get("task_id")
    if not task_id:
        return result
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        task = client.call("GET", "/api/v1/tasks/" + task_id)
        if task.get("status") == "completed":
            return task
        if task.get("status") in {"failed", "cancelled"}:
            raise RuntimeError("OpenViking background task " + task["status"])
        time.sleep(1)
    raise TimeoutError("OpenViking background task not completed")


def flatten_hits(result):
    return [hit for kind in ("resources", "memories", "skills") for hit in result.get(kind, [])]


def find(client, query, uri, *, limit=3):
    return flatten_hits(
        client.call(
            "POST",
            "/api/v1/search/find",
            json=dict(
                query=query,
                target_uri=uri,
                limit=limit,
                level=2,
            ),
        )
    )


def live_retrieval(url, key, resources, corpus, bindings):
    rows = []
    # A new HTTP client has no conversation history or cached retrieval state.
    with PilotClient(url, key) as client:
        for case in corpus["cases"]:
            allowed = allowed_resources(
                resources, owner="pilot-a", symbol=case["symbol"], as_of=case["as_of"]
            )
            targets = [
                uri for uri, identity in bindings.items() if identity in {r["id"] for r in allowed}
            ]
            row = dict(id=case["id"], evidence_retrieved=None, error=None, found=[])
            start = time.monotonic()
            try:
                hits = find(client, case["question"], targets) if targets else []
                found = resolve_hits(hits, bindings, allowed)
                verified = []
                for resource in found:
                    content = client.call(
                        "GET", "/api/v1/content/read", params={"uri": resource["backend_uri"]}
                    )
                    if verify_content(resource, content):
                        verified.append(resource)
                found = verified
                row.update(
                    found=[dict(document_id=r["document_id"], page=r["page"]) for r in found],
                    evidence_retrieved=retrieval_coverage(corpus["gold"][case["id"]], found),
                )
            except Exception as exc:
                row["error"] = type(exc).__name__
                if corpus["gold"][case["id"]]["status"] == "supported":
                    row["evidence_retrieved"] = False
            row["elapsed_seconds"] = round(time.monotonic() - start, 3)
            rows.append(row)
    return rows


def run_live(
    report, corpus, resources, *, resume=None, memory_only=False, runner=None, budget=None
):
    from app.config import Settings

    settings = Settings()
    if settings.model_provider != "qwen" or not settings.dashscope_api_key:
        raise ValueError("existing Qwen configuration is required")
    upstream = settings.model_base_url.rstrip("/")
    if (
        urlsplit(upstream).scheme != "https"
        or urlsplit(upstream).hostname != "dashscope.aliyuncs.com"
    ):
        raise ValueError("pilot only permits the existing DashScope HTTPS endpoint")
    provider_key = settings.dashscope_api_key.get_secret_value()
    WORK.mkdir(parents=True, exist_ok=False)
    runtime = ROOT / ".local-backups/openviking-runtime/Scripts/python.exe"
    if not runtime.is_file():
        raise RuntimeError("install the isolated OpenViking 0.5.2 runtime first")
    storage = WORK / "storage"
    root_key = secrets.token_urlsafe(32)
    if resume:
        prior = ROOT / ".local-backups" / ("openviking-pilot-2026-10-24-" + resume)
        previous_config = json.loads((prior / "ov.conf").read_text(encoding="utf-8"))
        storage = Path(previous_config["storage"]["workspace"]).resolve()
        if not storage.is_relative_to((ROOT / ".local-backups").resolve()):
            raise ValueError("resume workspace escapes experiment directory")
        root_key = previous_config["server"]["root_api_key"]
        report["resumed_workspace"] = prior.name
    base = "http://127.0.0.1:1933"
    # Refuse to attach to or replace an unrelated service.
    import socket

    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 1933)) == 0:
            raise RuntimeError("port 1933 already in use")
    child_env = {
        k: v
        for k, v in os.environ.items()
        if k.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "COMSPEC"}
    }
    child_env.update(
        PYTHONIOENCODING="utf-8",
        PYTHONUTF8="1",
        LITELLM_LOCAL_MODEL_COST_MAP="True",
        DO_NOT_TRACK="1",
        HOME=str(WORK),
        USERPROFILE=str(WORK),
    )
    with httpx.Client(trust_env=False, follow_redirects=False) as provider:

        def send(path, payload, timeout):
            response = provider.post(
                upstream + path,
                json=payload,
                timeout=timeout,
                headers={"Authorization": "Bearer " + provider_key},
            )
            return response.status_code, response.json()

        cache_path = ROOT / ".local-backups/openviking-embedding-cache.json"
        cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

        def save_cache(data):
            cache_path.write_text(json.dumps(data), encoding="utf-8")

        limits = budget or dict(max_calls=31 if memory_only else 60)
        gate = ModelGate(
            send,
            chat_model=settings.model_name,
            embedding_cache=cache,
            save_cache=save_cache,
            **limits,
        )
        with serve_gate(gate) as (gateway, gateway_key):
            config = dict(
                storage=dict(workspace=str(storage)),
                server=dict(
                    host="127.0.0.1",
                    port=1933,
                    root_api_key=root_key,
                    auth_mode="api_key",
                    cors_origins=[],
                ),
                embedding=dict(
                    max_concurrent=1,
                    max_retries=0,
                    dense=dict(
                        provider="openai",
                        model="text-embedding-v4",
                        api_base=gateway,
                        api_key=gateway_key,
                        dimension=1024,
                        batch_size=4,
                        input="text",
                        encoding_format="float",
                    ),
                ),
                vlm=dict(
                    provider="openai",
                    model=settings.model_name,
                    api_base=gateway,
                    api_key=gateway_key,
                    max_tokens=1024,
                    max_retries=0,
                    timeout=35,
                    max_concurrent=1,
                ),
                default_search_mode="fast",
                enable_watch_scheduler=False,
                output_language_override="zh-CN",
                memory=dict(session_skill_extraction_enabled=False),
                telemetry=dict(tracer=dict(enabled=False)),
            )
            config_path = WORK / "ov.conf"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            child_env["OPENVIKING_CONFIG_FILE"] = str(config_path)
            process = None
            try:
                with (WORK / "server.log").open("w", encoding="utf-8") as log:
                    process = subprocess.Popen(
                        [
                            str(runtime),
                            "-c",
                            "from openviking_cli.server_bootstrap import main; main()",
                            "--config",
                            str(config_path),
                            "--host",
                            "127.0.0.1",
                            "--port",
                            "1933",
                        ],
                        cwd=WORK,
                        env=child_env,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    deadline = time.monotonic() + 300
                    while time.monotonic() < deadline:
                        if process.poll() is not None:
                            raise RuntimeError(
                                "OpenViking startup failed; inspect local server.log"
                            )
                        try:
                            response = httpx.get(base + "/ready", timeout=2, trust_env=False)
                            if response.status_code == 200:
                                report["service_ready"] = True
                                break
                        except httpx.HTTPError:
                            pass
                        time.sleep(1)
                    else:
                        raise TimeoutError("OpenViking readiness deadline")
                    print(
                        "OpenViking ready on loopback; creating isolated test identities",
                        flush=True,
                    )
                    save(report)
                    extra = dict(gate=gate) if runner else {}
                    (runner or exercise)(
                        base,
                        root_key,
                        resources,
                        corpus,
                        report,
                        resume=bool(resume),
                        memory_only=memory_only,
                        **extra,
                    )
            finally:
                if process is not None and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                report["usage"] = gate.snapshot()
                report["services_stopped_after_experiment"] = True
                save(report)


def exercise(base, root_key, resources, corpus, report, *, resume=False, memory_only=False):
    with PilotClient(base, root_key) as admin:
        if not resume:
            admin.call(
                "POST",
                "/api/v1/admin/accounts",
                json=dict(account_id="pilotlab", admin_user_id="pilot-admin"),
            )
        keys = {}
        for user_id in ("pilot-a", "pilot-b"):
            path = "/api/v1/admin/accounts/pilotlab/users"
            if resume:
                path += "/" + user_id + "/key"
            keys[user_id] = admin.call("POST", path, json={} if resume else dict(user_id=user_id))[
                "user_key"
            ]
        key_a, key_b = keys["pilot-a"], keys["pilot-b"]
    if memory_only:
        with PilotClient(base, key_a) as client:
            new_session = client.call("POST", "/api/v1/sessions", json={})
            report["memory"] = dict(
                **read_memory(client),
                new_session_created=bool(new_session),
                persisted_from_previous_run=True,
                synthetic_only=True,
            )
            report["state"] = "completed"
            save(report)
        return
    bindings = {}
    imported = []
    with PilotClient(base, key_a) as client:
        for index, resource in enumerate(resources):
            target = f"viking://~/resources/turaq-pilot-{resource['id'][:16]}"
            content = (
                f"# {resource['symbol']} {resource['report_period']} "
                f"PDF page {resource['page']}\n\n"
            )
            content += resource["text"]
            uploaded = client.call(
                "POST",
                "/api/v1/resources/temp_upload",
                files={"file": ("page.md", content.encode(), "text/markdown")},
            )
            result = client.call(
                "POST",
                "/api/v1/resources",
                json=dict(
                    temp_file_id=uploaded["temp_file_id"],
                    to=target,
                    create_parent=True,
                    wait=True,
                    processing_mode="vectors_only",
                ),
            )
            wait_task(client, result)
            root_uri = result.get("root_uri")
            if not root_uri:
                raise RuntimeError("import did not return a stable root URI")
            files = client.call("GET", "/api/v1/fs/ls", params={"uri": root_uri, "recursive": True})
            texts = [
                (x["uri"], client.call("GET", "/api/v1/content/read", params={"uri": x["uri"]}))
                for x in files
                if not x.get("isDir") and not x.get("name", "").startswith(".")
            ]
            preserved = [(uri, text) for uri, text in texts if verify_content(resource, text)]
            if len(preserved) != 1:
                raise RuntimeError("imported body no longer preserves the frozen page text")
            backend_uri, backend_body = preserved[0]
            bound = bind_content(resource, backend_body)
            bound["backend_uri"] = backend_uri
            resources[index] = bound
            bindings[root_uri] = resource["id"]
            imported.append(
                dict(
                    id=resource["id"],
                    document_id=resource["document_id"],
                    page=resource["page"],
                    uri=root_uri,
                )
            )
            report["imports"] = imported
            save(report)
            print(f"Imported {resource['document_id']} page {resource['page']}", flush=True)
    report["openviking_retrieval"] = live_retrieval(base, key_a, resources, corpus, bindings)
    save(report)
    print("Retrieval completed with a fresh client", flush=True)
    lifecycle(base, key_a, key_b, resources, bindings, report)


def lifecycle(base, key_a, key_b, resources, bindings, report):
    preference = "研究偏好：每次阅读财报先核对证券代码、报告期、原文页码，金额保持原表单位。"
    with PilotClient(base, key_a) as a, PilotClient(base, key_b) as b:
        session = a.call(
            "POST",
            "/api/v1/sessions",
            json=dict(
                memory_policy=dict(
                    memory_types=["preferences"], working_memory=dict(enabled=False)
                ),
            ),
        )
        session_id = session["session_id"]
        a.call(
            "POST",
            f"/api/v1/sessions/{session_id}/messages",
            json=dict(role="user", content=preference),
        )
        committed = a.call("POST", f"/api/v1/sessions/{session_id}/commit", json={})
        task = wait_task(a, committed, seconds=150)
        new_session = a.call("POST", "/api/v1/sessions", json={})
        report["memory"] = dict(
            commit_task_status=task.get("status"),
            archive_accepted=True,
            new_session_created=new_session["session_id"] != session_id,
            **read_memory(a),
            synthetic_only=True,
        )
        target = next(iter(bindings))
        original = next(r for r in resources if r["id"] == bindings[target])
        file_uri = original["backend_uri"]
        read_status = b.http.get("/api/v1/content/read", params={"uri": file_uri}).status_code
        other_response = b.http.post(
            "/api/v1/search/find",
            json=dict(
                query="贵州茅台 营业收入",
                target_uri=target,
                limit=3,
                level=2,
            ),
        )
        other_hits = (
            flatten_hits(other_response.json().get("result", {}))
            if other_response.status_code == 200
            else []
        )
        report["native_isolation"] = dict(
            other_user_direct_read_status=read_status,
            other_user_retrieved=len(other_hits),
            other_user_search_status=other_response.status_code,
        )
        a.call(
            "POST",
            "/api/v1/content/write",
            json=dict(
                uri=file_uri,
                content="合成更正测试：原页面已撤回，请重新取得有效版本。",
                mode="replace",
                wait=True,
                processing_mode="vectors_only",
            ),
        )
        updated = a.call("GET", "/api/v1/content/read", params={"uri": file_uri})
        report["correction"] = dict(
            synthetic_only=True,
            application_rejects_changed_body=not verify_content(original, updated),
        )
        # These are disposable resources created by this experiment only.
        a.call("DELETE", "/api/v1/fs", params={"uri": target, "recursive": True, "wait": True})
        deleted_id = bindings[target]
        remaining = [dict(r, active=False) if r["id"] == deleted_id else r for r in resources]
        stale_status = a.http.get("/api/v1/content/read", params={"uri": file_uri}).status_code
        report["deletion"] = dict(
            read_status=stale_status,
            application_rejects_stale_uri=not resolve_hits(
                [dict(uri=file_uri)], bindings, remaining
            ),
        )
        report["state"] = "completed"
        save(report)


def main():
    global WORK, OUTPUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--resume", default="")
    parser.add_argument("--memory-only", action="store_true")
    args = parser.parse_args()
    if args.resume and not re.fullmatch(r"[a-z0-9-]{1,32}", args.resume):
        raise SystemExit("invalid resume id")
    if args.run_id:
        if not re.fullmatch(r"[a-z0-9-]{1,32}", args.run_id):
            raise SystemExit("invalid run id")
        WORK = WORK.with_name(WORK.name + "-" + args.run_id)
        OUTPUT = OUTPUT.with_name(OUTPUT.stem + "-" + args.run_id + OUTPUT.suffix)
    if OUTPUT.exists():
        raise SystemExit("Result already exists; preserve it before starting another experiment")
    corpus = load_corpus()
    resources = prepare_resources(corpus, owner="pilot-a")
    report = dict(
        state="offline",
        openviking_version="0.5.2",
        resource_pages=len(resources),
        service_ready=False,
        model_calls_authorized=args.live,
        metric="gold evidence-page coverage@3; not answer accuracy",
        comparison="independent lexical baseline; not production Chroma/BGE",
        retrieval_eligible=sum(g["status"] == "supported" for g in corpus["gold"].values()),
        lexical_baseline=[],
    )
    for case in corpus["cases"]:
        allowed = allowed_resources(
            resources, owner="pilot-a", symbol=case["symbol"], as_of=case["as_of"]
        )
        found = lexical_find(case["question"], allowed)
        report["lexical_baseline"].append(
            dict(
                id=case["id"],
                evidence_retrieved=retrieval_coverage(corpus["gold"][case["id"]], found),
            )
        )
    save(report)
    if args.live:
        try:
            run_live(report, corpus, resources, resume=args.resume, memory_only=args.memory_only)
        except Exception as exc:
            report.update(state="incomplete", error_type=type(exc).__name__)
            save(report)
            print(
                "Pilot incomplete: " + type(exc).__name__ + "; see local diagnostic log", flush=True
            )
            raise SystemExit(1) from None
    print(
        json.dumps({k: report[k] for k in ("state", "resource_pages", "retrieval_eligible")}),
        flush=True,
    )


if __name__ == "__main__":
    main()
