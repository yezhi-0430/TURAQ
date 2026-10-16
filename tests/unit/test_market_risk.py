from datetime import date, timedelta

from app.market_risk import assess_market, select_boards


def rows(falling=False):
    return [
        dict(
            trade_date=str(date(2026, 9, 1) + timedelta(days=i)),
            close=str(100 - i if falling else 100 + i),
            volume_lots="100",
        )
        for i in range(40)
    ]


def test_market_judgment_is_independent_of_missing_reports():
    falling = assess_market(rows(True), [], today=date(2026, 10, 11))
    rising = assess_market(rows(), [], today=date(2026, 10, 11))
    assert falling["risk_level"] == "high" and falling["basis"]
    assert rising["risk_level"] == "low"
    assert assess_market(rows()[:10], [], today=date(2026, 10, 11))["risk_level"] == "unknown"
    assert assess_market(rows(), [], today=date(2026, 11, 1))["risk_level"] == "unknown"


def test_intraday_and_unmatched_sector_dates_do_not_invent_comparison():
    sample = rows()
    sample[-1]["close"] = "1"
    result = assess_market(sample, [], today=date(2026, 10, 10), closed_today=False)
    assert result["latest_trade_date"] == "2026-10-09" and result["risk_level"] == "low"
    unmatched = [dict(trade_date="2020-01-01", close="10", volume_lots="1")]
    result = assess_market(rows(), [dict(name="行业", rows=unmatched)], today=date(2026, 10, 11))
    assert result["comparisons"][0]["relative_change_points"] is None


def test_sector_membership_is_bound_to_stock_and_safe_board_code():
    records = [
        dict(
            SECUCODE="600667.SH",
            NEW_BOARD_CODE="BK0726",
            BOARD_NAME="工程",
            BOARD_TYPE="行业",
            SELECTED_BOARD_REASON=None,
        ),
        dict(SECUCODE="600519.SH", NEW_BOARD_CODE="BK0001", BOARD_NAME="其他"),
        dict(SECUCODE="600667.SH", NEW_BOARD_CODE="../bad", BOARD_NAME="危险"),
    ]
    assert [b["code"] for b in select_boards(records, "600667.SH")] == ["BK0726"]


def test_optional_sector_failures_preserve_stock_rating_and_unknown_adjustment(monkeypatch):
    from datetime import datetime, time
    from types import SimpleNamespace

    from app.market import SHANGHAI
    from app.market_risk import MarketContextReader
    from app.tools.research import ResearchRangeArguments

    sample = rows()
    offset = date.today() - date(2026, 10, 11)
    for r in sample:
        r["trade_date"] = str(date.fromisoformat(r["trade_date"]) + offset)
    sample.append(dict(trade_date=str(date.today()), close="1", volume_lots="999"))
    monkeypatch.setattr(
        "app.market_risk.datetime",
        SimpleNamespace(now=lambda tz: datetime.combine(date.today(), time(12), SHANGHAI)),
    )

    class History:
        adjustment = "none"

        def remaining(self):
            return 5

        def __call__(self, args, session):
            return dict(
                rows=sample,
                stock_code=args.stock_code,
                adjustment=self.adjustment,
                warnings=[],
                coverage="unverified",
                source="test",
                source_kind="online_market",
                fetched_at=None,
            )

        async def fetch_bytes(self, *a, **kw):
            raise TimeoutError("source unavailable")

    h = History()
    args = ResearchRangeArguments(
        stock_code="600667.SH",
        start_date=str(date.today() - timedelta(days=90)),
        end_date=str(date.today()),
    )
    result = MarketContextReader(h).analyze(args, SimpleNamespace(info={}))
    assert result["assessment"]["risk_level"] == "low" and result["sector_coverage"] == "partial"
    assert result["input_data"]["latest_trade_date"] == result["assessment"]["latest_trade_date"]
    assert result["input_data"]["record_count"] == result["assessment"]["record_count"]
    h.adjustment = None
    result = MarketContextReader(h).analyze(args, SimpleNamespace(info={}))
    assert result["assessment"]["risk_level"] == "unknown"
