"""Real quotes for the simulator, read through the shared MarketService cache."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.market import normalize_symbol
from app.market_api import service


@dataclass(frozen=True)
class Quote:
    symbol: str
    name: str
    kind: str
    price: Decimal | None
    previous_close: Decimal | None
    quote_time: datetime | None
    stale: bool


def canonical(symbol: str) -> str:
    code = normalize_symbol(symbol)
    return code[2:] + "." + code[:2].upper()


def _decimal(value) -> Decimal | None:
    try:
        number = Decimal(str(value)) if value not in (None, "") else None
    except InvalidOperation:
        return None
    return number if number is not None and number.is_finite() and number > 0 else None


def _time(value) -> datetime | None:
    try:
        stamp = datetime.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None
    return stamp if stamp is not None and stamp.tzinfo is not None else None


async def load_quotes(symbols) -> dict[str, Quote]:
    """Missing symbols are simply absent; callers decide how to degrade."""
    wanted = list(dict.fromkeys(symbols))
    result: dict[str, Quote] = {}
    for start in range(0, len(wanted), 40):
        snapshot = await service.quotes(wanted[start:start + 40])
        # Snapshot-level "stale" also covers other symbols; trust each row's own flag.
        for row in snapshot.get("quotes", []):
            symbol = row.get("symbol")
            if not symbol or not row.get("name"):
                continue
            result[symbol] = Quote(
                symbol=symbol,
                name=row["name"],
                kind=row.get("kind", "stock"),
                price=_decimal(row.get("price")),
                previous_close=_decimal(row.get("previous_close")),
                quote_time=_time(row.get("quote_time")),
                stale=bool(row.get("stale")),
            )
    return result
