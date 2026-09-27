"""Minimal provider/tool loop for the Day 01 exercise."""

import asyncio
from collections.abc import Sequence

from minimal_harness.types import (
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


async def run_agent_loop(
    *,
    model: ModelAdapter,
    tool_executor: ToolExecutor,
    initial_messages: Sequence[AgentMessage],
    signal: CancellationToken | None = None,
    max_steps: int = 8,
    max_consecutive_format_errors: int = 3,
) -> tuple[AgentMessage, ...]:
    """Run model turns until a final, failed, or aborted assistant message."""
    if max_steps <= 0:
        raise ValueError("max_steps must be positive")
    if max_consecutive_format_errors < 0:
        raise ValueError("max_consecutive_format_errors must be non-negative")

    messages = list(initial_messages)
    consecutive_format_errors = 0

    for _ in range(max_steps):
        _raise_if_cancelled(signal)
        try:
            assistant = await model.query(tuple(messages), signal)
        except ModelFormatError as error:
            _raise_if_cancelled(signal)
            consecutive_format_errors += 1
            messages.append(error.feedback)
            reached_limit = (
                max_consecutive_format_errors > 0
                and consecutive_format_errors >= max_consecutive_format_errors
            )
            if reached_limit:
                messages.append(
                    AssistantMessage(
                        content=(), stop_reason="error", error_message="RepeatedFormatError"
                    )
                )
                return tuple(messages)
            continue

        _raise_if_cancelled(signal)
        consecutive_format_errors = 0
        messages.append(assistant)

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
            result = await _execute_tool(tool_executor, tool_call, signal)
            messages.append(_to_tool_result_message(tool_call, result))

    raise RuntimeError("step limit exceeded")


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
