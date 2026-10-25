"""Authenticated local PDF checks and explicit admitted model fact evaluations."""

import base64
import binascii
import hashlib

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.analysis.evaluation import evaluate_document
from app.analysis.quality import MAX_BYTES, analyze_pages, parse_pdf
from app.auth.dependencies import require_actor
from app.llm_client import ModelClient
from app.model_limits import (
    Admission,
    LimitsUnavailable,
    ModelDeadlineExceeded,
    RateLimited,
    model_admission,
    public_error,
)
from app.risk_api import get_model_client

router = APIRouter(prefix="/api/analysis", tags=["财报分析"], dependencies=[Depends(require_actor)])


class ReportUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=255)
    company_name: str = Field(default="未知公司", max_length=200)
    content_base64: str = Field(min_length=1, max_length=((MAX_BYTES + 2) // 3) * 4)


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


@router.post("/upload")
def upload_financial_report(payload: ReportUpload):
    if not payload.filename.lower().endswith(".pdf"):
        raise HTTPException(422, "请选择PDF文件")
    try:
        data = base64.b64decode(payload.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "文件内容无效，请重新选择PDF") from None
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "PDF超过20MiB上限")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(422, "文件不是有效PDF，未生成财务数据")
    try:
        return analyze_pages(
            parse_pdf(data),
            payload.company_name.strip() or "未知公司",
            hashlib.sha256(data).hexdigest(),
            filename=payload.filename,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except Exception:
        raise HTTPException(503, "解析服务暂不可用，请稍后重试；未使用模拟数据") from None


@router.get("/test")
def test_analysis():
    text = "\n".join(
        [
            "营业收入 150000000000",
            "净利润 75000000000",
            "资产总计 500000000000",
            "负债合计 150000000000",
            "流动资产合计 300000000000",
            "流动负债合计 80000000000",
            "应收账款 8000000000",
            "存货 60000000000",
            "经营活动产生的现金流量净额 90000000000",
        ]
    )
    return analyze_pages(
        [dict(page=1, text=text)],
        "演示公司（模拟数据）",
        "0" * 64,
        filename="演示数据",
        kind="demo",
    )


@router.post("/evaluate")
def evaluate_report(
    payload: EvaluationRequest,
    admission: Admission = Depends(model_admission),
    model: ModelClient = Depends(get_model_client),
):
    try:
        result = evaluate_document(payload.source_sha256, model, admission)
        failure = result.pop("runtime_failure", None)
        if failure:
            return JSONResponse(
                status_code=failure["status"],
                headers=failure["headers"],
                content=dict(detail=failure["detail"], partial=result),
            )
        return result
    except (RateLimited, LimitsUnavailable, ModelDeadlineExceeded) as exc:
        raise public_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
