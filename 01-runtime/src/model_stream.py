"""Provider-neutral chunks emitted by model adapters."""

from dataclasses import dataclass, field
from typing import Literal

from .types import JSONValue, StopReason, ToolCall, freeze_json


@dataclass(frozen=True, slots=True)
class TextChunk:
    text: str
    type: Literal["text"] = field(default="text", init=False)


@dataclass(frozen=True, slots=True)
class ToolCallChunk:
    tool_call: ToolCall
    type: Literal["tool_call"] = field(default="tool_call", init=False)


@dataclass(frozen=True, slots=True)
class UsageChunk:
    input_tokens: int
    output_tokens: int
    type: Literal["usage"] = field(default="usage", init=False)


@dataclass(frozen=True, slots=True)
class ProviderReplayState:
    provider: str
    schema_version: int
    payload: JSONValue

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", freeze_json(self.payload))


@dataclass(frozen=True, slots=True)
class FinishChunk:
    stop_reason: StopReason
    error_message: str | None = None
    type: Literal["finish"] = field(default="finish", init=False)
    replay_state: ProviderReplayState | None = None


type ModelStreamChunk = TextChunk | ToolCallChunk | UsageChunk | FinishChunk
