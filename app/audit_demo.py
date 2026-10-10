"""Use a fake model and the dedicated test database to save and query an audit run."""

import json
from collections.abc import Mapping, Sequence
from functools import partial

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent_loop import run_agent_loop
from app.audit.repository import list_tool_executions, save_tool_execution
from app.config import Settings
from app.database import ToolAuditRecord
from app.llm_client import FakeModelClient
from app.llm_types import ToolReply

DEMO_DATABASE = "a_share_risk_agent_test"


class AuditDemoClient(FakeModelClient):
    """Preset requests; report the actual success and failure results received."""

    def chat_with_tools(
        self, messages: Sequence[Mapping[str, object]], tools: list[dict[str, object]]
    ) -> ToolReply:
        results = [json.loads(str(item["content"])) for item in messages if item["role"] == "tool"]
        if results:
            descriptions = [
                f"计算结果：{item['result']['change_percent']}%"
                if item["status"] == "success"
                else f"拒绝原因：{item['error']['message']}"
                for item in results
            ]
            return ToolReply(content="假模型演示；" + "；".join(descriptions))
        return ToolReply.model_validate(
            {
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": "calculate_change",
                            "arguments": json.dumps(
                                {"previous_close": previous, "current_close": "9"}
                            ),
                        },
                    }
                    for call_id, previous in [("day12_success", "10"), ("day12_rejected", "0")]
                ]
            }
        )


def main() -> None:
    settings = Settings().model_copy(update={"database_name": DEMO_DATABASE})
    demo_engine = create_engine(settings.database_url)
    try:
        ToolAuditRecord.__table__.create(demo_engine, checkfirst=True)
        factory = sessionmaker(bind=demo_engine)
        result = run_agent_loop(
            AuditDemoClient(reply="审计演示"),
            [{"role": "user", "content": "虚构数据：分别计算10到9、0到9的涨跌幅。"}],
            audit_writer=partial(save_tool_execution, session_factory=factory),
        )
        stored = []
        after_id = 0
        while page := list_tool_executions(
            result.run_id, after_id=after_id, limit=1, session_factory=factory
        ):
            stored.extend(item.model_dump(mode="json") for item in page)
            after_id = page[-1].id
        print(
            json.dumps(
                {
                    "database": DEMO_DATABASE,
                    "model": "fake",
                    "loop": result.model_dump(mode="json"),
                    "stored_records": stored,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        demo_engine.dispose()


if __name__ == "__main__":
    main()
