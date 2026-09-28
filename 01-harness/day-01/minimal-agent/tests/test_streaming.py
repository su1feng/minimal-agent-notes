"""Day 02 contract tests for streaming drafts and final message commits."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

import pytest

from minimal_harness.agent_loop import run_agent_loop
from minimal_harness.events import (
    AgentEndEvent,
    AgentEvent,
    AgentStartEvent,
    AssistantDraft,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
)
from minimal_harness.model_stream import FinishChunk, ModelStreamChunk, TextChunk
from minimal_harness.types import (
    AgentMessage,
    AssistantMessage,
    CancellationToken,
    TextContent,
    UserMessage,
)
from tests.fakes import ScriptedToolExecutor


@dataclass(slots=True)
class RecordingEventSink:
    events: list[AgentEvent] = field(default_factory=list)

    async def emit(self, event: AgentEvent) -> None:
        self.events.append(event)


type StreamOutcome = ModelStreamChunk | BaseException


@dataclass(slots=True)
class ScriptedStreamingModel:
    outcomes: Sequence[StreamOutcome]

    def __post_init__(self) -> None:
        self.outcomes = tuple(self.outcomes)

    async def stream(
        self,
        messages: Sequence[AgentMessage],
        signal: CancellationToken | None = None,
    ) -> AsyncIterator[ModelStreamChunk]:
        del messages, signal
        for outcome in self.outcomes:
            if isinstance(outcome, BaseException):
                raise outcome
            yield outcome


def answer(text: str) -> AssistantMessage:
    return AssistantMessage(content=(TextContent(text=text),), stop_reason="stop")


@pytest.mark.asyncio
async def test_streaming_drafts_are_events_but_only_the_final_message_enters_history() -> None:
    initial = (UserMessage(content="hello"),)
    final = answer("Hello")
    model = ScriptedStreamingModel(
        [
            TextChunk(text="Hel"),
            TextChunk(text="lo"),
            FinishChunk(stop_reason="stop"),
        ]
    )
    sink = RecordingEventSink()

    result = await run_agent_loop(
        model=model,
        tool_executor=ScriptedToolExecutor([]),
        initial_messages=initial,
        event_sink=sink,
    )

    assert result == (*initial, final)
    assert sink.events == [
        AgentStartEvent(),
        MessageStartEvent(message=AssistantDraft(text="")),
        MessageUpdateEvent(message=AssistantDraft(text="Hel"), delta="Hel"),
        MessageUpdateEvent(message=AssistantDraft(text="Hello"), delta="lo"),
        MessageEndEvent(message=final),
        AgentEndEvent(messages=result),
    ]


@dataclass(slots=True)
class NotifyingCancellationToken:
    cancelled: bool = False
    _cancelled: asyncio.Event = field(default_factory=asyncio.Event, init=False)

    def is_cancelled(self) -> bool:
        return self.cancelled

    def cancel(self) -> None:
        self.cancelled = True
        self._cancelled.set()

    async def wait_cancelled(self) -> None:
        await self._cancelled.wait()


@dataclass(slots=True)
class BlockingStreamingModel:
    delta_sent: asyncio.Event = field(default_factory=asyncio.Event, init=False)

    async def stream(
        self,
        messages: Sequence[AgentMessage],
        signal: CancellationToken | None = None,
    ) -> AsyncIterator[ModelStreamChunk]:
        del messages
        assert isinstance(signal, NotifyingCancellationToken)
        yield TextChunk(text="partial")
        self.delta_sent.set()
        await signal.wait_cancelled()
        raise asyncio.CancelledError


@pytest.mark.asyncio
async def test_stream_cancellation_commits_one_aborted_message_then_propagates() -> None:
    token = NotifyingCancellationToken()
    model = BlockingStreamingModel()
    sink = RecordingEventSink()
    task = asyncio.create_task(
        run_agent_loop(
            model=model,
            tool_executor=ScriptedToolExecutor([]),
            initial_messages=(),
            signal=token,
            event_sink=sink,
        )
    )

    await asyncio.wait_for(model.delta_sent.wait(), timeout=0.1)
    token.cancel()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=0.1)

    assert sink.events[:3] == [
        AgentStartEvent(),
        MessageStartEvent(message=AssistantDraft(text="")),
        MessageUpdateEvent(message=AssistantDraft(text="partial"), delta="partial"),
    ]
    message_end = sink.events[-2]
    assert isinstance(message_end, MessageEndEvent)
    aborted = message_end.message
    assert isinstance(aborted, AssistantMessage)
    assert aborted == AssistantMessage(
        content=(TextContent(text="partial"),),
        stop_reason="aborted",
        error_message="Cancelled",
    )
    assert sink.events[-1] == AgentEndEvent(messages=(aborted,))
    assert sum(isinstance(event, MessageEndEvent) for event in sink.events) == 1


@pytest.mark.asyncio
async def test_stream_without_a_terminal_message_is_a_contract_error() -> None:
    sink = RecordingEventSink()
    model = ScriptedStreamingModel([TextChunk(text="unfinished")])

    with pytest.raises(RuntimeError, match="before finish"):
        await run_agent_loop(
            model=model,
            tool_executor=ScriptedToolExecutor([]),
            initial_messages=(),
            event_sink=sink,
        )

    assert sink.events[-1] == AgentEndEvent(messages=())
