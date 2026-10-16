"""Explicit, additive upgrade; leaves existing identity/watchlist/market tables untouched."""

from sqlalchemy import Engine

from app.database import Base, engine
from app.risk_records import RiskAnalysis, RiskEvent
from app.risk_task_records import RiskTask, RiskTaskItem


def upgrade_risk_tables(target: Engine) -> None:
    with target.begin() as connection:
        Base.metadata.create_all(
            connection,
            tables=[
                RiskAnalysis.__table__,
                RiskEvent.__table__,
                RiskTask.__table__,
                RiskTaskItem.__table__,
            ],
        )


if __name__ == "__main__":
    upgrade_risk_tables(engine)
    print("风险分析与事件表已就绪；现有数据未改动。")
