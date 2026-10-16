"""A-share trading rules used by the simulator; pure functions, no I/O."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

SHANGHAI = timezone(timedelta(hours=8))
CENT = Decimal("0.01")
STAMP_DUTY_RATE = Decimal("0.0005")  # sells only, halved on 2023-08-28
TRANSFER_FEE_RATE = Decimal("0.00001")  # both sides
DEFAULT_COMMISSION_RATE = Decimal("0.00025")
DEFAULT_MIN_COMMISSION = Decimal("5")
# SSE/SZSE main-board risk-warning stocks moved from 5% to 10% on 2026-07-06.
MAIN_BOARD_ST_10_PERCENT_FROM = date(2026, 7, 6)
SESSIONS = ((time(9, 30), time(11, 30)), (time(13, 0), time(15, 0)))
QUOTE_MAX_AGE = timedelta(minutes=3)


@dataclass(frozen=True)
class Board:
    name: str
    limit: Decimal
    min_quantity: int
    step: int


def board_for(symbol: str, name: str, today: date) -> Board:
    code, market = symbol.split(".")
    st = "ST" in name.upper()
    if market == "BJ":
        return Board("北交所", Decimal("0.30"), 100, 1)
    if code.startswith(("688", "689")):
        return Board("科创板", Decimal("0.20"), 200, 1)
    if code.startswith(("300", "301", "302")):
        return Board("创业板", Decimal("0.20"), 100, 100)
    if st:
        limit = Decimal("0.10") if today >= MAIN_BOARD_ST_10_PERCENT_FROM else Decimal("0.05")
        return Board("主板风险警示", limit, 100, 100)
    return Board("主板", Decimal("0.10"), 100, 100)


def price_band(previous_close: Decimal, board: Board) -> tuple[Decimal, Decimal]:
    up = (previous_close * (1 + board.limit)).quantize(CENT, ROUND_HALF_UP)
    down = (previous_close * (1 - board.limit)).quantize(CENT, ROUND_HALF_UP)
    return down, up


def check_buy_quantity(quantity: int, board: Board) -> str | None:
    if quantity < board.min_quantity:
        return f"{board.name}买入至少 {board.min_quantity} 股"
    if (quantity - board.min_quantity) % board.step:
        return f"{board.name}买入须为 {board.step} 股整数倍"
    return None


def check_sell_quantity(quantity: int, sellable: int, board: Board) -> str | None:
    if quantity > sellable:
        return f"可卖数量不足（当前可卖 {sellable} 股，当日买入次日可卖）"
    # Odd lots below the minimum must be sold together in a single order.
    if quantity == sellable:
        return None
    if quantity < board.min_quantity or (quantity - board.min_quantity) % board.step:
        return (f"{board.name}卖出须满足 {board.min_quantity} 股起、{board.step} 股递增，"
                "或一次卖出全部零股")
    return None


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, ROUND_HALF_UP)


@dataclass(frozen=True)
class Fees:
    amount: Decimal
    commission: Decimal
    stamp_duty: Decimal
    transfer_fee: Decimal

    @property
    def total(self) -> Decimal:
        return self.commission + self.stamp_duty + self.transfer_fee


def fees(side: str, price: Decimal, quantity: int, rate: Decimal, minimum: Decimal) -> Fees:
    amount = money(price * quantity)
    commission = max(money(amount * rate), minimum)
    stamp = money(amount * STAMP_DUTY_RATE) if side == "sell" else Decimal("0.00")
    return Fees(amount, commission, stamp, money(amount * TRANSFER_FEE_RATE))


def max_buy_quantity(cash: Decimal, price: Decimal, board: Board, rate: Decimal,
                     minimum: Decimal) -> int:
    if price <= 0:
        return 0
    quantity = int((cash / (price * (1 + rate + TRANSFER_FEE_RATE))).to_integral_value(ROUND_DOWN))
    if quantity < board.min_quantity:
        return 0
    quantity -= (quantity - board.min_quantity) % board.step
    while quantity >= board.min_quantity:
        cost = fees("buy", price, quantity, rate, minimum)
        if cost.amount + cost.total <= cash:
            return quantity
        quantity -= board.step
    return 0


def in_session(moment: datetime) -> bool:
    local = moment.astimezone(SHANGHAI)
    if local.weekday() >= 5:
        return False
    return any(start <= local.time() < end for start, end in SESSIONS)


def trade_date(moment: datetime) -> date:
    return moment.astimezone(SHANGHAI).date()


def live_quote_problem(quote_time: datetime, now: datetime) -> str | None:
    """Holidays have no calendar here; a same-day, fresh source quote proves the market is open."""
    if not in_session(now):
        return "当前不在交易时段（工作日 9:30-11:30、13:00-15:00）"
    if trade_date(quote_time) != trade_date(now) or now - quote_time > QUOTE_MAX_AGE:
        return "行情源没有当日实时成交（可能休市或停牌）"
    return None
