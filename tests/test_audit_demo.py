import json

import httpx

from app import audit_demo
from app.audit.repository import list_tool_executions


def test_demo_uses_fake_model_test_database_and_queries_saved_records(monkeypatch, capsys):
    monkeypatch.setenv("MODEL_PROVIDER", "qwen")

    def no_http(*args, **kwargs):
        raise AssertionError("demo must not request a real model")

    monkeypatch.setattr(httpx.Client, "send", no_http)
    original_engine = audit_demo.create_engine
    selected_databases = []

    def check_engine(url):
        selected_databases.append(url.database)
        return original_engine(url)

    monkeypatch.setattr(audit_demo, "create_engine", check_engine)
    # Even a different environment database must not receive demo writes.
    monkeypatch.setenv("DATABASE_NAME", "must_not_connect_here")
    audit_demo.main()
    first = json.loads(capsys.readouterr().out)
    assert selected_databases == ["a_share_risk_agent_test"]
    assert first["database"] == "a_share_risk_agent_test"
    assert first["loop"]["status"] == "completed"
    assert first["loop"]["rounds"] == 2
    records = first["stored_records"]
    assert len(records) == 2
    assert [row["status"] for row in records] == ["success", "error"]
    assert records[0]["result"] == {"change_percent": "-10.0000"}
    assert records[1]["error"]["kind"] == "invalid_arguments"
    assert all(row["run_id"] == first["loop"]["run_id"] for row in records)
    assert [
        item.model_dump(mode="json") for item in list_tool_executions(first["loop"]["run_id"])
    ] == records
    audit_demo.main()
    second = json.loads(capsys.readouterr().out)
    assert second["loop"]["run_id"] != first["loop"]["run_id"]
    assert len(list_tool_executions(first["loop"]["run_id"])) == 2
