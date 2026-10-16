import pytest
from pydantic import ValidationError

from app.llm_client import FakeModelClient
from app.risk_summary import (
    RiskSummary,
    RiskSummaryParseError,
    generate_risk_summary,
    parse_risk_summary,
)


def test_accepts_valid_risk_summary() -> None:
    data = {
        "facts": ["今日收盘价9元，昨日10元"],
        "inferences": [],
        "unknowns": ["缺少成交量和公司公告"],
        "risk_level": "unknown",
        "sources": ["用户提供的数据"],
    }

    summary = RiskSummary.model_validate(data)

    assert summary.risk_level == "unknown"
    assert summary.facts == ["今日收盘价9元，昨日10元"]


def test_rejects_missing_risk_level() -> None:
    data = {
        "facts": ["今日收盘价9元，昨日10元"],
        "inferences": [],
        "unknowns": ["缺少成交量和公司公告"],
        "sources": ["用户提供的数据"],
    }

    with pytest.raises(ValidationError) as exc_info:
        RiskSummary.model_validate(data)

    assert any(
        error["loc"] == ("risk_level",) and error["type"] == "missing"
        for error in exc_info.value.errors()
    )


def test_rejects_facts_as_string() -> None:
    data = {
        "facts": "今日收盘价9元，昨日10元",
        "inferences": [],
        "unknowns": ["缺少成交量和公司公告"],
        "risk_level": "unknown",
        "sources": ["用户提供的数据"],
    }

    with pytest.raises(ValidationError) as exc_info:
        RiskSummary.model_validate(data)

    assert any(
        error["loc"] == ("facts",) and error["type"] == "list_type"
        for error in exc_info.value.errors()
    )


def test_rejects_invalid_risk_level() -> None:
    data = {
        "facts": ["今日收盘价9元，昨日10元"],
        "inferences": [],
        "unknowns": ["缺少成交量和公司公告"],
        "risk_level": "safe",
        "sources": ["用户提供的数据"],
    }

    with pytest.raises(ValidationError) as exc_info:
        RiskSummary.model_validate(data)

    assert any(
        error["loc"] == ("risk_level",) and error["type"] == "literal_error"
        for error in exc_info.value.errors()
    )


def test_parses_valid_json_text() -> None:
    text = """
    {
        "facts": ["今日收盘价9元，昨日10元"],
        "inferences": [],
        "unknowns": ["缺少成交量和公司公告"],
        "risk_level": "unknown",
        "sources": ["用户提供的数据"]
    }
    """

    summary = parse_risk_summary(text)

    assert isinstance(summary, RiskSummary)
    assert summary.risk_level == "unknown"
    assert summary.facts == ["今日收盘价9元，昨日10元"]


def test_reports_invalid_json() -> None:
    text = '{"facts": ['

    with pytest.raises(
        RiskSummaryParseError,
        match="模型输出格式无效",
    ):
        parse_risk_summary(text)


def test_reports_missing_field_in_json() -> None:
    text = """
    {
        "facts": ["今日收盘价9元"],
        "inferences": [],
        "unknowns": ["缺少成交量"],
        "sources": ["用户提供的数据"]
    }
    """

    with pytest.raises(
        RiskSummaryParseError,
        match="模型输出格式无效",
    ):
        parse_risk_summary(text)


def test_generates_risk_summary_from_model_reply() -> None:
    client = FakeModelClient(
        reply="""
        {
            "facts": ["今日收盘价9元，昨日10元"],
            "inferences": [],
            "unknowns": ["缺少成交量"],
            "risk_level": "unknown",
            "sources": ["用户提供的数据"]
        }
        """
    )

    summary = generate_risk_summary(
        client,
        "昨日收盘价10元，今日收盘价9元，来源：用户提供的数据。",
    )

    assert isinstance(summary, RiskSummary)
    assert summary.facts == ["今日收盘价9元，昨日10元"]
    assert summary.risk_level == "unknown"


def test_generation_reports_invalid_model_reply() -> None:
    client = FakeModelClient(reply="这是一段普通文字，不是JSON")

    with pytest.raises(
        RiskSummaryParseError,
        match="模型输出格式无效",
    ):
        generate_risk_summary(client, "请根据提供的数据生成风险摘要")


def test_risk_generation_budgets_output_and_surfaces_truncation():
    from app.llm_client import ModelOutputTruncatedError

    class Truncated:
        def chat(self, messages):
            assert "每个数组最多3条" in messages[0]["content"]
            assert "总计不超过450个汉字" in messages[0]["content"]
            raise ModelOutputTruncatedError("模型输出达到长度上限，结果未完整生成")

    with pytest.raises(RiskSummaryParseError, match="输出达到长度上限"):
        generate_risk_summary(Truncated(), "资料" * 9000)
