"""Position alerts from the user's own risk events and measured portfolio facts.

No model call happens here: each alert cites a stored RiskEvent or a number
computed from real quotes, so the page never shows invented advice.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.paper_trading import performance, service
from app.paper_trading.models import PaperAccount
from app.paper_trading.quotes import Quote

CONCENTRATION = Decimal("0.30")
POSITION_LOSS = Decimal("-0.08")
LEVEL_ORDER = {"high": 0, "medium": 1, "unknown": 2, "low": 3}


def account_alerts(session: Session, account: PaperAccount, quotes: dict[str, Quote],
                   now: datetime) -> dict:
    valuation = performance.value_account(session, account, quotes, now)
    rows = performance.holdings(session, account.id)
    stocks = {stock.symbol: stock for _, stock in rows}
    events = service.recent_risk_events(session, account.owner_id, list(stocks.values()), now)
    latest = {}
    for event in events:
        symbol = next((sym for sym, st in stocks.items() if st.id == event.stock_id),
                      ((event.context or {}).get("subject") or {}).get("symbol"))
        latest.setdefault(symbol, event)
    alerts = []
    for row in valuation["positions"]:
        event = latest.get(row["symbol"])
        base = {"symbol": row["symbol"], "name": row["name"]}
        if event is not None and event.risk_level in ("high", "medium"):
            alerts.append({
                **base, "kind": "risk_event", "level": event.risk_level,
                "message": event.summary, "risk_event_id": event.id,
                "risk_type": event.risk_type, "analyzed_at": event.analyzed_at,
            })
        weight = row["weight"]
        if weight is not None and weight >= CONCENTRATION:
            alerts.append({
                **base, "kind": "concentration", "level": "medium",
                "message": f"单只持仓占总资产 {weight * 100:.1f}%，超过 {CONCENTRATION * 100:.0f}%",
            })
        loss = row["unrealized_pct"]
        if loss is not None and loss <= POSITION_LOSS:
            alerts.append({
                **base, "kind": "drawdown", "level": "medium",
                "message": f"按{'实时' if row['price_live'] else '最近成交/估值'}价格浮亏 "
                           f"{-loss * 100:.1f}%（含买入费用）",
            })
    alerts.sort(key=lambda a: (LEVEL_ORDER.get(a["level"], 9), a["symbol"]))
    return {
        "alerts": alerts,
        "unanalyzed": [r["symbol"] for r in valuation["positions"] if r["symbol"] not in latest],
        "valuation_complete": valuation["valuation_complete"],
        "lookback_days": service.RISK_LOOKBACK.days,
    }
