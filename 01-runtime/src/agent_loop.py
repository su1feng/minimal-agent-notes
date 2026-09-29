"""Minimal provider/tool loop with events and streaming support."""

import asyncio
from collections.abc import Sequence

from .assistant_attempt import AttemptResult, AttemptStatus, finalize_attempt
from .assistant_message_assembler import AssistantMessageAssembler
from .events import (
    AgentEndEvent,
    AgentEvent,
    AgentEventSink,
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
from .lifecycle import IdGenerator, StepEndReason, TurnEndReason, UUIDIdGenerator
from .model_stream import ModelStreamChunk, TextChunk
from .types import (
    AgentMessage,
    AssistantMessage,
    CancellationToken,
    ModelAdapter,
    ModelFormatError,
    ToolCall,
    ToolExecutionResult,
    ToolExecutor,
    ToolResultMessage,
)


class ModelRequestError(RuntimeError):
    """The model request ended in an error."""


class StepLimitExceeded(RuntimeError):
    """The run exhausted its model-step budget."""


async def run_agent_loop(
    *,
    model: ModelAdapter,
    tool_executor: ToolExecutor,
    initial_messages: Sequence[AgentMessage],
    signal: CancellationToken | None = None,
    max_steps: int = 8,
    max_consecutive_format_errors: int = 3,
    event_sink: AgentEventSink | None = None,
    id_generator: IdGenerator | None = None,
) -> tuple[AgentMessage, ...]:
    """Run model turns until a final, failed, or aborted assistant message."""
    if max_steps <= 0:
        raise ValueError("max_steps must be positive")
    if max_consecutive_format_errors < 0:
        raise ValueError("max_consecutive_format_errors must be non-negative")

    ids = id_generator or UUIDIdGenerator()
    run_id = ids.new_id("run")
    turn_id = ids.new_id("turn")
    messages = list(initial_messages)
    turn_reason: TurnEndReason = "failed"

    await _emit(event_sink, AgentStartEvent(run_id=run_id))
    await _emit(event_sink, TurnStartEvent(run_id=run_id, turn_id=turn_id))
    try:
        turn_reason = await _run_turn(
            model=model,
            tool_executor=tool_executor,
            messages=messages,
            signal=signal,
            max_steps=max_steps,
            max_consecutive_format_errors=max_consecutive_format_errors,
            event_sink=event_sink,
            id_generator=ids,
            run_id=run_id,
            turn_id=turn_id,
        )
        return tuple(messages)
    except StepLimitExceeded:
        turn_reason = "step_limit"
        raise
    except asyncio.CancelledError:
        turn_reason = "cancelled"
        raise
    finally:
        await _emit(
            event_sink,
            TurnEndEvent(run_id=run_id, turn_id=turn_id, reason=turn_reason),
        )
        await _emit(
            event_sink,
            AgentEndEvent(messages=tuple(messages), run_id=run_id),
        )


async def _run_turn(
    *,
    model: ModelAdapter,
    tool_executor: ToolExecutor,
    messages: list[AgentMessage],
    signal: CancellationToken | None,
    max_steps: int,
    max_consecutive_format_errors: int,
    event_sink: AgentEventSink | None,
    id_generator: IdGenerator,
    run_id: str,
    turn_id: str,
) -> TurnEndReason:
    consecutive_format_errors = 0

    for _ in range(max_steps):
        _raise_if_cancelled(signal)
        step_id = id_generator.new_id("step")
        try:
            reason = await _run_step(
                model=model,
                tool_executor=tool_executor,
                messages=messages,
                signal=signal,
                event_sink=event_sink,
                id_generator=id_generator,
                run_id=run_id,
                turn_id=turn_id,
                step_id=step_id,
            )
        except ModelFormatError as error:
            _raise_if_cancelled(signal)
            consecutive_format_errors += 1
            await _append_message(messages, error.feedback, event_sink)
            reached_limit = (
                max_consecutive_format_errors > 0
                and consecutive_format_errors >= max_consecutive_format_errors
            )
            if reached_limit:
                await _append_message(
                    messages,
                    AssistantMessage(
                        content=(), stop_reason="error", error_message="RepeatedFormatError"
                    ),
                    event_sink,
                )
                return "failed"
            continue

        consecutive_format_errors = 0
        if reason == "completed":
            return "completed"

    raise StepLimitExceeded("step limit exceeded")


async def _run_step(
    *,
    model: ModelAdapter,
    tool_executor: ToolExecutor,
    messages: list[AgentMessage],
    signal: CancellationToken | None,
    event_sink: AgentEventSink | None,
    id_generator: IdGenerator,
    run_id: str,
    turn_id: str,
    step_id: str,
) -> StepEndReason:
    await _emit(
        event_sink,
        StepStartEvent(run_id=run_id, turn_id=turn_id, step_id=step_id),
    )
    reason: StepEndReason = "model_error"
    try:
        attempt_id = id_generator.new_id("attempt")
        attempt = await _run_assistant_attempt(
            model=model,
            messages=messages,
            signal=signal,
            event_sink=event_sink,
            attempt_id=attempt_id,
            run_id=run_id,
            turn_id=turn_id,
            step_id=step_id,
        )
        assistant = attempt.message
        if assistant is None:
            raise AssertionError("completed assistant attempt must contain a message")

        tool_calls = tuple(block for block in assistant.content if isinstance(block, ToolCall))
        if assistant.stop_reason == "stop":
            if tool_calls:
                raise ValueError("stop response must not contain a ToolCall")
            reason = "completed"
            return reason

        if not tool_calls:
            raise ValueError("toolUse response must contain at least one ToolCall")

        for tool_call in tool_calls:
            _raise_if_cancelled(signal)
            await _emit(event_sink, ToolExecutionStartEvent(tool_call=tool_call))
            result = await _execute_tool(tool_executor, tool_call, signal)
            await _emit(
                event_sink,
                ToolExecutionEndEvent(tool_call=tool_call, result=result),
            )
            await _append_message(
                messages,
                _to_tool_result_message(tool_call, result),
                event_sink,
            )

        reason = "tool_results"
        return reason
    except ModelFormatError:
        reason = "format_error"
        raise
    except asyncio.CancelledError:
        reason = "cancelled"
        raise
    finally:
        await _emit(
            event_sink,
            StepEndEvent(
                run_id=run_id,
                turn_id=turn_id,
                step_id=step_id,
                reason=reason,
            ),
        )


async def _emit(event_sink: AgentEventSink | None, event: AgentEvent) -> None:
    if event_sink is not None:
        await event_sink.emit(event)


async def _append_message(
    messages: list[AgentMessage],
    message: AgentMessage,
    event_sink: AgentEventSink | None,
) -> None:
    await _emit(event_sink, MessageStartEvent(message=message))
    messages.append(message)
    await _emit(event_sink, MessageEndEvent(message=message))


async def _run_assistant_attempt(
    *,
    model: ModelAdapter,
    messages: list[AgentMessage],
    signal: CancellationToken | None,
    event_sink: AgentEventSink | None,
    attempt_id: str,
    run_id: str,
    turn_id: str,
    step_id: str,
) -> AttemptResult:
    assembler = AssistantMessageAssembler()
    chunks: list[ModelStreamChunk] = []
    text = ""
    started = False
    await _emit(
        event_sink,
        AssistantAttemptStartEvent(
            attempt_id=attempt_id,
            run_id=run_id,
            turn_id=turn_id,
            step_id=step_id,
        ),
    )
    try:
        async for chunk in model.stream(tuple(messages), signal):
            _raise_if_cancelled(signal)
            chunks.append(chunk)
            assembler.push(chunk)
            if isinstance(chunk, TextChunk):
                if not started:
                    await _emit(
                        event_sink,
                        MessageStartEvent(message=AssistantDraft(text="")),
                    )
                    started = True
                text += chunk.text
                await _emit(
                    event_sink,
                    MessageUpdateEvent(
                        message=AssistantDraft(text=text),
                        delta=chunk.text,
                    ),
                )
    except asyncio.CancelledError:
        await _settle_assistant_attempt(
            attempt_id=attempt_id,
            run_id=run_id,
            turn_id=turn_id,
            step_id=step_id,
            status="cancelled",
            chunks=chunks,
            assembler=assembler,
            messages=messages,
            draft_started=started,
            event_sink=event_sink,
        )
        raise
    except Exception:
        await _settle_assistant_attempt(
            attempt_id=attempt_id,
            run_id=run_id,
            turn_id=turn_id,
            step_id=step_id,
            status="failed",
            chunks=chunks,
            assembler=assembler,
            messages=messages,
            draft_started=started,
            event_sink=event_sink,
        )
        raise

    try:
        final = assembler.message()
    except Exception:
        await _settle_assistant_attempt(
            attempt_id=attempt_id,
            run_id=run_id,
            turn_id=turn_id,
            step_id=step_id,
            status="failed",
            chunks=chunks,
            assembler=assembler,
            messages=messages,
            draft_started=started,
            event_sink=event_sink,
        )
        raise
    if final.stop_reason == "error":
        await _settle_assistant_attempt(
            attempt_id=attempt_id,
            run_id=run_id,
            turn_id=turn_id,
            step_id=step_id,
            status="failed",
            chunks=chunks,
            assembler=assembler,
            messages=messages,
            draft_started=started,
            event_sink=event_sink,
        )
        raise ModelRequestError(final.error_message or "model request failed")
    if final.stop_reason == "aborted":
        await _settle_assistant_attempt(
            attempt_id=attempt_id,
            run_id=run_id,
            turn_id=turn_id,
            step_id=step_id,
            status="cancelled",
            chunks=chunks,
            assembler=assembler,
            messages=messages,
            draft_started=started,
            event_sink=event_sink,
        )
        raise asyncio.CancelledError

    return await _settle_assistant_attempt(
        attempt_id=attempt_id,
        run_id=run_id,
        turn_id=turn_id,
        step_id=step_id,
        status="completed",
        chunks=chunks,
        assembler=assembler,
        messages=messages,
        draft_started=started,
        event_sink=event_sink,
    )


async def _settle_assistant_attempt(
    *,
    attempt_id: str,
    run_id: str,
    turn_id: str,
    step_id: str,
    status: AttemptStatus,
    chunks: list[ModelStreamChunk],
    assembler: AssistantMessageAssembler,
    messages: list[AgentMessage],
    draft_started: bool,
    event_sink: AgentEventSink | None,
) -> AttemptResult:
    result = finalize_attempt(
        attempt_id=attempt_id,
        run_id=run_id,
        turn_id=turn_id,
        step_id=step_id,
        status=status,
        chunks=chunks,
        assembler=assembler,
    )
    await _commit_attempt_message(messages, result, draft_started, event_sink)
    await _emit(event_sink, AssistantAttemptEndEvent(attempt=result.attempt))
    return result


async def _commit_attempt_message(
    messages: list[AgentMessage],
    result: AttemptResult,
    draft_started: bool,
    event_sink: AgentEventSink | None,
) -> None:
    message = result.message
    if message is None:
        return
    if draft_started:
        messages.append(message)
        await _emit(event_sink, MessageEndEvent(message=message))
        return
    await _append_message(messages, message, event_sink)


def _raise_if_cancelled(signal: CancellationToken | None) -> None:
    if signal is not None and signal.is_cancelled():
        raise asyncio.CancelledError


async def _execute_tool(
    executor: ToolExecutor,
    tool_call: ToolCall,
    signal: CancellationToken | None,
) -> ToolExecutionResult:
    try:
        return await executor.execute(tool_call, signal)
    except Exception as error:
        return ToolExecutionResult(
            content=str(error),
            details={"exception_type": type(error).__name__},
            is_error=True,
        )


def _to_tool_result_message(
    tool_call: ToolCall,
    result: ToolExecutionResult,
) -> ToolResultMessage:
    return ToolResultMessage(
        tool_call_id=tool_call.id,
        tool_name=tool_call.name,
        content=result.content,
        details=result.details,
        is_error=result.is_error,
    )
