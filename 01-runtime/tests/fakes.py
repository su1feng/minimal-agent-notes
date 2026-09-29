"""Deterministic test doubles for the Day 01 agent loop."""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

from src.lifecycle import LifecycleIdKind
from src.model_stream import FinishChunk, ModelStreamChunk, TextChunk, ToolCallChunk
from src.types import (
    AgentMessage,
    AssistantMessage,
    CancellationToken,
    TextContent,
    ToolCall,
    ToolExecutionResult,
)

type ModelOutcome = AssistantMessage | Exception
type ToolOutcome = ToolExecutionResult | Exception


@dataclass(slots=True)
class SequentialIdGenerator:
    """Generate deterministic lifecycle identifiers for event assertions."""

    counts: dict[LifecycleIdKind, int] = field(default_factory=dict)

    def new_id(self, kind: LifecycleIdKind) -> str:
        number = self.counts.get(kind, 0) + 1
        self.counts[kind] = number
        return f"{kind}-{number}"


@dataclass(slots=True)
class FakeCancellationToken:
    """Manually controlled cooperative-cancellation token."""

    cancelled: bool = False

    def is_cancelled(self) -> bool:
        return self.cancelled

    def cancel(self) -> None:
        self.cancelled = True


@dataclass(slots=True)
class ScriptedModel:
    """Return or raise scripted outcomes while recording immutable call snapshots."""

    outcomes: Sequence[ModelOutcome]
    calls: list[tuple[AgentMessage, ...]] = field(default_factory=list, init=False)
    signals: list[CancellationToken | None] = field(default_factory=list, init=False)
    _cursor: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.outcomes = tuple(self.outcomes)

    async def stream(
        self,
        messages: Sequence[AgentMessage],
        signal: CancellationToken | None = None,
    ) -> AsyncIterator[ModelStreamChunk]:
        self.calls.append(tuple(messages))
        self.signals.append(signal)
        outcome = self._next_outcome()
        if isinstance(outcome, Exception):
            raise outcome
        for block in outcome.content:
            if isinstance(block, TextContent):
                yield TextChunk(text=block.text)
            else:
                yield ToolCallChunk(tool_call=block)

        yield FinishChunk(
            stop_reason=outcome.stop_reason,
            error_message=outcome.error_message,
        )

    def _next_outcome(self) -> ModelOutcome:
        if self._cursor >= len(self.outcomes):
            raise AssertionError("ScriptedModel has no response left")
        outcome = self.outcomes[self._cursor]
        self._cursor += 1
        return outcome


@dataclass(slots=True)
class ScriptedToolExecutor:
    """Return or raise scripted outcomes while recording tool calls and signals."""

    outcomes: Sequence[ToolOutcome]
    calls: list[ToolCall] = field(default_factory=list, init=False)
    signals: list[CancellationToken | None] = field(default_factory=list, init=False)
    _cursor: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.outcomes = tuple(self.outcomes)

    async def execute(
        self,
        tool_call: ToolCall,
        signal: CancellationToken | None = None,
    ) -> ToolExecutionResult:
        self.calls.append(tool_call)
        self.signals.append(signal)
        outcome = self._next_outcome()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def _next_outcome(self) -> ToolOutcome:
        if self._cursor >= len(self.outcomes):
            raise AssertionError("ScriptedToolExecutor has no result left")
        outcome = self.outcomes[self._cursor]
        self._cursor += 1
        return outcome
