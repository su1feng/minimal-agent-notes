"""Day 02 contract tests for observable agent-loop lifecycle events."""

import asyncio
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
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    TurnEndEvent,
    TurnStartEvent,
)
from src.model_stream import FinishChunk, ModelStreamChunk, TextChunk, ToolCallChunk
from src.types import (
    AssistantMessage,
    CancellationToken,
    ModelFormatError,
    TextContent,
    ToolCall,
    ToolExecutionResult,
    ToolResultMessage,
    UserMessage,
)
from tests.fakes import (
    FakeCancellationToken,
    ScriptedModel,
    ScriptedToolExecutor,
    SequentialIdGenerator,
)

RUN_ID = "run-1"
TURN_ID = "turn-1"


@dataclass(slots=True)
class RecordingEventSink:
    """Record events only after the awaited sink call is reached."""

    events: list[AgentEvent] = field(default_factory=list)

    async def emit(self, event: AgentEvent) -> None:
        self.events.append(event)


def answer(text: str) -> AssistantMessage:
    return AssistantMessage(content=(TextContent(text=text),), stop_reason="stop")


def tool_request(call: ToolCall) -> AssistantMessage:
    return AssistantMessage(content=(call,), stop_reason="toolUse")


def attempt(
    *,
    attempt_id: str,
    step_id: str,
    status: AttemptStatus,
    chunks: tuple[ModelStreamChunk, ...],
) -> AssistantAttempt:
    return AssistantAttempt(
        attempt_id=attempt_id,
        run_id=RUN_ID,
        turn_id=TURN_ID,
        step_id=step_id,
        status=status,
        chunks=chunks,
    )


@pytest.mark.asyncio
async def test_emits_a_closed_lifecycle_for_a_direct_answer() -> None:
    initial = (UserMessage(content="hello"),)
    final = answer("hi")
    sink = RecordingEventSink()

    result = await run_agent_loop(
        model=ScriptedModel([final]),
        tool_executor=ScriptedToolExecutor([]),
        initial_messages=initial,
        event_sink=sink,
        id_generator=SequentialIdGenerator(),
    )

    assert sink.events == [
        AgentStartEvent(run_id=RUN_ID),
        TurnStartEvent(run_id=RUN_ID, turn_id=TURN_ID),
        StepStartEvent(run_id=RUN_ID, turn_id=TURN_ID, step_id="step-1"),
        AssistantAttemptStartEvent(
            attempt_id="attempt-1", run_id=RUN_ID, turn_id=TURN_ID, step_id="step-1"
        ),
        MessageStartEvent(message=AssistantDraft(text="")),
        MessageUpdateEvent(message=AssistantDraft(text="hi"), delta="hi"),
        MessageEndEvent(message=final),
        AssistantAttemptEndEvent(
            attempt=attempt(
                attempt_id="attempt-1",
                step_id="step-1",
                status="completed",
                chunks=(TextChunk(text="hi"), FinishChunk(stop_reason="stop")),
            )
        ),
        StepEndEvent(run_id=RUN_ID, turn_id=TURN_ID, step_id="step-1", reason="completed"),
        TurnEndEvent(run_id=RUN_ID, turn_id=TURN_ID, reason="completed"),
        AgentEndEvent(messages=result, run_id=RUN_ID),
    ]


@pytest.mark.asyncio
async def test_emits_tool_events_before_the_corresponding_result_message() -> None:
    initial = (UserMessage(content="read README"),)
    call = ToolCall(id="call-1", name="read", arguments={"path": "README.md"})
    request = tool_request(call)
    execution_result = ToolExecutionResult(
        content="contents",
        details={"path": "README.md"},
    )
    result_message = ToolResultMessage(
        tool_call_id=call.id,
        tool_name=call.name,
        content=execution_result.content,
        details=execution_result.details,
        is_error=False,
    )
    final = answer("done")
    sink = RecordingEventSink()

    result = await run_agent_loop(
        model=ScriptedModel([request, final]),
        tool_executor=ScriptedToolExecutor([execution_result]),
        initial_messages=initial,
        event_sink=sink,
        id_generator=SequentialIdGenerator(),
    )

    assert sink.events == [
        AgentStartEvent(run_id=RUN_ID),
        TurnStartEvent(run_id=RUN_ID, turn_id=TURN_ID),
        StepStartEvent(run_id=RUN_ID, turn_id=TURN_ID, step_id="step-1"),
        AssistantAttemptStartEvent(
            attempt_id="attempt-1", run_id=RUN_ID, turn_id=TURN_ID, step_id="step-1"
        ),
        MessageStartEvent(message=request),
        MessageEndEvent(message=request),
        AssistantAttemptEndEvent(
            attempt=attempt(
                attempt_id="attempt-1",
                step_id="step-1",
                status="completed",
                chunks=(
                    ToolCallChunk(tool_call=call),
                    FinishChunk(stop_reason="toolUse"),
                ),
            )
        ),
        ToolExecutionStartEvent(tool_call=call),
        ToolExecutionEndEvent(tool_call=call, result=execution_result),
        MessageStartEvent(message=result_message),
        MessageEndEvent(message=result_message),
        StepEndEvent(
            run_id=RUN_ID,
            turn_id=TURN_ID,
            step_id="step-1",
            reason="tool_results",
        ),
        StepStartEvent(run_id=RUN_ID, turn_id=TURN_ID, step_id="step-2"),
        AssistantAttemptStartEvent(
            attempt_id="attempt-2", run_id=RUN_ID, turn_id=TURN_ID, step_id="step-2"
        ),
        MessageStartEvent(message=AssistantDraft(text="")),
        MessageUpdateEvent(message=AssistantDraft(text="done"), delta="done"),
        MessageEndEvent(message=final),
        AssistantAttemptEndEvent(
            attempt=attempt(
                attempt_id="attempt-2",
                step_id="step-2",
                status="completed",
                chunks=(TextChunk(text="done"), FinishChunk(stop_reason="stop")),
            )
        ),
        StepEndEvent(run_id=RUN_ID, turn_id=TURN_ID, step_id="step-2", reason="completed"),
        TurnEndEvent(run_id=RUN_ID, turn_id=TURN_ID, reason="completed"),
        AgentEndEvent(messages=result, run_id=RUN_ID),
    ]


@pytest.mark.asyncio
async def test_tool_exception_is_observable_as_an_error_result() -> None:
    call = ToolCall(id="call-1", name="explode", arguments={})
    request = tool_request(call)
    final = answer("recovered")
    sink = RecordingEventSink()

    result = await run_agent_loop(
        model=ScriptedModel([request, final]),
        tool_executor=ScriptedToolExecutor([RuntimeError("boom")]),
        initial_messages=(),
        event_sink=sink,
        id_generator=SequentialIdGenerator(),
    )

    tool_end = next(event for event in sink.events if isinstance(event, ToolExecutionEndEvent))
    assert tool_end.tool_call is call
    assert tool_end.result == ToolExecutionResult(
        content="boom",
        details={"exception_type": "RuntimeError"},
        is_error=True,
    )
    result_message = result[-2]
    assert isinstance(result_message, ToolResultMessage)
    assert MessageEndEvent(message=result_message) in sink.events
    assert sink.events[-1] == AgentEndEvent(messages=result, run_id=RUN_ID)


@pytest.mark.asyncio
async def test_format_error_settles_its_attempt_before_the_next_step() -> None:
    feedback = UserMessage(content="Return valid output")
    final = answer("recovered")
    sink = RecordingEventSink()

    result = await run_agent_loop(
        model=ScriptedModel([ModelFormatError(feedback), final]),
        tool_executor=ScriptedToolExecutor([]),
        initial_messages=(),
        event_sink=sink,
        id_generator=SequentialIdGenerator(),
    )

    attempts = [
        event.attempt for event in sink.events if isinstance(event, AssistantAttemptEndEvent)
    ]
    assert [(item.attempt_id, item.step_id, item.status) for item in attempts] == [
        ("attempt-1", "step-1", "failed"),
        ("attempt-2", "step-2", "completed"),
    ]
    assert attempts[0].chunks == ()
    format_step_end = sink.events.index(
        StepEndEvent(
            run_id=RUN_ID,
            turn_id=TURN_ID,
            step_id="step-1",
            reason="format_error",
        )
    )
    feedback_start = sink.events.index(MessageStartEvent(message=feedback))
    next_step_start = sink.events.index(
        StepStartEvent(run_id=RUN_ID, turn_id=TURN_ID, step_id="step-2")
    )
    assert format_step_end < feedback_start < next_step_start
    assert result == (feedback, final)


@dataclass(slots=True)
class NotifyingCancellationToken:
    """Cancellation token that lets a cooperative test tool await cancellation."""

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
class BlockingTool:
    """Start once, then cooperate with cancellation instead of completing."""

    started: asyncio.Event = field(default_factory=asyncio.Event, init=False)

    async def execute(
        self,
        tool_call: ToolCall,
        signal: CancellationToken | None = None,
    ) -> ToolExecutionResult:
        del tool_call
        assert isinstance(signal, NotifyingCancellationToken)
        self.started.set()
        await signal.wait_cancelled()
        raise asyncio.CancelledError


@pytest.mark.asyncio
async def test_cancellation_during_a_tool_closes_promptly_without_result_events() -> None:
    token = NotifyingCancellationToken()
    call = ToolCall(id="call-1", name="wait", arguments={})
    request = tool_request(call)
    tool = BlockingTool()
    sink = RecordingEventSink()
    task = asyncio.create_task(
        run_agent_loop(
            model=ScriptedModel([request]),
            tool_executor=tool,
            initial_messages=(),
            signal=token,
            event_sink=sink,
            id_generator=SequentialIdGenerator(),
        )
    )

    await asyncio.wait_for(tool.started.wait(), timeout=0.1)
    token.cancel()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=0.1)

    assert sink.events == [
        AgentStartEvent(run_id=RUN_ID),
        TurnStartEvent(run_id=RUN_ID, turn_id=TURN_ID),
        StepStartEvent(run_id=RUN_ID, turn_id=TURN_ID, step_id="step-1"),
        AssistantAttemptStartEvent(
            attempt_id="attempt-1", run_id=RUN_ID, turn_id=TURN_ID, step_id="step-1"
        ),
        MessageStartEvent(message=request),
        MessageEndEvent(message=request),
        AssistantAttemptEndEvent(
            attempt=attempt(
                attempt_id="attempt-1",
                step_id="step-1",
                status="completed",
                chunks=(
                    ToolCallChunk(tool_call=call),
                    FinishChunk(stop_reason="toolUse"),
                ),
            )
        ),
        ToolExecutionStartEvent(tool_call=call),
        StepEndEvent(run_id=RUN_ID, turn_id=TURN_ID, step_id="step-1", reason="cancelled"),
        TurnEndEvent(run_id=RUN_ID, turn_id=TURN_ID, reason="cancelled"),
        AgentEndEvent(messages=(request,), run_id=RUN_ID),
    ]
    events_after_cancellation = tuple(sink.events)
    await asyncio.sleep(0)
    assert tuple(sink.events) == events_after_cancellation


@pytest.mark.asyncio
async def test_pre_cancelled_run_only_emits_the_lifecycle_boundary() -> None:
    token = FakeCancellationToken(cancelled=True)
    model = ScriptedModel([answer("must not run")])
    tools = ScriptedToolExecutor([])
    sink = RecordingEventSink()

    with pytest.raises(asyncio.CancelledError):
        await run_agent_loop(
            model=model,
            tool_executor=tools,
            initial_messages=(),
            signal=token,
            event_sink=sink,
            id_generator=SequentialIdGenerator(),
        )

    assert model.calls == []
    assert tools.calls == []
    assert sink.events == [
        AgentStartEvent(run_id=RUN_ID),
        TurnStartEvent(run_id=RUN_ID, turn_id=TURN_ID),
        TurnEndEvent(run_id=RUN_ID, turn_id=TURN_ID, reason="cancelled"),
        AgentEndEvent(messages=(), run_id=RUN_ID),
    ]


@pytest.mark.asyncio
async def test_step_limit_error_still_ends_the_lifecycle() -> None:
    call = ToolCall(id="call-1", name="work", arguments={})
    request = tool_request(call)
    execution_result = ToolExecutionResult(content="done")
    result_message = ToolResultMessage(
        tool_call_id=call.id,
        tool_name=call.name,
        content="done",
    )
    sink = RecordingEventSink()

    with pytest.raises(RuntimeError, match="step limit exceeded"):
        await run_agent_loop(
            model=ScriptedModel([request]),
            tool_executor=ScriptedToolExecutor([execution_result]),
            initial_messages=(),
            max_steps=1,
            event_sink=sink,
            id_generator=SequentialIdGenerator(),
        )

    assert sink.events[-2:] == [
        TurnEndEvent(run_id=RUN_ID, turn_id=TURN_ID, reason="step_limit"),
        AgentEndEvent(messages=(request, result_message), run_id=RUN_ID),
    ]
    assert sum(isinstance(event, AgentEndEvent) for event in sink.events) == 1


@pytest.mark.asyncio
async def test_model_error_after_tool_result_keeps_prior_messages_without_a_final_answer() -> None:
    initial = (UserMessage(content="read file"),)
    call = ToolCall(id="call-1", name="read", arguments={"path": "README.md"})
    request = tool_request(call)
    tool_result = ToolExecutionResult(content="file contents")
    result_message = ToolResultMessage(
        tool_call_id=call.id,
        tool_name=call.name,
        content=tool_result.content,
    )
    failed_answer = AssistantMessage(
        content=(TextContent(text="The file"),),
        stop_reason="error",
        error_message="provider disconnected",
    )
    model = ScriptedModel([request, failed_answer])
    sink = RecordingEventSink()

    with pytest.raises(RuntimeError, match="provider disconnected"):
        await run_agent_loop(
            model=model,
            tool_executor=ScriptedToolExecutor([tool_result]),
            initial_messages=initial,
            event_sink=sink,
            id_generator=SequentialIdGenerator(),
        )

    assert model.calls[1] == (*initial, request, result_message)
    failed_attempt = next(
        event
        for event in sink.events
        if isinstance(event, AssistantAttemptEndEvent) and event.attempt.status == "failed"
    )
    assert failed_attempt.attempt.step_id == "step-2"
    assert sink.events[-2:] == [
        TurnEndEvent(run_id=RUN_ID, turn_id=TURN_ID, reason="failed"),
        AgentEndEvent(messages=(*initial, request, result_message), run_id=RUN_ID),
    ]
    assert MessageEndEvent(message=failed_answer) not in sink.events
