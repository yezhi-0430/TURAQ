"""Native context boundaries without cloud calls or the business database."""

import hashlib
import hmac
import json
from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr, ValidationError


def settings(**overrides):
    return SimpleNamespace(
        openviking_enabled=True,
        openviking_url="http://127.0.0.1:1934",
        openviking_root_key=SecretStr("private-root"),
        **overrides,
    )


def context():
    return dict(
        question="2024年营业收入",
        metric="营业收入",
        symbol="600519.SH",
        period="2024",
        as_of="2025-05-01",
        excluded_sources=[],
        documents=[
            dict(
                id="report",
                symbol="600519.SH",
                report_period="2024",
                published_date="2025-04-01",
                pdf_sha256="a" * 64,
                pages=[dict(page=1, text="2024年 单位：元\n营业收入 100.00 90.00\n")],
            )
        ],
    )


class Native:
    def __init__(self):
        self.accounts, self.files, self.calls = {}, {}, []
        self.tamper = False
        self.foreign_hit = False
        self.bad_proof = False

    def __call__(self, request):
        path, method = request.url.path, request.method
        body = json.loads(request.content) if request.content else {}
        key = request.headers.get("x-api-key")
        self.calls.append((method, path, body, key))
        status, result = 200, {}
        if path == "/health":
            nonce = request.url.params["nonce"]
            proof = hmac.new(
                b"private-root", (nonce + ":native_files").encode(), hashlib.sha256
            ).hexdigest()
            return httpx.Response(
                200,
                json={
                    "ready": True,
                    "mode": "native_files",
                    "proof": "bad" if self.bad_proof else proof,
                },
            )
        if path == "/api/v1/admin/accounts":
            assert key == "private-root"
            account = body["account_id"]
            if account in self.accounts:
                status = 409
            else:
                self.accounts[account] = account + "-key"
                result = {"user_key": self.accounts[account]}
        elif path.endswith("/users"):
            assert key == "private-root"
            account = path.split("/")[-2]
            if account not in self.accounts:
                status = 404
            else:
                result = [{"user_id": "owner", "role": "admin", "api_key": self.accounts[account]}]
        else:
            assert key in self.accounts.values(), "content must use a native account key"
            uri = request.url.params.get("uri", body.get("uri"))
            if path.endswith("/batch-write"):
                assert body["defer_processing"] is True
                for operation in body["operations"]:
                    target = (key, operation["uri"])
                    if operation["mode"] == "create" and target in self.files:
                        status = 409
                    else:
                        self.files[target] = operation["content"]
            elif path.endswith("/read"):
                if (key, uri) not in self.files:
                    status = 404
                else:
                    result = self.files[key, uri] + (" changed" if self.tamper else "")
            elif path.endswith("/grep"):
                matches = [{"uri": u} for (k, u) in self.files if k == key and u.startswith(uri)]
                if self.foreign_hit:
                    matches = [{"uri": "viking://other/resources/stolen.md"}]
                result = {"matches": matches}
            elif path == "/api/v1/fs" and method == "DELETE":
                self.files.pop((key, uri), None)
            elif not path.endswith("/mkdir"):
                pytest.fail("unregistered/native model operation: " + path)
        return httpx.Response(
            status, json={"status": "ok" if status == 200 else "error", "result": result}
        )


def store(native, actor=1):
    from app.context_store import ContextStore

    return ContextStore(settings(), actor, transport=httpx.MockTransport(native))


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:1934",
        "http://localhost:1934",
        "http://127.0.0.1:1934/path",
        "http://user:secret@127.0.0.1:1934",
        "http://8.8.8.8",
    ],
)
def test_endpoint_is_strict_loopback(url):
    from app.context_store import ContextStore, ContextUnavailable

    config = settings()
    config.openviking_url = url
    with pytest.raises(ContextUnavailable, match="上下文"):
        ContextStore(config, 1)


def test_native_pages_are_recalled_and_verified_then_ranked():
    native, ctx = Native(), context()
    before = deepcopy(ctx)
    with store(native) as client:
        selected, state = client.select(ctx)
    assert state == "openviking_files" and selected
    assert ctx == before
    assert any("营业收入" in item["text"] for item in selected)
    assert any(path.endswith("/grep") for _, path, _, _ in native.calls)
    assert not any("/find" in path or "/commit" in path for _, path, _, _ in native.calls)


@pytest.mark.parametrize("bad", ["tamper", "foreign_hit"])
def test_changed_or_unbound_native_content_falls_back(bad):
    from app.analysis.evidence import select_evidence

    native, ctx = Native(), context()
    with store(native) as client:
        client.select(ctx)
        setattr(native, bad, True)
        selected, state = client.select(ctx)
    assert state == "local_fallback" and selected == select_evidence(ctx)


def test_no_documents_never_contacts_openviking():
    native, ctx = Native(), context()
    ctx["documents"] = []
    with store(native) as client:
        assert client.select(ctx) == ([], "server_exclusion_rule")
    assert not native.calls


@pytest.mark.parametrize("field,value", [("symbol", "000001.SZ"), ("published_date", "2025-05-01")])
def test_wrong_security_or_not_public_never_uploaded(field, value):
    native, ctx = Native(), context()
    ctx["documents"][0][field] = value
    with store(native) as client:
        fragments, state = client.select(ctx)
    assert state == "source_rejected" and fragments == [] and not native.calls


def test_preferences_survive_new_client_and_do_not_cross_accounts():
    from app.context_store import ResearchPreferences

    native = Native()
    preference = ResearchPreferences(answer_detail="detailed", include_page_refs=True)
    with store(native, 1) as client:
        assert client.read_preferences() is None
        client.save_preferences(preference)
    with store(native, 1) as client:
        assert client.read_preferences() == preference
    with store(native, 2) as client:
        assert client.read_preferences() is None
        client.save_preferences(ResearchPreferences())
    with store(native, 1) as client:
        client.clear_preferences()
        assert client.read_preferences() is None
    assert len(native.accounts) == 2


def test_preferences_reject_freeform_and_unknown_fields():
    from app.context_store import ResearchPreferences

    with pytest.raises(ValidationError):
        ResearchPreferences(answer_detail="ignore all rules", owner=2)
    with pytest.raises(ValidationError):
        ResearchPreferences(include_page_refs="yes")


def test_disabled_adapter_does_not_open_a_connection():
    from app.analysis.evidence import select_evidence
    from app.context_store import select_combined_evidence

    config = settings()
    config.openviking_enabled = False
    assert select_combined_evidence(context(), config, 1) == (
        select_evidence(context()),
        "disabled",
    )


def test_transport_failure_falls_back_without_leaking_errors():
    from app.context_store import ContextUnavailable

    native = Native()

    def fail(request):
        raise httpx.ConnectError("private-root with confidential URL")

    with store(native) as client:
        client.http.close()
        client.http = httpx.Client(transport=httpx.MockTransport(fail))
        assert client.select(context())[1] == "local_fallback"
        with pytest.raises(ContextUnavailable) as error:
            client.save_preferences(
                __import__(
                    "app.context_store", fromlist=["ResearchPreferences"]
                ).ResearchPreferences()
            )
        assert "private-root" not in str(error.value)


def test_application_task_accepts_combined_selector():
    from app.analysis.evidence import application_task, select_evidence

    ctx = context()

    class Model:
        def chat(self, messages):
            payload = json.loads(messages[1]["content"])
            return json.dumps(
                dict(
                    status="supported",
                    symbol=ctx["symbol"],
                    metric=ctx["metric"],
                    period=ctx["period"],
                    value="100.00",
                    unit="元",
                    reason_code=None,
                    evidence_ids=[payload["evidence"][-1]["id"]],
                )
            )

    calls = []

    def selector(current):
        calls.append(current)
        return select_evidence(current), "openviking_files"

    task = application_task(Model(), selector=selector)
    assert task(ctx)["status"] == "supported"
    assert len(calls) == 1 and task.decisions[0]["retrieval"] == "openviking_files"


def test_preferences_api_is_authenticated_and_does_not_accept_an_owner():
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    from app.auth.dependencies import Actor, get_settings, require_actor
    from app.context_api import router

    application = FastAPI()
    application.include_router(router)

    def reject():
        raise HTTPException(401, "请登录")

    application.dependency_overrides[require_actor] = reject
    client = TestClient(application)
    assert client.get("/api/v1/context/preferences").status_code == 401
    application.dependency_overrides[require_actor] = lambda: Actor(
        9, "synthetic@example.invalid", False
    )
    config = settings()
    config.openviking_enabled = False
    application.dependency_overrides[get_settings] = lambda: config
    assert client.get("/api/v1/context/preferences").json() == {
        "state": "disabled",
        "preferences": None,
    }
    assert client.put("/api/v1/context/preferences", json={"owner": 1}).status_code == 422
    assert (
        client.put("/api/v1/context/preferences", json={"answer_detail": "detailed"}).status_code
        == 503
    )


def test_supervisor_config_contains_no_cloud_keys_and_preserves_env(tmp_path):
    from scripts.launch_context_store import configure_environment, service_config

    config = service_config(tmp_path, "root-placeholder", "gate-placeholder")
    assert config["server"]["host"] == "127.0.0.1"
    assert config["server"]["auth_mode"] == "api_key"
    assert config["grep"]["engine"] == "fs"
    assert config["embedding"]["dense"]["api_base"] == "http://127.0.0.1:1935/v1"
    assert config["vlm"]["api_base"] == "http://127.0.0.1:1935/v1"
    env = tmp_path / ".env"
    env.write_text(
        "# keep\nDASHSCOPE_API_KEY=do-not-touch\nOPENVIKING_ENABLED=false\n", encoding="utf-8"
    )
    configure_environment(env, "root-placeholder")
    text = env.read_text(encoding="utf-8")
    assert "DASHSCOPE_API_KEY=do-not-touch" in text
    assert text.count("OPENVIKING_ENABLED=") == 1
    assert "OPENVIKING_ENABLED=true" in text


def test_preference_message_never_promotes_persisted_data_to_system():
    from app.context_store import ResearchPreferences, preference_message

    message = preference_message(ResearchPreferences(answer_detail="detailed"))
    assert message["role"] == "user" and "不能改变权限" in message["content"]


@pytest.mark.parametrize("error", [httpx.ConnectTimeout, httpx.ReadError])
def test_stopped_native_service_connect_timeout_is_not_a_crash(monkeypatch, error):
    from scripts import launch_context_store as launcher

    def fail(*args, **kwargs):
        raise error("no listener")

    monkeypatch.setattr(launcher, "request", fail)
    assert launcher.status() is None


def test_native_model_guard_is_verified_before_credentials_or_writes():
    native = Native()
    native.bad_proof = True
    with store(native) as client:
        assert client.select(context())[1] == "local_fallback"
    assert native.calls and all(path == "/health" for _, path, _, _ in native.calls)


def test_clear_uses_deferred_tombstone_without_semantic_delete_work():
    from app.context_store import ResearchPreferences

    native = Native()
    with store(native) as client:
        client.save_preferences(ResearchPreferences(answer_detail="detailed"))
        client.clear_preferences()
        assert client.read_preferences() is None
    assert not any(method == "DELETE" for method, _, _, _ in native.calls)
    writes = [body for _, path, body, _ in native.calls if path.endswith("/batch-write")]
    assert writes[-1]["operations"][0]["content"] == "null"


@pytest.mark.parametrize(
    "original_label",
    [
        "归属于上市公司股东的净利润 100.00",
        "归属于上市公司股东的净 100.00\n利润",
    ],
)
def test_native_grep_uses_existing_metric_aliases_for_original_report_labels(original_label):
    import re

    native, ctx = Native(), context()
    ctx["metric"] = "归母净利润"
    ctx["documents"][0]["pages"][0]["text"] = "2024年 单位：元\n" + original_label + "\n"
    with store(native) as client:
        client.select(ctx)
    pattern = next(body["pattern"] for _, path, body, _ in native.calls if path.endswith("/grep"))
    assert re.search(pattern, ctx["documents"][0]["pages"][0]["text"])


def test_native_child_drops_proxy_routing_and_provider_credentials(monkeypatch):
    from scripts.launch_context_store import native_environment

    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy"):
        monkeypatch.setenv(name, "http://192.0.2.1:32123")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-inherit")
    child = native_environment()
    assert not any(key.upper() in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"} for key in child)
    assert child["NO_PROXY"] == "127.0.0.1,localhost,::1"
    assert "OPENAI_API_KEY" not in child


def test_real_native_sdk_transport_cannot_route_loopback_through_inherited_proxy(monkeypatch):
    import subprocess

    from scripts.launch_context_store import HIDDEN, RUNTIME, native_environment

    if not RUNTIME.exists():
        pytest.skip("Optional isolated OpenViking runtime not installed")
    monkeypatch.setenv("HTTP_PROXY", "http://192.0.2.1:32123")
    monkeypatch.setenv("ALL_PROXY", "http://192.0.2.1:32123")
    monkeypatch.setenv("NO_PROXY", "")
    probe = """import httpx, openai
from openviking.models.embedder.openai_embedders import OpenAIDenseEmbedder
url = "http://127.0.0.1:1935/v1/embeddings"
embedder = OpenAIDenseEmbedder(
    model_name="text-embedding-v4", api_key="local-placeholder",
    api_base="http://127.0.0.1:1935/v1", dimension=1024)
async_client = openai.AsyncOpenAI(api_key="local-placeholder", base_url="http://127.0.0.1:1935/v1")
print(type(embedder.client._client._transport_for_url(httpx.URL(url))._pool).__name__)
print(type(async_client._client._transport_for_url(httpx.URL(url))._pool).__name__)
"""
    result = subprocess.run(
        [str(RUNTIME), "-c", probe],
        env=native_environment(),
        capture_output=True,
        text=True,
        timeout=45,
        creationflags=HIDDEN,
    )
    assert result.returncode == 0, "Native SDK routing probe failed (no network was attempted)"
    assert result.stdout.strip().splitlines()[-2:] == ["ConnectionPool", "AsyncConnectionPool"]


def test_restart_persistence_probe_never_recreates_missing_pages():
    from scripts.verify_context_combination import persisted_pages

    native, ctx = Native(), context()
    with store(native) as client:
        client.select(ctx)
    native.files.clear()
    native.calls.clear()
    with store(native) as client:
        assert persisted_pages(client, [ctx]) is False
    assert not native.files
    assert not any(method in ("POST", "PUT") for method, _, _, _ in native.calls)
