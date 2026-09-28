"""Observable lifecycle events emitted by the minimal agent loop."""

from dataclasses import dataclass, field
from typing import Literal, Protocol

from .types import AgentMessage, ToolCall, ToolExecutionResult


@dataclass(frozen=True, slots=True)
class AgentStartEvent:
    type: Literal["agent_start"] = field(default="agent_start", init=False)


@dataclass(frozen=True, slots=True)
class AgentEndEvent:
    messages: tuple[AgentMessage, ...]
    type: Literal["agent_end"] = field(default="agent_end", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "messages", tuple(self.messages))


@dataclass(frozen=True, slots=True)
class AssistantDraft:
    text: str


type ObservableMessage = AgentMessage | AssistantDraft


@dataclass(frozen=True, slots=True)
class MessageStartEvent:
    message: ObservableMessage
    type: Literal["message_start"] = field(default="message_start", init=False)


@dataclass(frozen=True, slots=True)
class MessageUpdateEvent:
    message: AssistantDraft
    delta: str
    type: Literal["message_update"] = field(default="message_update", init=False)


@dataclass(frozen=True, slots=True)
class MessageEndEvent:
    message: ObservableMessage
    type: Literal["message_end"] = field(default="message_end", init=False)


@dataclass(frozen=True, slots=True)
class ToolExecutionStartEvent:
    tool_call: ToolCall
    type: Literal["tool_execution_start"] = field(default="tool_execution_start", init=False)


@dataclass(frozen=True, slots=True)
class ToolExecutionEndEvent:
    tool_call: ToolCall
    result: ToolExecutionResult
    type: Literal["tool_execution_end"] = field(default="tool_execution_end", init=False)


type AgentEvent = (
    AgentStartEvent
    | AgentEndEvent
    | MessageStartEvent
    | MessageUpdateEvent
    | MessageEndEvent
    | ToolExecutionStartEvent
    | ToolExecutionEndEvent
)


class AgentEventSink(Protocol):
    async def emit(self, event: AgentEvent) -> None: ...
