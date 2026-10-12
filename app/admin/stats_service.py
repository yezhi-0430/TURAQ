"""Counts with explicit provenance; tool attempts are not model calls or cost."""

from datetime import UTC, datetime, time, timedelta, timezone

from sqlalchemy import Date, case, cast, func, select

from app.auth.models import Invite, LoginSession, ModelBudget, User
from app.auth.service import utcnow
from app.database import ToolAuditRecord as Audit

SHANGHAI = timezone(timedelta(hours=8))


def start_of_day(day):
    return datetime.combine(day, time.min, SHANGHAI).astimezone(UTC)


def overview(db):
    now = utcnow()
    today = now.astimezone(SHANGHAI).date()
    budgets = db.execute(select(ModelBudget.key, ModelBudget.events)).all()
    cutoff, end = (now - timedelta(days=1)).timestamp(), now.timestamp()
    research, attempts = 0, 0
    for key, events in budgets:
        count = sum(cutoff < event <= end for event in events)
        if key == "site:attempts":
            attempts += count
        elif key.startswith("user:"):
            research += count
    slots = db.scalar(
        select(func.coalesce(func.sum(Invite.max_uses - Invite.uses), 0)).where(
            Invite.revoked.is_(False), Invite.expires_at > now, Invite.uses < Invite.max_uses
        )
    )
    active = db.scalar(
        select(func.count(func.distinct(LoginSession.user_id))).where(
            LoginSession.user_id.is_not(None),
            LoginSession.last_seen_at >= now - timedelta(days=7),
            LoginSession.last_seen_at <= now,
        )
    )
    tools_today = db.scalar(
        select(func.count())
        .select_from(Audit)
        .where(Audit.created_at >= start_of_day(today), Audit.created_at <= now)
    )
    return {
        "total_users": db.scalar(select(func.count()).select_from(User)),
        "active_users_7d": active,
        "total_invites": db.scalar(select(func.count()).select_from(Invite)),
        "available_slots": slots,
        "research_requests_24h": research,
        "model_http_attempts_24h": attempts,
        "tool_attempts_today": tools_today,
        "tokens": None,
        "estimated_cost": None,
        "model_calls_7d": None,
        "as_of": now,
        "timezone": "Asia/Shanghai",
    }


def llm_usage(db):
    now = utcnow()
    today = now.astimezone(SHANGHAI).date()
    first = today - timedelta(days=6)
    filters = (Audit.created_at >= start_of_day(first), Audit.created_at <= now)
    count = func.count(Audit.id)
    successes = func.sum(case((Audit.status == "success", 1), else_=0))
    users = db.execute(
        select(User.id, User.email, count.label("calls"), successes.label("success"))
        .join(Audit, Audit.actor_id == User.id)
        .where(*filters)
        .group_by(User.id, User.email)
        .order_by(count.desc(), User.id)
        .limit(20)
    ).all()
    tools = db.execute(
        select(Audit.tool_name, count.label("usage"), successes.label("success"))
        .where(*filters)
        .group_by(Audit.tool_name)
        .order_by(count.desc(), Audit.tool_name)
        .limit(100)
    ).all()
    day_expression = (
        cast(func.timezone("Asia/Shanghai", Audit.created_at), Date)
        if db.bind.dialect.name == "postgresql"
        else func.date(Audit.created_at, "+8 hours")
    )
    dates = {
        str(day): n
        for day, n in db.execute(
            select(day_expression, count).where(*filters).group_by(day_expression)
        )
    }
    return {
        "metric": "tool_attempts",
        "period_days": 7,
        "timezone": "Asia/Shanghai",
        "by_user": [
            {
                "id": row.id,
                "email": row.email,
                "calls": row.calls,
                "success_rate": row.success / row.calls,
            }
            for row in users
        ],
        "by_tool": [
            {
                "tool_name": row.tool_name,
                "usage": row.usage,
                "success_rate": row.success / row.usage,
            }
            for row in tools
        ],
        "daily_trend": [
            {
                "date": str(first + timedelta(days=i)),
                "calls": dates.get(str(first + timedelta(days=i)), 0),
            }
            for i in range(7)
        ],
        "tokens": None,
        "estimated_cost": None,
        "as_of": now,
    }
