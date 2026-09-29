"""Day 02 contract tests for streaming drafts and final message commits."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

import pytest

from src.agent_loop import run_agent_loop
from src.assistant_attempt import AssistantAttempt, AttemptStatus
from src.events import (
    AgentEndEvent,
    AgentEvent,
    AgentStartEvent,
    AssistantAttemptEndEvent,
    AssistantAttemptStartEvent,
    AssistantDraft,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    StepEndEvent,
    StepStartEvent,
    TurnEndEvent,
    TurnStartEvent,
)
from src.model_stream import FinishChunk, ModelStreamChunk, TextChunk
from src.types import (
    AgentMessage,
    AssistantMessage,
    CancellationToken,
    TextContent,
    UserMessage,
)
from tests.fakes import ScriptedToolExecutor, SequentialIdGenerator

RUN_ID = "run-1"
TURN_ID = "turn-1"


def attempt(*, status: AttemptStatus, chunks: tuple[ModelStreamChunk, ...]) -> AssistantAttempt:
    return AssistantAttempt(
        attempt_id="attempt-1",
        run_id=RUN_ID,
        turn_id=TURN_ID,
        step_id="step-1",
        status=status,
        chunks=chunks,
    )


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
        id_generator=SequentialIdGenerator(),
    )

    assert result == (*initial, final)
    assert sink.events == [
        AgentStartEvent(run_id=RUN_ID),
        TurnStartEvent(run_id=RUN_ID, turn_id=TURN_ID),
        StepStartEvent(run_id=RUN_ID, turn_id=TURN_ID, step_id="step-1"),
        AssistantAttemptStartEvent(
            attempt_id="attempt-1", run_id=RUN_ID, turn_id=TURN_ID, step_id="step-1"
        ),
        MessageStartEvent(message=AssistantDraft(text="")),
        MessageUpdateEvent(message=AssistantDraft(text="Hel"), delta="Hel"),
        MessageUpdateEvent(message=AssistantDraft(text="Hello"), delta="lo"),
        MessageEndEvent(message=final),
        AssistantAttemptEndEvent(
            attempt=attempt(
                status="completed",
                chunks=(
                    TextChunk(text="Hel"),
                    TextChunk(text="lo"),
                    FinishChunk(stop_reason="stop"),
                ),
            )
        ),
        StepEndEvent(run_id=RUN_ID, turn_id=TURN_ID, step_id="step-1", reason="completed"),
        TurnEndEvent(run_id=RUN_ID, turn_id=TURN_ID, reason="completed"),
        AgentEndEvent(messages=result, run_id=RUN_ID),
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
            id_generator=SequentialIdGenerator(),
        )
    )

    await asyncio.wait_for(model.delta_sent.wait(), timeout=0.1)
    token.cancel()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=0.1)

    assert sink.events[:6] == [
        AgentStartEvent(run_id=RUN_ID),
        TurnStartEvent(run_id=RUN_ID, turn_id=TURN_ID),
        StepStartEvent(run_id=RUN_ID, turn_id=TURN_ID, step_id="step-1"),
        AssistantAttemptStartEvent(
            attempt_id="attempt-1", run_id=RUN_ID, turn_id=TURN_ID, step_id="step-1"
        ),
        MessageStartEvent(message=AssistantDraft(text="")),
        MessageUpdateEvent(message=AssistantDraft(text="partial"), delta="partial"),
    ]
    message_end = next(event for event in sink.events if isinstance(event, MessageEndEvent))
    assert isinstance(message_end, MessageEndEvent)
    aborted = message_end.message
    assert isinstance(aborted, AssistantMessage)
    assert aborted == AssistantMessage(
        content=(TextContent(text="partial"),),
        stop_reason="aborted",
        error_message="Cancelled",
    )
    attempt_end = next(
        event for event in sink.events if isinstance(event, AssistantAttemptEndEvent)
    )
    assert attempt_end == AssistantAttemptEndEvent(
        attempt=attempt(status="cancelled", chunks=(TextChunk(text="partial"),))
    )
    assert sink.events[-3:] == [
        StepEndEvent(run_id=RUN_ID, turn_id=TURN_ID, step_id="step-1", reason="cancelled"),
        TurnEndEvent(run_id=RUN_ID, turn_id=TURN_ID, reason="cancelled"),
        AgentEndEvent(messages=(aborted,), run_id=RUN_ID),
    ]
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
            id_generator=SequentialIdGenerator(),
        )

    assert sink.events[-3:] == [
        StepEndEvent(run_id=RUN_ID, turn_id=TURN_ID, step_id="step-1", reason="model_error"),
        TurnEndEvent(run_id=RUN_ID, turn_id=TURN_ID, reason="failed"),
        AgentEndEvent(messages=(), run_id=RUN_ID),
    ]
