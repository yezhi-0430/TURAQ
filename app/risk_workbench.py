"""Saved text analysis and private workbench queries; scanning is not connected."""

import hashlib
import logging
from datetime import UTC, date, datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import case, func, or_, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.auth.dependencies import Actor, get_session_factory, require_actor
from app.auth.service import aware
from app.database import Stock, Watchlist, WatchlistItem
from app.llm_client import (
    ModelAPIError,
    ModelAuthenticationError,
    ModelClient,
    ModelConfigurationError,
    ModelConnectionError,
    ModelResponseError,
)
from app.model_limits import Admission, ModelDeadlineExceeded, model_admission, public_error
from app.risk_api import RiskSummaryRequest, create_risk_summary, get_model_client
from app.risk_records import RiskAnalysis, RiskEvent
from app.risk_task_records import RiskTask, RiskTaskItem

RiskType = Literal["announcement", "financial", "price_volume", "comprehensive"]
RiskLevel = Literal["high", "medium", "low", "unknown"]
ReviewStatus = Literal["unread", "viewed", "following"]
router = APIRouter(prefix="/api/v1/risk", tags=["risk"], dependencies=[Depends(require_actor)])
logger = logging.getLogger(__name__)


class AnalysisRequest(RiskSummaryRequest):
    request_id: UUID
    symbol: str | None = Field(default=None, max_length=20)
    risk_type: Literal["announcement", "financial"] = "announcement"
    title: str = Field(default="用户提供的资料", min_length=1, max_length=200)
    published_date: date | None = None
    source_url: str | None = Field(default=None, max_length=2000)
    page: str | None = Field(default=None, max_length=40)

    @field_validator("input_text", "title")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("请输入非空资料或标题")
        return value

    @field_validator("source_url")
    @classmethod
    def safe_url(cls, value):
        if not value:
            return None
        try:
            parts = urlsplit(value)
            if (
                parts.scheme not in ("https", "http")
                or not parts.hostname
                or parts.username
                or parts.password
                or "\\" in value
                or any(ord(c) <= 32 for c in value)
            ):
                raise ValueError("来源链接须为无凭据的 HTTP(S) 链接")
            _ = parts.port
        except ValueError as exc:
            raise ValueError("来源链接无效") from exc
        return value


class StatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ReviewStatus


def iso(value):
    if isinstance(value, datetime):
        return aware(value).isoformat()
    return value.isoformat() if value else None


def owned_stock_ids(db, actor_id, group_id=None):
    if (
        group_id is not None
        and db.scalar(
            select(Watchlist.id).where(Watchlist.id == group_id, Watchlist.owner_id == actor_id)
        )
        is None
    ):
        raise HTTPException(404, "自选组不存在")
    statement = select(WatchlistItem.stock_id).join(Watchlist).where(Watchlist.owner_id == actor_id)
    if group_id is not None:
        statement = statement.where(Watchlist.id == group_id)
    return statement.distinct()


def event_dict(db, event, *, detail=False):
    analysis = db.get(RiskAnalysis, event.analysis_id)
    stock = db.get(Stock, event.stock_id) if event.stock_id else None
    result = dict(
        id=event.id,
        analysis_id=analysis.id,
        symbol=stock.symbol if stock else (event.context or {}).get("subject", {}).get("symbol"),
        stock_name=stock.name if stock else (event.context or {}).get("subject", {}).get("name"),
        summary=event.summary,
        risk_type=event.risk_type,
        risk_level=event.risk_level,
        status=event.status,
        published_date=iso(event.published_date),
        trade_date=iso(event.trade_date),
        scanned_at=iso(event.scanned_at),
        analyzed_at=iso(event.analyzed_at),
        model_mode=analysis.model_mode,
        title=analysis.title,
    )
    if detail:
        result.update(
            result=analysis.result,
            evidence=analysis.evidence,
            model_sources=(analysis.result or {}).get("sources", []),
            input_text=analysis.input_text,
            context=event.context,
            version=analysis.version,
        )
    return result


def find_event(db, eid, owner):
    event = db.scalar(select(RiskEvent).where(RiskEvent.id == eid, RiskEvent.owner_id == owner))
    if event is None:
        raise HTTPException(404, "风险记录不存在")
    return event


def existing_result(db, row, fingerprint):
    if row.fingerprint != fingerprint:
        raise HTTPException(409, "请求编号已用于不同资料")
    if row.generation_status == "pending":
        raise HTTPException(409, "资料分析已受理，结果待确认；请刷新历史记录")
    if row.generation_status == "failed":
        raise HTTPException(row.error_status or 502, row.error or "分析失败")
    event = db.scalar(select(RiskEvent).where(RiskEvent.analysis_id == row.id))
    return event_dict(db, event, detail=True)


def save_result(factory, aid, owner_id, result, admission):
    with factory() as db:
        admission.bound_database_work(db)
        row = db.get(RiskAnalysis, aid)
        if row.model_mode == "fake":
            result = result.model_copy(
                update={
                    "facts": [],
                    "inferences": [],
                    "sources": [],
                    "risk_level": "unknown",
                    "unknowns": ["隔离测试模型结果，未对资料进行真实分析。"],
                }
            )
        row.result, row.generation_status = result.model_dump(), "completed"
        row.generated_at = datetime.now(UTC)
        event = RiskEvent(
            owner_id=owner_id,
            analysis_id=row.id,
            stock_id=row.stock_id,
            risk_type=row.risk_type,
            summary=(result.inferences or result.facts or result.unknowns or [row.title])[0][:500],
            risk_level=result.risk_level,
            analyzed_at=row.generated_at,
            published_date=row.published_date,
        )
        db.add(event)
        db.commit()
        return event_dict(db, event, detail=True)


def record_failure(factory, aid, error):
    try:
        with factory() as db:
            if db.bind.dialect.name == "postgresql":
                db.execute(text("SET LOCAL statement_timeout = '3000ms'"))
                db.execute(text("SET LOCAL lock_timeout = '3000ms'"))
            row = db.get(RiskAnalysis, aid)
            # A lost COMMIT acknowledgement must never overwrite a completed result.
            if row.generation_status == "pending":
                row.generation_status, row.error = "failed", str(error.detail)[:200]
                row.error_status = error.status_code
            db.commit()
    except SQLAlchemyError:
        logger.error("风险分析失败状态暂未能保存")


@router.post("/analyses", status_code=201)
def analyze(
    payload: AnalysisRequest,
    actor: Actor = Depends(require_actor),
    factory=Depends(get_session_factory),
    admission: Admission = Depends(model_admission),
    model: ModelClient = Depends(get_model_client),
):
    fingerprint = hashlib.sha256(
        payload.model_dump_json(exclude={"request_id"}).encode()
    ).hexdigest()
    with factory() as db:
        admission.bound_database_work(db)
        existing = db.scalar(
            select(RiskAnalysis).where(
                RiskAnalysis.owner_id == actor.id,
                RiskAnalysis.request_id == str(payload.request_id),
            )
        )
        if existing:
            return existing_result(db, existing, fingerprint)
        stock = None
        if payload.symbol:
            stock = db.scalar(
                select(Stock).where(
                    Stock.symbol == payload.symbol.strip().upper(),
                    Stock.id.in_(owned_stock_ids(db, actor.id)),
                )
            )
            if stock is None:
                raise HTTPException(404, "关联股票不在你的自选范围中")
        row = RiskAnalysis(
            owner_id=actor.id,
            request_id=str(payload.request_id),
            fingerprint=fingerprint,
            stock_id=stock.id if stock else None,
            title=payload.title,
            risk_type=payload.risk_type,
            published_date=payload.published_date,
            input_text=payload.input_text,
            model_mode=admission.settings.model_provider,
            evidence=[
                dict(
                    kind="user_material",
                    verification="user_provided",
                    title=payload.title,
                    date=iso(payload.published_date),
                    url=payload.source_url,
                    page=payload.page,
                    excerpt=payload.input_text,
                    conclusion_refs=[],
                )
            ],
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.scalar(
                select(RiskAnalysis).where(
                    RiskAnalysis.owner_id == actor.id,
                    RiskAnalysis.request_id == str(payload.request_id),
                )
            )
            if existing:
                return existing_result(db, existing, fingerprint)
            raise
        aid = row.id
    try:
        result = create_risk_summary(
            RiskSummaryRequest(input_text=payload.input_text), admission, model
        )
        return save_result(factory, aid, actor.id, result, admission)
    except (
        HTTPException,
        ModelConnectionError,
        ModelAPIError,
        ModelResponseError,
        ModelAuthenticationError,
        ModelConfigurationError,
        ModelDeadlineExceeded,
        SQLAlchemyError,
    ) as exc:
        if isinstance(exc, HTTPException):
            error = exc
        elif isinstance(exc, ModelDeadlineExceeded):
            error = public_error(exc)
        elif isinstance(exc, SQLAlchemyError):
            error = HTTPException(503, "分析结果保存未确认，请刷新历史核对")
        elif isinstance(exc, (ModelAuthenticationError, ModelConfigurationError)):
            error = HTTPException(503, "模型服务配置暂不可用")
        else:
            error = HTTPException(502, "模型服务请求失败")
        # Cleanup/history deliberately has its own finite DB timeout, after model deadline expiry.
        record_failure(factory, aid, error)
        raise error from exc


@router.get("/events")
def events(
    actor: Actor = Depends(require_actor),
    factory=Depends(get_session_factory),
    group_id: int | None = Query(None, ge=1),
    symbol: str | None = Query(None, max_length=20),
    include_unlinked: bool = True,
    external_symbol: str | None = Query(None, max_length=20),
    risk_type: RiskType | None = None,
    risk_level: RiskLevel | None = None,
    status: ReviewStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(10, ge=1, le=50),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "起始日期不能晚于结束日期")
    with factory() as db:
        stocks = owned_stock_ids(db, actor.id, group_id)
        if symbol:
            stocks = stocks.where(
                WatchlistItem.stock_id.in_(
                    select(Stock.id).where(Stock.symbol == symbol.strip().upper())
                )
            )
        stock_count = len(db.scalars(stocks).all())
        scope = RiskEvent.stock_id.in_(stocks)
        if external_symbol:
            if group_id is not None or symbol:
                raise HTTPException(422, "组外股票分析范围不能与自选筛选混用")
            from app.disclosures import canonical

            try:
                external_symbol = canonical(external_symbol)
            except ValueError as exc:
                raise HTTPException(422, "股票代码格式无效") from exc
            scope = or_(
                RiskEvent.context["subject"]["symbol"].as_string() == external_symbol,
                RiskEvent.stock_id.in_(select(Stock.id).where(Stock.symbol == external_symbol)),
            )
            stock_count = 1
        if include_unlinked and group_id is None and not symbol and not external_symbol:
            scope = or_(scope, RiskEvent.stock_id.is_(None))
        filters = [RiskEvent.owner_id == actor.id, scope]
        for column, value in [
            (RiskEvent.risk_type, risk_type),
            (RiskEvent.risk_level, risk_level),
            (RiskEvent.status, status),
        ]:
            if value:
                filters.append(column == value)
        # Time filter means SOURCE publication date, never generated_at or trade_date.
        if date_from:
            filters.append(RiskEvent.published_date >= date_from)
        if date_to:
            filters.append(RiskEvent.published_date <= date_to)
        real = RiskAnalysis.model_mode != "fake"
        counts = db.execute(
            select(
                func.count(RiskEvent.id),
                func.sum(case((real & (RiskEvent.status != "viewed"), 1), else_=0)),
                func.sum(case((real & (RiskEvent.risk_level == "high"), 1), else_=0)),
                func.sum(case((real & (RiskEvent.risk_level == "unknown"), 1), else_=0)),
            )
            .join(RiskAnalysis)
            .where(*filters)
        ).one()
        rows = db.scalars(
            select(RiskEvent)
            .where(*filters)
            .order_by(
                case(
                    ((RiskEvent.risk_level == "high") & (RiskEvent.status == "unread"), 0), else_=1
                ),
                case(
                    (RiskEvent.risk_level == "high", 0),
                    (RiskEvent.risk_level == "medium", 1),
                    (RiskEvent.risk_level == "low", 2),
                    else_=3,
                ),
                RiskEvent.analyzed_at.desc(),
                RiskEvent.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return dict(
            items=[event_dict(db, e) for e in rows],
            total=counts[0],
            page=page,
            page_size=page_size,
            overview=dict(
                monitored_stocks=stock_count,
                pending=counts[1] or 0,
                high=counts[2] or 0,
                unknown=counts[3] or 0,
            ),
            scan=dict(
                status="not_connected",
                last_scanned_at=None,
                coverage=None,
                task_status="not_scanned",
                announcement=False,
                financial=False,
                price_volume=False,
            ),
        )


@router.get("/events/{event_id}")
def detail(
    event_id: int, actor: Actor = Depends(require_actor), factory=Depends(get_session_factory)
):
    with factory() as db:
        return event_dict(db, find_event(db, event_id, actor.id), detail=True)


@router.patch("/events/{event_id}")
def review(
    event_id: int,
    payload: StatusRequest,
    actor: Actor = Depends(require_actor),
    factory=Depends(get_session_factory),
):
    with factory() as db:
        event = find_event(db, event_id, actor.id)
        event.status = payload.status
        db.commit()
        return event_dict(db, event, detail=True)


def version_event(db, analysis_id, owner_id):
    versions = (
        select(RiskAnalysis.id)
        .where(
            RiskAnalysis.id == analysis_id,
            RiskAnalysis.owner_id == owner_id,
        )
        .cte("owned_versions", recursive=True)
    )
    versions = versions.union(
        select(RiskAnalysis.id)
        .join(
            versions,
            RiskAnalysis.previous_version_id == versions.c.id,
        )
        .where(RiskAnalysis.owner_id == owner_id)
    )
    return db.scalar(
        select(RiskEvent).where(
            RiskEvent.owner_id == owner_id,
            RiskEvent.analysis_id.in_(select(versions.c.id)),
        )
    )


@router.get("/analyses")
def history(
    actor: Actor = Depends(require_actor),
    factory=Depends(get_session_factory),
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(10, ge=1, le=50),
):
    with factory() as db:
        query = select(RiskAnalysis).where(RiskAnalysis.owner_id == actor.id)
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.execute(
            query.add_columns(RiskEvent.id)
            .outerjoin(RiskEvent, RiskEvent.analysis_id == RiskAnalysis.id)
            .order_by(RiskAnalysis.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return dict(
            total=total,
            page=page,
            page_size=page_size,
            items=[
                dict(
                    id=r.id,
                    request_id=r.request_id,
                    event_id=eid
                    or getattr(version_event(db, r.id, actor.id), "id", None)
                    or db.scalar(
                        select(RiskTaskItem.event_id)
                        .join(RiskTask)
                        .where(
                            RiskTask.owner_id == actor.id,
                            RiskTaskItem.snapshot["analysis_id"].as_integer() == r.id,
                        )
                    ),
                    title=r.title,
                    generation_status=(
                        "unconfirmed"
                        if r.generation_status == "pending"
                        and (datetime.now(UTC) - aware(r.created_at)).total_seconds() > 130
                        else r.generation_status
                    ),
                    created_at=iso(r.created_at),
                    generated_at=iso(r.generated_at),
                    model_mode=r.model_mode,
                    version=r.version,
                    error=r.error,
                )
                for r, eid in rows
            ],
        )


@router.get("/analyses/{analysis_id}")
def analysis_detail(
    analysis_id: int, actor: Actor = Depends(require_actor), factory=Depends(get_session_factory)
):
    with factory() as db:
        row = db.scalar(
            select(RiskAnalysis).where(
                RiskAnalysis.id == analysis_id, RiskAnalysis.owner_id == actor.id
            )
        )
        if row is None or row.generation_status != "completed":
            raise HTTPException(404, "分析记录不存在或尚未完成")
        event = db.scalar(
            select(RiskEvent).where(RiskEvent.analysis_id == row.id, RiskEvent.owner_id == actor.id)
        )
        item = db.scalar(
            select(RiskTaskItem)
            .join(RiskTask)
            .where(
                RiskTask.owner_id == actor.id,
                RiskTaskItem.snapshot["analysis_id"].as_integer() == row.id,
            )
        )
        if event is None and item and item.event_id:
            event = find_event(db, item.event_id, actor.id)
        if event is None:
            event = version_event(db, row.id, actor.id)
        if event is None:
            raise HTTPException(404, "分析版本对应事件不存在")
        output = event_dict(db, event, detail=True)
        output.update(
            analysis_id=row.id,
            title=row.title,
            input_text=row.input_text,
            result=row.result,
            evidence=row.evidence,
            model_sources=(row.result or {}).get("sources", []),
            model_mode=row.model_mode,
            version=row.version,
            analyzed_at=iso(row.generated_at),
            risk_level=row.result["risk_level"],
            historical=event.analysis_id != row.id,
        )
        output["summary"] = (
            row.result.get("inferences")
            or row.result.get("facts")
            or row.result.get("unknowns")
            or [row.title]
        )[0][:500]
        if item:
            output.update(
                symbol=item.symbol,
                stock_name=item.name,
                context=item.snapshot.get("context", {}),
                trade_date=item.snapshot.get("trade_date"),
            )
        if row.result.get("record_context"):
            output.update(row.result["record_context"])
        return output
