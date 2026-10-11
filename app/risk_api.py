from collections.abc import Iterator
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.auth.dependencies import require_actor
from app.config import Settings
from app.llm_client import ModelClient, create_model_client
from app.risk_summary import (
    RiskSummary,
    RiskSummaryParseError,
    generate_risk_summary,
)

router = APIRouter(dependencies=[Depends(require_actor)])


class RiskSummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_text: str = Field(min_length=1)


def get_model_client() -> Iterator[ModelClient]:
    offline_summary = RiskSummary(
        facts=[],
        inferences=[],
        sources=[],
        unknowns=["当前为离线假模型模式，未对输入数据进行分析。"],
        risk_level="unknown",
    )
    with httpx.Client() as http_client:
        yield create_model_client(
            Settings(), http_client, fake_reply=offline_summary.model_dump_json()
        )


@router.post("/api/v1/risk-summary", response_model=RiskSummary)
def create_risk_summary(
    payload: RiskSummaryRequest,
    model: Annotated[ModelClient, Depends(get_model_client)],
) -> RiskSummary:
    try:
        return generate_risk_summary(model, payload.input_text)
    except RiskSummaryParseError as exc:
        raise HTTPException(
            status_code=502,
            detail="模型输出格式无效",
        ) from exc
