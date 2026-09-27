"""第一关：在这里手写核心类型与接口。

需要定义：
JSONValue、TextContent、ToolCall、UserMessage、AssistantMessage、
ToolExecutionResult、ToolResultMessage、AgentMessage、ModelAdapter、ToolExecutor。

约束：禁止使用 Any；不要引用任何模型厂商或参考项目的类型。
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, Protocol

type JSONPrimitive = None | bool | int | float | str
type JSONValue = JSONPrimitive | tuple[JSONValue, ...] | Mapping[str, JSONValue]


def freeze_json(value: object) -> JSONValue:
    if value is None or isinstance(
        value,
        (bool, int, float, str),
    ):
        return value

    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)

    if isinstance(value, Mapping):
        copied: dict[str, JSONValue] = {}

        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")

            copied[key] = freeze_json(item)

        return MappingProxyType(copied)

    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


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
    async def query(
        self, messages: Sequence[AgentMessage], signal: CancellationToken | None = None
    ) -> AssistantMessage: ...


class ToolExecutor(Protocol):
    async def execute(
        self, tool_call: ToolCall, signal: CancellationToken | None = None
    ) -> ToolExecutionResult: ...
