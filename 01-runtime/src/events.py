"""Observable lifecycle events emitted by the minimal agent loop."""

from dataclasses import dataclass, field
from typing import Literal, Protocol

from .assistant_attempt import AssistantAttempt
from .lifecycle import StepEndReason, TurnEndReason
from .types import AgentMessage, ToolCall, ToolExecutionResult


@dataclass(frozen=True, slots=True)
class AgentStartEvent:
    run_id: str
    type: Literal["agent_start"] = field(default="agent_start", init=False)


@dataclass(frozen=True, slots=True)
class AgentEndEvent:
    messages: tuple[AgentMessage, ...]
    run_id: str
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


@dataclass(frozen=True, slots=True)
class TurnStartEvent:
    run_id: str
    turn_id: str
    type: Literal["turn_start"] = field(default="turn_start", init=False)


@dataclass(frozen=True, slots=True)
class TurnEndEvent:
    run_id: str
    turn_id: str
    reason: TurnEndReason
    type: Literal["turn_end"] = field(default="turn_end", init=False)


@dataclass(frozen=True, slots=True)
class StepStartEvent:
    run_id: str
    turn_id: str
    step_id: str
    type: Literal["step_start"] = field(default="step_start", init=False)


@dataclass(frozen=True, slots=True)
class StepEndEvent:
    run_id: str
    turn_id: str
    step_id: str
    reason: StepEndReason
    type: Literal["step_end"] = field(default="step_end", init=False)


@dataclass(frozen=True, slots=True)
class AssistantAttemptStartEvent:
    attempt_id: str
    run_id: str
    turn_id: str
    step_id: str
    type: Literal["assistant_attempt_start"] = field(default="assistant_attempt_start", init=False)


@dataclass(frozen=True, slots=True)
class AssistantAttemptEndEvent:
    attempt: AssistantAttempt
    type: Literal["assistant_attempt_end"] = field(default="assistant_attempt_end", init=False)


type AgentEvent = (
    AgentStartEvent
    | AgentEndEvent
    | MessageStartEvent
    | MessageUpdateEvent
    | MessageEndEvent
    | ToolExecutionStartEvent
    | ToolExecutionEndEvent
    | TurnStartEvent
    | TurnEndEvent
    | StepStartEvent
    | StepEndEvent
    | AssistantAttemptStartEvent
    | AssistantAttemptEndEvent
)


class AgentEventSink(Protocol):
    async def emit(self, event: AgentEvent) -> None: ...
