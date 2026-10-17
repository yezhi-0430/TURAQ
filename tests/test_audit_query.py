from uuid import uuid4

import pytest

from app.audit.repository import list_tool_executions, save_tool_execution
from app.tools.executor import execute_tool


def test_query_isolates_runs_and_paginates_in_id_order():
    first, second = str(uuid4()), str(uuid4())
    record = execute_tool("unknown", "{}")
    ids = [save_tool_execution(first, record)]
    save_tool_execution(second, record)
    ids.append(save_tool_execution(first, record))
    ids.append(save_tool_execution(first, record))
    page1 = list_tool_executions(first, limit=1)
    page2 = list_tool_executions(first, after_id=page1[-1].id, limit=1)
    page3 = list_tool_executions(first, after_id=page2[-1].id, limit=1)
    assert [page1[0].id, page2[0].id, page3[0].id] == ids
    assert list_tool_executions(first, after_id=page3[-1].id) == []
    assert [item.id for item in list_tool_executions(first)] == ids
    assert len(list_tool_executions(second)) == 1
    assert list_tool_executions(str(uuid4())) == []
    assert page1[0].model_dump(mode="json")["error"]["kind"] == "unknown_tool"
    assert page1[0].run_id == first


@pytest.mark.parametrize("limit", [0, -1, 101, True, 1.5, "1", None])
def test_invalid_limit_rejected_before_connection(limit):
    def no_session():
        pytest.fail("invalid query must not connect")

    with pytest.raises(ValueError, match="limit"):
        list_tool_executions("run", limit=limit, session_factory=no_session)


@pytest.mark.parametrize("after_id", [-1, True, 1.5, "1", None])
def test_invalid_cursor_rejected_before_connection(after_id):
    def no_session():
        pytest.fail("invalid query must not connect")

    with pytest.raises(ValueError, match="after_id"):
        list_tool_executions("run", after_id=after_id, session_factory=no_session)
