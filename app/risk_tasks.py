"""Private, durable scope tasks. The browser advances one bounded item at a time."""

import hashlib
import json
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from typing import Literal, Self
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.auth.dependencies import Actor, get_session_factory, require_actor
from app.auth.service import aware
from app.config import Settings
from app.database import Stock
from app.disclosures import canonical
from app.market import SHANGHAI
from app.model_limits import (
    Admission,
    LimitsUnavailable,
    ModelDeadlineExceeded,
    RateLimited,
    admit,
    model_admission,
    public_error,
)
from app.risk_api import RiskSummaryRequest, create_risk_summary, get_model_client
from app.risk_reading import (
    collect_step,
    document_summary,
    final_material,
    progress,
    retry_failed,
    review_step,
)
from app.risk_records import RiskAnalysis, RiskEvent
from app.risk_summary import RiskSummaryParseError
from app.risk_task_analysis import collect_stock
from app.risk_task_records import RiskTask, RiskTaskItem
from app.risk_workbench import owned_stock_ids
from app.stock_list import stock_list_service
from app.user_settings.runtime import get_runtime_policy

router = APIRouter(
    prefix="/api/v1/risk/tasks", tags=["risk"], dependencies=[Depends(require_actor)]
)


class TaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    scope: Literal["all", "group", "stock"]
    group_id: int | None = Field(default=None, ge=1)
    symbol: str | None = Field(default=None, max_length=20)
    days: Literal[30, 90, 180] = 90
    force: bool = False
    mode: Literal["quick", "full"] = "quick"

    @model_validator(mode="after")
    def valid_scope(self) -> Self:
        if self.scope == "stock":
            if not self.symbol or self.group_id is not None:
                raise ValueError("单股分析须提供股票代码，不混用自选组")
            self.symbol = canonical(self.symbol)
        elif self.symbol or (self.scope == "group") != (self.group_id is not None):
            raise ValueError("自选范围参数不一致")
        return self


def get_stock_analyzer():
    return collect_stock


def owned_task(db, task_id, owner, *, lock=False):
    query = select(RiskTask).where(RiskTask.id == task_id, RiskTask.owner_id == owner)
    task = db.scalar(query.with_for_update() if lock else query)
    if task is None:
        raise HTTPException(404, "分析任务不存在")
    return task


def update_task(db, task):
    items = db.scalars(
        select(RiskTaskItem).where(RiskTaskItem.task_id == task.id).order_by(RiskTaskItem.id)
    ).all()
    now = datetime.now(UTC)
    for item in items:
        if (
            item.status == "running"
            and item.lease_expires_at
            and aware(item.lease_expires_at) < now
        ):
            item.status = "unconfirmed"
            item.error = "处理租约已过期，结果待核对；未自动重复模型调用。"
    states = [i.status for i in items]
    task.status = (
        "running"
        if "running" in states
        else "cancelled"
        if task.cancelled
        else "queued"
        if "pending" in states
        else "completed"
        if all(s == "completed" for s in states)
        else "partial_failed"
        if any(s in ("completed", "partial_failed") for s in states)
        else "failed"
    )
    return items


def task_dict(db, task):
    items = update_task(db, task)
    return dict(
        id=task.id,
        status=task.status,
        scope=task.scope,
        days=task.days,
        total=len(items),
        processed=sum(i.status not in ("pending", "running") for i in items),
        created_at=aware(task.created_at).isoformat(),
        updated_at=aware(task.updated_at).isoformat(),
        driver="browser",
        items=[
            dict(
                id=i.id,
                symbol=i.symbol,
                name=i.name,
                status=i.status,
                event_id=i.event_id,
                analysis_id=i.snapshot.get("analysis_id"),
                error=i.error,
                coverage=i.snapshot.get("coverage", {}),
                facts=i.snapshot.get("facts", []),
                market_assessment=i.snapshot.get("context", {}).get("market_assessment", {}),
                progress=progress(i.snapshot),
                answer=i.snapshot.get("answer"),
                recent_findings=(i.snapshot.get("reading", {}).get("findings") or [None])[-1],
            )
            for i in items
        ],
    )


@router.post("", status_code=201)
def create(
    payload: TaskRequest,
    actor: Actor = Depends(require_actor),
    factory=Depends(get_session_factory),
    settings: Settings = Depends(get_runtime_policy),
):
    fingerprint = hashlib.sha256(
        payload.model_dump_json(exclude={"request_id"}).encode()
    ).hexdigest()
    with factory() as db:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SET LOCAL statement_timeout = '5000ms'"))
            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": actor.id})
        existing = db.scalar(
            select(RiskTask).where(
                RiskTask.owner_id == actor.id, RiskTask.request_id == str(payload.request_id)
            )
        )
        if existing:
            if existing.fingerprint != fingerprint:
                raise HTTPException(409, "请求编号已用于不同范围")
            return task_dict(db, existing)
        if payload.scope == "stock":
            cached = stock_list_service.get_by_symbol(payload.symbol)
            stored = db.scalar(select(Stock).where(Stock.symbol == payload.symbol))
            if not cached and stored is None:
                raise HTTPException(404, "未在证券目录找到该股票，请搜索并确认目标")
            securities = [
                dict(symbol=payload.symbol, name=cached["name"] if cached else stored.name)
            ]
        else:
            stocks = db.scalars(
                select(Stock)
                .where(Stock.id.in_(owned_stock_ids(db, actor.id, payload.group_id)))
                .order_by(Stock.symbol)
            ).all()
            securities = [dict(symbol=s.symbol, name=s.name) for s in stocks]
        if not securities:
            raise HTTPException(422, "所选范围没有股票，请选择分组或搜索股票")
        if len(securities) > 100:
            raise HTTPException(422, "单次范围最多100只股票，请选择更小分组")
        scope = dict(
            kind=payload.scope,
            group_id=payload.group_id,
            symbol=payload.symbol,
            securities=securities,
            end_date=datetime.now(SHANGHAI).date().isoformat(),
            analysis_rule="stock_overview_v4_answer_first",
            mode=payload.mode,
        )
        key = hashlib.sha256(
            json.dumps(
                dict(
                    symbols=[s["symbol"] for s in securities],
                    days=payload.days,
                    date=scope["end_date"],
                    rule=scope["analysis_rule"],
                    model_mode=settings.model_provider,
                    mode=payload.mode,
                ),
                sort_keys=True,
            ).encode()
        ).hexdigest()
        if not payload.force:
            existing = db.scalar(
                select(RiskTask)
                .where(
                    RiskTask.owner_id == actor.id,
                    RiskTask.scope_key == key,
                    RiskTask.cancelled.is_(False),
                )
                .order_by(RiskTask.id.desc())
            )
            if existing:
                return task_dict(db, existing)
        task = RiskTask(
            owner_id=actor.id,
            request_id=str(payload.request_id),
            fingerprint=fingerprint,
            scope_key=key,
            scope=scope,
            days=payload.days,
        )
        db.add(task)
        db.flush()
        db.add_all([RiskTaskItem(task_id=task.id, **s) for s in securities])
        db.commit()
        return task_dict(db, task)


@router.get("")
def recent(actor: Actor = Depends(require_actor), factory=Depends(get_session_factory)):
    with factory() as db:
        tasks = db.scalars(
            select(RiskTask)
            .where(RiskTask.owner_id == actor.id)
            .order_by(RiskTask.id.desc())
            .limit(10)
        ).all()
        result = [task_dict(db, t) for t in tasks]
        db.commit()
        return dict(items=result)


@router.get("/{task_id}")
def detail(
    task_id: int, actor: Actor = Depends(require_actor), factory=Depends(get_session_factory)
):
    with factory() as db:
        result = task_dict(db, owned_task(db, task_id, actor.id, lock=True))
        db.commit()
        return result


@router.post("/{task_id}/cancel")
def cancel(
    task_id: int, actor: Actor = Depends(require_actor), factory=Depends(get_session_factory)
):
    with factory() as db:
        task = owned_task(db, task_id, actor.id, lock=True)
        task.cancelled = True
        for item in update_task(db, task):
            if item.status == "pending":
                item.status = "cancelled"
        result = task_dict(db, task)
        db.commit()
        return result


@router.post("/{task_id}/resume")
def resume(
    task_id: int, actor: Actor = Depends(require_actor), factory=Depends(get_session_factory)
):
    with factory() as db:
        task = owned_task(db, task_id, actor.id, lock=True)
        items = update_task(db, task)
        if any(i.status == "running" for i in items):
            raise HTTPException(409, "当前股票仍在处理，请先等待结果")
        task.cancelled = False
        for item in items:
            if item.status in ("failed", "cancelled"):
                item.status = "pending"
                item.error = None
        result = task_dict(db, task)
        db.commit()
        return result


def require_pending_task(
    task_id: int,
    request: Request,
    actor: Actor = Depends(require_actor),
    factory=Depends(get_session_factory),
    settings: Settings = Depends(get_runtime_policy),
):
    """Reject an idle retransmission before reserving any model quota; recheck under lock later."""
    with factory() as db:
        task = owned_task(db, task_id, actor.id, lock=True)
        items = update_task(db, task)
        active = next((i for i in items if i.status == "pending"), None)
        if (
            active
            and active.snapshot.get("reading")
            and active.snapshot["reading"].get("model_mode") != settings.model_provider
        ):
            raise HTTPException(409, "模型模式已变化，请新建当前模式任务；未消耗模型额度。")
        ready = (
            not task.cancelled
            and any(i.status == "pending" for i in items)
            and not any(i.status == "running" for i in items)
        )
        if active and active.snapshot.get("reading") and settings.model_provider == "qwen":
            request.state.model_purpose = "risk_document"
        db.commit()
    if not ready:
        raise HTTPException(409, "任务没有可立即执行项，请刷新进度核对；未消耗模型额度。")


@router.post("/{task_id}/items/{item_id}/{action}")
def reading_action(
    task_id: int,
    item_id: int,
    action: Literal["overview", "deepen"],
    actor: Actor = Depends(require_actor),
    factory=Depends(get_session_factory),
    settings: Settings = Depends(get_runtime_policy),
):
    """Choose a saved first answer or opt into full reading, without a model call."""
    with factory() as db:
        task = owned_task(db, task_id, actor.id, lock=True)
        items = update_task(db, task)
        item = next((i for i in items if i.id == item_id), None)
        if item is None:
            raise HTTPException(404, "分析项不存在")
        if any(i.status == "running" for i in items) or item.status == "unconfirmed":
            raise HTTPException(409, "当前处理尚未结束，请先刷新进度核对")
        snapshot = deepcopy(item.snapshot)
        work = snapshot.get("reading")
        if not work or work.get("model_mode") != settings.model_provider:
            raise HTTPException(409, "尚无可用资料或模型模式已变化，请重新分析")
        if action == "overview":
            if work["stage"] in ("overview", "done"):
                raise HTTPException(409, "结论已生成或正在等待生成")
            work["resume_stage"] = work.get("resume_stage", work["stage"])
            work["stage"] = "overview"
        else:
            if work["stage"] != "paused" or work.get("resume_stage") == "done":
                raise HTTPException(409, "没有待继续的全文核查")
            stage = work.pop("resume_stage", "listing")
            retry, cleared = retry_failed(work)
            # Retried sources restart collection; already-read batches and cursor are kept.
            if retry and stage not in ("listing",):
                stage = retry
            work["stage"] = stage
            snapshot["warnings"] = [w for w in snapshot.get("warnings", []) if w not in cleared]
        item.snapshot = snapshot
        item.status = "pending"
        item.error = None
        task.cancelled = False
        task.updated_at = datetime.now(UTC)
        result = task_dict(db, task)
        db.commit()
        return result


@router.post("/{task_id}/process")
def process(
    task_id: int,
    actor: Actor = Depends(require_actor),
    factory=Depends(get_session_factory),
    eligibility=Depends(require_pending_task),
    admission: Admission = Depends(model_admission),
    model=Depends(get_model_client),
    analyzer=Depends(get_stock_analyzer),
):
    with factory() as db:
        admission.bound_database_work(db)
        task = owned_task(db, task_id, actor.id, lock=True)
        items = update_task(db, task)
        if task.cancelled or not any(i.status == "pending" for i in items):
            result = task_dict(db, task)
            db.commit()
            return result
        if any(i.status == "running" for i in items):
            raise HTTPException(409, "已有股票正在分析，请查询进度")
        item = next(i for i in items if i.status == "pending")
        token = str(uuid4())
        item.status = "running"
        item.lease_token = token
        item.lease_expires_at = datetime.now(UTC) + timedelta(seconds=admission.remaining() + 10)
        task.status = "running"
        task.updated_at = datetime.now(UTC)
        symbol, days, iid, name = item.symbol, task.days, item.id, item.name
        saved_snapshot = item.snapshot
        interval_end = date.fromisoformat(task.scope["end_date"])
        db.commit()
    snapshot = saved_snapshot
    try:
        if snapshot.get("reading"):
            if snapshot["reading"]["stage"] in ("review", "reduce"):
                snapshot = review_step(snapshot, model, admission)
                if snapshot["reading"]["stage"] != "ready":
                    return save_continuation(
                        factory, actor.id, task_id, iid, token, snapshot, admission
                    )
                # Final synthesis is a separate model-admitted request.
                return save_continuation(
                    factory, actor.id, task_id, iid, token, snapshot, admission
                )
            if snapshot["reading"]["stage"] not in ("ready", "overview"):
                raise HTTPException(409, "请先推进资料采集阶段，不重复调用模型")
            # Each overview/deepen pass re-summarizes; keep one current progress line.
            snapshot["facts"] = [f for f in snapshot["facts"] if not f.startswith("全文提取")]
            snapshot["input_text"] = final_material(snapshot)
            p = progress(snapshot)
            snapshot["facts"].append(
                f"全文提取{p['extracted']}份、{p['pages']}页，"
                f"模型已阅读{p['batches']}批、{p['read_characters']}字；失败文件{p['failed']}份。"
            )
            snapshot["warnings"] = list(
                dict.fromkeys(
                    snapshot["warnings"] + [e["message"] for e in snapshot["reading"]["errors"]]
                )
            )
        else:
            snapshot = analyzer(symbol, days, admission, end_date=interval_end)
        with factory() as db:
            admission.bound_database_work(db)
            current = db.get(RiskTaskItem, iid)
            current.snapshot = snapshot
            db.commit()
        if not snapshot["evidence"] and admission.settings.model_provider == "qwen":
            raise HTTPException(502, "未取得可分析的真实资料，未生成风险结论；请查看各资料状态。")
        if snapshot.get("reading") and admission.settings.model_provider == "qwen":
            from app.risk_summary import RiskSummary

            summary = RiskSummary.model_validate(
                document_summary(
                    model,
                    admission,
                    snapshot["input_text"],
                    final=True,
                    preliminary=snapshot["reading"]["stage"] == "overview",
                )
            )
        else:
            summary = create_risk_summary(
                RiskSummaryRequest(input_text=snapshot["input_text"]), admission, model
            )
        # Source excerpts and server calculations are retained independently of model claims.
        result = summary.model_dump()
        preliminary = snapshot.get("reading", {}).get("stage") == "overview"
        result["analysis_scope"] = "preliminary" if preliminary else "full"
        result["inferences"] += ["模型提取，须对照原文：" + f for f in result["facts"]]
        result["facts"] = snapshot["facts"]
        result["unknowns"] = list(dict.fromkeys(snapshot["warnings"] + result["unknowns"]))
        assessment = snapshot.get("context", {}).get("market_assessment", {})
        result["risk_level"] = assessment.get("risk_level", "unknown")
        result["market_assessment"] = assessment
        result["inferences"] += assessment.get("basis", [])
        if preliminary:
            result["unknowns"].append("首轮判断基于已取得资料，未读披露尚未核查；可继续全文核查。")
        if admission.settings.model_provider == "fake":
            result = dict(
                facts=[],
                inferences=[],
                unknowns=["隔离测试模型，未进行真实分析。"],
                sources=[],
                risk_level="unknown",
            )
        with factory() as db:
            admission.bound_database_work(db)
            current = db.get(RiskTaskItem, iid)
            if current.lease_token != token or current.status != "running":
                raise HTTPException(409, "结果提交租约已过期，请核对历史")
            stock = db.scalar(select(Stock).where(Stock.symbol == symbol))
            documents = sorted(
                {
                    str(e.get("document_id") or e.get("url"))
                    for e in snapshot["evidence"]
                    if e.get("kind") == "public_document"
                }
            )
            identity = json.dumps(
                dict(
                    symbol=symbol,
                    days=days,
                    trade_date=snapshot["trade_date"] or str(interval_end),
                    documents=None if snapshot.get("reading") else documents,
                    rule="stock_overview_v4_answer_first"
                    if snapshot.get("reading")
                    else "stock_overview_v2_market_attention",
                    model_mode=admission.settings.model_provider,
                ),
                sort_keys=True,
            )
            dedup_key = hashlib.sha256(identity.encode()).hexdigest()
            existing_event = db.scalar(
                select(RiskEvent)
                .where(RiskEvent.owner_id == actor.id, RiskEvent.dedup_key == dedup_key)
                .with_for_update()
            )
            previous = db.get(RiskAnalysis, existing_event.analysis_id) if existing_event else None
            result["record_context"] = dict(
                symbol=symbol,
                stock_name=name,
                trade_date=snapshot["trade_date"],
                context={**snapshot.get("context", {}), "coverage": snapshot["coverage"]},
            )
            analysis = RiskAnalysis(
                owner_id=actor.id,
                request_id=token,
                fingerprint=hashlib.sha256(snapshot["input_text"].encode()).hexdigest(),
                stock_id=stock.id if stock else None,
                risk_type="comprehensive",
                title=f"{name}自动风险分析",
                input_text=snapshot["input_text"],
                evidence=snapshot["evidence"],
                result=result,
                model_mode=admission.settings.model_provider,
                generation_status="completed",
                generated_at=datetime.now(UTC),
                version=previous.version + 1 if previous else 1,
                previous_version_id=previous.id if previous else None,
            )
            db.add(analysis)
            db.flush()
            context = {
                **snapshot.get("context", {}),
                "subject": dict(symbol=symbol, name=name),
                "coverage": snapshot["coverage"],
                "task_id": task_id,
            }
            event = existing_event or RiskEvent(
                owner_id=actor.id,
                analysis_id=analysis.id,
                stock_id=analysis.stock_id,
                risk_type="comprehensive",
                risk_level=result["risk_level"],
                dedup_key=dedup_key,
            )
            event.analysis_id = analysis.id
            event.risk_level = result["risk_level"]
            event.summary = (result["inferences"] or result["facts"] or result["unknowns"])[0][:500]
            event.trade_date = (
                date.fromisoformat(snapshot["trade_date"]) if snapshot["trade_date"] else None
            )
            event.analyzed_at = analysis.generated_at
            event.context = context
            if existing_event is None:
                db.add(event)
            db.flush()
            current.event_id = event.id
            current.snapshot = {**snapshot, "analysis_id": analysis.id}
            current.snapshot["answer"] = (
                {
                    **result,
                    "inferences": summary.inferences,
                }
                if admission.settings.model_provider == "qwen"
                else result
            )
            if snapshot.get("reading"):
                current.snapshot["reading"]["stage"] = "paused" if preliminary else "done"
            # 分析完成，只是资料覆盖有限
            current.status = "completed"
            current.lease_token = None
            current.lease_expires_at = None
            t = owned_task(db, task_id, actor.id, lock=True)
            t.updated_at = datetime.now(UTC)
            output = task_dict(db, t)
            db.commit()
            return output
    except Exception as exc:
        # Independent bounded cleanup preserves acquired facts even after the model deadline.
        if isinstance(exc, (RateLimited, LimitsUnavailable, ModelDeadlineExceeded)):
            failure_message = public_error(exc).detail
        elif isinstance(exc, RiskSummaryParseError):
            failure_message = str(exc)
        elif isinstance(exc, HTTPException):
            failure_message = str(exc.detail)
        else:
            failure_message = "资料获取、模型生成或保存失败，请核对任务后重试。"
        with factory() as db:
            if db.bind.dialect.name == "postgresql":
                db.execute(text("SET LOCAL statement_timeout = '3000ms'"))
                db.execute(text("SET LOCAL lock_timeout = '3000ms'"))
            current = db.get(RiskTaskItem, iid)
            if current.lease_token == token and current.status == "running":
                current.status = "failed"
                current.snapshot = snapshot
                current.error = failure_message[:200]
                current.lease_token = None
                current.lease_expires_at = None
            t = owned_task(db, task_id, actor.id, lock=True)
            t.updated_at = datetime.now(UTC)
            output = task_dict(db, t)
            db.commit()
        if isinstance(exc, SQLAlchemyError):
            raise HTTPException(503, "分析保存未确认，请刷新任务核对") from exc
        return output


def save_continuation(factory, owner, task_id, iid, token, snapshot, admission):
    with factory() as db:
        admission.bound_database_work(db)
        item = db.get(RiskTaskItem, iid)
        if item.lease_token != token or item.status != "running":
            raise HTTPException(409, "处理租约已变化，请核对任务进度")
        task = owned_task(db, task_id, owner, lock=True)
        item.snapshot = snapshot
        item.status = "cancelled" if task.cancelled else "pending"
        item.lease_token = None
        item.lease_expires_at = None
        task.updated_at = datetime.now(UTC)
        output = task_dict(db, task)
        db.commit()
        return output


def collection_admission(
    request: Request,
    actor: Actor = Depends(require_actor),
    factory=Depends(get_session_factory),
    settings: Settings = Depends(get_runtime_policy),
):
    # Whole-document reading downloads and parses large PDFs; give it the document budget.
    purpose = getattr(request.state, "model_purpose", "default")
    try:
        admission = admit(factory, actor.id, settings, charge_request=False, purpose=purpose)
    except (RateLimited, LimitsUnavailable, ModelDeadlineExceeded) as exc:
        raise public_error(exc) from exc
    try:
        yield admission
    finally:
        admission.release()


@router.post("/{task_id}/collect")
def collect(
    task_id: int,
    actor: Actor = Depends(require_actor),
    factory=Depends(get_session_factory),
    eligibility=Depends(require_pending_task),
    admission: Admission = Depends(collection_admission),
):
    with factory() as db:
        admission.bound_database_work(db)
        task = owned_task(db, task_id, actor.id, lock=True)
        items = update_task(db, task)
        if task.cancelled or any(i.status == "running" for i in items):
            raise HTTPException(409, "任务已停止或正在处理")
        item = next((i for i in items if i.status == "pending"), None)
        if item is None:
            raise HTTPException(409, "没有待采集项")
        if item.snapshot.get("reading", {}).get("stage") in (
            "review",
            "reduce",
            "ready",
            "done",
            "overview",
            "paused",
        ):
            raise HTTPException(409, "采集阶段已完成，请推进模型阅读")
        token = str(uuid4())
        iid = item.id
        symbol = item.symbol
        days = task.days
        snapshot = item.snapshot
        end_date = date.fromisoformat(task.scope["end_date"])
        first_answer = task.scope.get("mode") == "quick" and not snapshot.get("reading")
        item.status = "running"
        item.lease_token = token
        item.lease_expires_at = datetime.now(UTC) + timedelta(seconds=admission.remaining() + 10)
        task.updated_at = datetime.now(UTC)
        db.commit()
    try:
        snapshot = collect_step(symbol, days, admission, end_date=end_date, state=snapshot)
        if first_answer and admission.settings.model_provider == "qwen":
            # Reuse only this owner's same-symbol, same-period, same-mode saved reading.
            with factory() as db:
                candidates = db.execute(
                    select(RiskTaskItem.snapshot, RiskTask.scope)
                    .join(RiskTask, RiskTask.id == RiskTaskItem.task_id)
                    .where(
                        RiskTask.owner_id == actor.id,
                        RiskTask.days == days,
                        RiskTaskItem.symbol == symbol,
                        RiskTaskItem.id != iid,
                        RiskTaskItem.status != "running",
                        RiskTask.scope["end_date"].as_string() == str(end_date),
                    )
                    .order_by(RiskTaskItem.id.desc())
                    .limit(5)
                ).all()
            reusable = [
                s
                for s, _ in candidates
                if s.get("reading", {}).get("model_mode") == "qwen"
                and s["reading"].get("batches", 0) > 0
            ]
            if reusable:
                previous = max(reusable, key=lambda s: s["reading"].get("read_characters", 0))
                snapshot["reading"] = deepcopy(previous["reading"])
                snapshot["evidence"] += deepcopy(
                    [e for e in previous.get("evidence", []) if e.get("kind") == "public_document"]
                )
                for kind in ("reports", "announcements"):
                    snapshot["coverage"][kind] = previous.get("coverage", {}).get(kind, "partial")
                snapshot["warnings"].append(
                    "披露发现复用同日、同区间已保存阅读；新增披露尚未重新查询。"
                )
            work = snapshot["reading"]
            work["resume_stage"] = work.get("resume_stage", work["stage"])
            work["stage"] = "overview"
            if not reusable:
                snapshot["coverage"].update(reports="not_connected", announcements="not_connected")
        return save_continuation(factory, actor.id, task_id, iid, token, snapshot, admission)
    except Exception as exc:
        with factory() as db:
            if db.bind.dialect.name == "postgresql":
                db.execute(text("SET LOCAL statement_timeout = '3000ms'"))
            item = db.get(RiskTaskItem, iid)
            if item.lease_token == token:
                item.snapshot = snapshot
                item.status = "failed"
                item.lease_token = None
                item.lease_expires_at = None
                item.error = "资料采集未完成，已保留进度：" + type(exc).__name__
            task = owned_task(db, task_id, actor.id, lock=True)
            task.updated_at = datetime.now(UTC)
            output = task_dict(db, task)
            db.commit()
            return output
