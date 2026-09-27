"""Minimal provider/tool loop with Day 02 events and streaming support."""

import asyncio
from collections.abc import AsyncIterator, Sequence

from minimal_harness.events import (
    AgentEndEvent,
    AgentEvent,
    AgentEventSink,
    AgentStartEvent,
    AssistantDraft,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
)
from minimal_harness.types import (
    AgentMessage,
    AssistantMessage,
    AssistantStreamEnd,
    AssistantStreamEvent,
    AssistantTextDelta,
    CancellationToken,
    ModelAdapter,
    ModelFormatError,
    TextContent,
    ToolCall,
    ToolExecutionResult,
    ToolExecutor,
    ToolResultMessage,
)


async def run_agent_loop(
    *,
    model: ModelAdapter,
    tool_executor: ToolExecutor,
    initial_messages: Sequence[AgentMessage],
    signal: CancellationToken | None = None,
    max_steps: int = 8,
    max_consecutive_format_errors: int = 3,
    event_sink: AgentEventSink | None = None,
) -> tuple[AgentMessage, ...]:
    """Run model turns until a final, failed, or aborted assistant message."""
    if max_steps <= 0:
        raise ValueError("max_steps must be positive")
    if max_consecutive_format_errors < 0:
        raise ValueError("max_consecutive_format_errors must be non-negative")

    messages = list(initial_messages)
    consecutive_format_errors = 0

    await _emit(event_sink, AgentStartEvent())
    try:
        for _ in range(max_steps):
            _raise_if_cancelled(signal)
            try:
                assistant = await _stream_assistant_response(
                    model.stream(tuple(messages), signal),
                    messages,
                    signal,
                    event_sink,
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
                    return tuple(messages)
                continue

            consecutive_format_errors = 0

            if assistant.stop_reason in {"error", "aborted"}:
                return tuple(messages)

            tool_calls = tuple(block for block in assistant.content if isinstance(block, ToolCall))

            if assistant.stop_reason == "stop":
                if tool_calls:
                    raise ValueError("stop response must not contain a ToolCall")
                return tuple(messages)

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

        raise RuntimeError("step limit exceeded")
    finally:
        await _emit(event_sink, AgentEndEvent(messages=tuple(messages)))


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


async def _stream_assistant_response(
    stream: AsyncIterator[AssistantStreamEvent],
    messages: list[AgentMessage],
    signal: CancellationToken | None,
    event_sink: AgentEventSink | None,
) -> AssistantMessage:
    text = ""
    started = False
    try:
        async for stream_event in stream:
            _raise_if_cancelled(signal)
            if isinstance(stream_event, AssistantTextDelta):
                if not started:
                    await _emit(
                        event_sink,
                        MessageStartEvent(message=AssistantDraft(text="")),
                    )
                    started = True
                text += stream_event.delta
                await _emit(
                    event_sink,
                    MessageUpdateEvent(
                        message=AssistantDraft(text=text),
                        delta=stream_event.delta,
                    ),
                )
                continue

            if isinstance(stream_event, AssistantStreamEnd):
                final = stream_event.message
                if started:
                    messages.append(final)
                    await _emit(event_sink, MessageEndEvent(message=final))
                else:
                    await _append_message(messages, final, event_sink)
                return final

        raise ValueError("stream ended without an AssistantStreamEnd")
    except asyncio.CancelledError:
        content = (TextContent(text=text),) if text else ()
        aborted = AssistantMessage(
            content=content,
            stop_reason="aborted",
            error_message="Cancelled",
        )
        if started:
            messages.append(aborted)
            await _emit(event_sink, MessageEndEvent(message=aborted))
        else:
            await _append_message(messages, aborted, event_sink)
        raise


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
