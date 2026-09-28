"""Minimal core message, streaming, model, and tool contracts.

The core remains provider-neutral and intentionally avoids ``Any``.
"""
import json
import math
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, NoReturn, Protocol

if TYPE_CHECKING:
    from minimal_harness.model_stream import ModelStreamChunk

type JSONPrimitive = None | bool | int | float | str
type JSONValue = JSONPrimitive | tuple[JSONValue, ...] | Mapping[str, JSONValue]

# Freeze tool-call parameters and results before storing them in history.
def freeze_json(value: object) -> JSONValue:
    return _freeze_json(value, ancestors=set())


def _freeze_json(value: object, ancestors: set[int]) -> JSONValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value

    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("JSON numbers must be finite")
        return value

    if not isinstance(value, (list, tuple, Mapping)):
        raise TypeError(f"Unsupported JSON value: {type(value).__name__}")

    identity = id(value)
    if identity in ancestors:
        raise TypeError("Circular JSON value is not supported")

    ancestors.add(identity)
    try:
        if isinstance(value, (list, tuple)):
            return tuple(_freeze_json(item, ancestors) for item in value)

        copied: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            copied[key] = _freeze_json(item, ancestors)

        return MappingProxyType(copied)
    finally:
        ancestors.remove(identity)

#
def serialize_json(value: JSONValue) -> str:
    return json.dumps(_to_json_compatible(value), allow_nan=False, separators=(",", ":"))

def _to_json_compatible(value: JSONValue) -> object:
    if isinstance(value, tuple):
        return [_to_json_compatible(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _to_json_compatible(item) for key, item in value.items()}
    return value

def deserialize_json(encoded: str) -> JSONValue:
    try:
        parsed: object = json.loads(encoded, parse_constant=_reject_non_finite_json_constant)
    except json.JSONDecodeError as error:
        raise ValueError("Invalid JSON") from error
    return freeze_json(parsed)

def _reject_non_finite_json_constant(value: str) -> NoReturn:
    raise ValueError(f"JSON contains non-finite number: {value}")

@dataclass(frozen=True, slots=True)
class TextContent:
    text: str
    type: Literal["text"] = field(default="text", init=False)


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: Mapping[str, JSONValue]
    type: Literal["toolCall"] = field(default="toolCall", init=False)

    def __post_init__(self) -> None:
        frozen = freeze_json(self.arguments)

        if not isinstance(frozen, Mapping):
            raise TypeError("Tool call arguments must be a JSON object")

        object.__setattr__(self, "arguments", frozen)


@dataclass(frozen=True, slots=True)
class UserMessage:
    content: str
    role: Literal["user"] = field(default="user", init=False)


class ModelFormatError(Exception):
    """Model output could not be converted into a valid assistant message."""

    def __init__(self, feedback: UserMessage) -> None:
        super().__init__(feedback.content)
        self.feedback = feedback


type StopReason = Literal["stop", "toolUse", "error", "aborted"]


@dataclass(frozen=True, slots=True)
class AssistantMessage:
    content: tuple[TextContent | ToolCall, ...]
    stop_reason: StopReason
    error_message: str | None = None
    role: Literal["assistant"] = field(default="assistant", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "content", tuple(self.content))


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    content: str
    details: JSONValue = None
    is_error: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", freeze_json(self.details))


@dataclass(frozen=True, slots=True)
class ToolResultMessage:
    tool_call_id: str
    tool_name: str
    content: str
    details: JSONValue = None
    is_error: bool = False
    role: Literal["toolResult"] = field(default="toolResult", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", freeze_json(self.details))


type AgentMessage = UserMessage | AssistantMessage | ToolResultMessage


class CancellationToken(Protocol):
    def is_cancelled(self) -> bool: ...


class ModelAdapter(Protocol):
    def stream(
        self, messages: Sequence[AgentMessage], signal: CancellationToken | None = None
    ) -> AsyncIterator["ModelStreamChunk"]: ...


class ToolExecutor(Protocol):
    async def execute(
        self, tool_call: ToolCall, signal: CancellationToken | None = None
    ) -> ToolExecutionResult: ...
