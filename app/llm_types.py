from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator


class FunctionCall(BaseModel):
    name: str = Field(strict=True, min_length=1)
    arguments: str = Field(strict=True)


class ToolCall(BaseModel):
    id: str = Field(strict=True, min_length=1)
    type: Literal["function"]
    function: FunctionCall


class ToolReply(BaseModel):
    usage: dict[str, object] | None = Field(default=None, exclude=True)
    content: str | None = Field(default=None, strict=True)
    tool_calls: list[ToolCall] = Field(default_factory=list)

    @field_validator("tool_calls", mode="before")
    @classmethod
    def normalize_null_calls(cls, value: object) -> object:
        return [] if value is None else value

    @model_validator(mode="after")
    def require_text_or_calls(self) -> Self:
        if self.content is None and not self.tool_calls:
            raise ValueError("模型既没有文本也没有工具调用")
        return self
