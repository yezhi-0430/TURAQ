from collections.abc import Iterator
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.auth.dependencies import require_actor
from app.llm_client import ModelClient, ModelTimeoutError, create_model_client
from app.model_limits import (
    Admission,
    LimitsUnavailable,
    ModelDeadlineExceeded,
    RateLimited,
    bind_model,
    model_admission,
    public_error,
)
from app.risk_summary import (
    RiskSummary,
    RiskSummaryParseError,
    generate_risk_summary,
)

router = APIRouter(dependencies=[Depends(require_actor)])


class RiskSummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_text: str = Field(min_length=1, max_length=20000)


def get_model_client(admission: Admission = Depends(model_admission)) -> Iterator[ModelClient]:
    offline_summary = RiskSummary(
        facts=[],
        inferences=[],
        sources=[],
        unknowns=["当前为离线假模型模式，未对输入数据进行分析。"],
        risk_level="unknown",
    )
    with httpx.Client() as http_client:
        yield create_model_client(
            admission.settings, http_client, fake_reply=offline_summary.model_dump_json()
        )


@router.post("/api/v1/risk-summary", response_model=RiskSummary)
def create_risk_summary(
    payload: RiskSummaryRequest,
    admission: Annotated[Admission, Depends(model_admission)],
    model: Annotated[ModelClient, Depends(get_model_client)],
) -> RiskSummary:
    try:
        return generate_risk_summary(bind_model(model, admission), payload.input_text)
    except (RateLimited, LimitsUnavailable, ModelDeadlineExceeded) as exc:
        raise public_error(exc) from exc
    except ModelTimeoutError as exc:
        raise HTTPException(504, "模型请求超时，请稍后重试") from exc
    except RiskSummaryParseError as exc:
        raise HTTPException(
            status_code=502,
            detail="模型输出格式无效",
        ) from exc
