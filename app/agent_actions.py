"""Separate model proposals from explicit client requests and committed results."""

import json
import logging
from collections.abc import Callable
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy.orm import Session

from app.tools.market_data import StockProfileArguments
from app.watchlists.repository import (
    StockNotInWatchlistError,
    WatchlistNotFoundError,
    remove_stock_from_watchlist,
)

logger = logging.getLogger(__name__)


def _validate_text(value: str) -> str:
    if not value.strip():
        raise ValueError("文本不能为空白")
    value.encode("utf-8")
    return value


class ActionTarget(StockProfileArguments):
    operation: Literal["remove_watchlist_stock"]
    watchlist_id: int = Field(strict=True, gt=0, le=2147483647)


class Suggestion(ActionTarget):
    kind: Literal["suggestion"]
    status: Literal["suggested"] = "suggested"
    text: str = Field(strict=True, min_length=1, max_length=4000)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _validate_text(value)


class ExecutionRequest(ActionTarget):
    """An explicit API request, not proof of authentication or human identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["execution_request"]


class ActionError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["watchlist_not_found", "stock_not_in_watchlist", "execution_error"]
    message: str


class ExecutionResult(ActionTarget):
    kind: Literal["execution_result"] = "execution_result"
    status: Literal["success", "error"]
    error: ActionError | None = None

    @model_validator(mode="after")
    def require_consistent_error(self) -> Self:
        if (self.status == "error") != (self.error is not None):
            raise ValueError("执行状态必须与后端错误一致")
        return self


class SuggestionAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(strict=True, min_length=1, max_length=20000)
    suggestions: list[Suggestion] = Field(default_factory=list, max_length=5)

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, value: str) -> str:
        return _validate_text(value)


class InvalidSuggestionOutput(Exception):
    pass


def parse_agent_answer(raw: str | None) -> tuple[str | None, list[Suggestion]]:
    """Validate optional structured suggestions; never turn them into execution requests."""
    if raw is None:
        return None, []
    try:
        decoded = json.loads(raw)
    except (ValueError, RecursionError):
        return raw, []
    if not isinstance(decoded, dict) or "suggestions" not in decoded:
        return raw, []
    try:
        result = SuggestionAnswer.model_validate(decoded)
    except ValidationError as exc:
        raise InvalidSuggestionOutput("模型建议格式无效") from exc
    return result.answer, result.suggestions


def execute_watchlist_removal(
    request: ExecutionRequest,
    *,
    session_factory: Callable[[], Session],
) -> ExecutionResult:
    """Only this explicit request path invokes writes; success follows repository commit."""
    if not isinstance(request, ExecutionRequest):
        raise TypeError("执行服务只接受 ExecutionRequest")
    error = None
    try:
        with session_factory() as session:
            try:
                remove_stock_from_watchlist(session, request.watchlist_id, request.stock_code)
            except Exception:
                session.rollback()
                raise
    except WatchlistNotFoundError:
        error = ActionError(kind="watchlist_not_found", message="自选组不存在")
    except StockNotInWatchlistError:
        error = ActionError(kind="stock_not_in_watchlist", message="自选组中不存在该股票")
    except Exception:
        logger.exception("显式自选股移除失败")
        error = ActionError(kind="execution_error", message="操作未完成，请稍后重试")
    result = ExecutionResult(
        **request.model_dump(exclude={"kind"}),
        status="error" if error else "success",
        error=error,
    )
    logger.info(result.model_dump_json())
    return result
