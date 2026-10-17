"""Demonstrate a full tool loop with fictitious prices, offline by default."""

import argparse
import json
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path

import httpx

from app.agent_loop import run_agent_loop
from app.config import Settings
from app.llm_client import FakeModelClient, create_model_client
from app.llm_types import ToolReply


class OfflineDemoClient(FakeModelClient):
    """Preset tool selection followed by a deterministic answer from its result."""

    def __init__(self) -> None:
        super().__init__(reply="离线演示")

    def chat_with_tools(
        self, messages: Sequence[Mapping[str, object]], tools: list[dict[str, object]]
    ) -> ToolReply:
        if messages[-1]["role"] == "tool":
            payload = json.loads(str(messages[-1]["content"]))
            if payload["status"] == "error":
                return ToolReply(content="离线演示：工具执行失败，无法给出计算结果。")
            change = payload["result"]["change_percent"]
            return ToolReply(content=f"离线演示：工具返回涨跌幅 {change}%。")
        return ToolReply.model_validate(
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "offline_day11_calc",
                        "type": "function",
                        "function": {
                            "name": "calculate_change",
                            "arguments": '{"previous_close": "10", "current_close": "9"}',
                        },
                    }
                ],
            }
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Day 11 完整工具循环演示")
    parser.add_argument(
        "--provider",
        choices=("fake", "qwen"),
        default="fake",
        help="默认 fake 离线演示；qwen 使用本地配置发出真实模型请求",
    )
    args = parser.parse_args(argv)
    settings = Settings().model_copy(update={"model_provider": args.provider})
    messages = [
        {
            "role": "system",
            "content": (
                "使用用户提供的虚构价格选择计算工具。涨跌幅必须由计算工具计算。"
                "收到工具结果后给出简短中文回答。这里不需要查询股票资料或行情。"
            ),
        },
        {
            "role": "user",
            "content": "虚构数据：昨日收盘价 10 元，今日收盘价 9 元，请计算涨跌幅。",
        },
    ]
    label = (
        "离线完整循环演示（工具选择预设，回答由程序生成）"
        if args.provider == "fake"
        else f"千问完整循环演示（{settings.model_name}）"
    )
    log_path = Path("data/private/day11-tool-calls.jsonl").resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("app.tools.executor")
    previous_level, previous_propagate = logger.level, logger.propagate
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)
    try:
        with httpx.Client() as http_client:
            client = (
                OfflineDemoClient()
                if args.provider == "fake"
                else create_model_client(settings, http_client)
            )
            result = run_agent_loop(client, messages)
        print(label)
        print(result.model_dump_json(indent=2))
        print(f"Log: {log_path}")
    finally:
        logger.removeHandler(handler)
        handler.close()
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate


if __name__ == "__main__":
    main()
