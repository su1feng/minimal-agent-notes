"""Behavior-driven alternative adapters used to prove protocol substitutability."""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

from src.model_stream import FinishChunk, ModelStreamChunk, TextChunk, ToolCallChunk
from src.types import (
    AgentMessage,
    CancellationToken,
    ToolCall,
    ToolExecutionResult,
    ToolResultMessage,
    UserMessage,
)


@dataclass(slots=True)
class RuleBasedEchoModel:
    """Choose the next response from transcript state instead of a script."""

    calls: list[tuple[AgentMessage, ...]] = field(default_factory=list, init=False)
    signals: list[CancellationToken | None] = field(default_factory=list, init=False)

    async def stream(
        self,
        messages: Sequence[AgentMessage],
        signal: CancellationToken | None = None,
    ) -> AsyncIterator[ModelStreamChunk]:
        snapshot = tuple(messages)
        self.calls.append(snapshot)
        self.signals.append(signal)

        if snapshot and isinstance(snapshot[-1], ToolResultMessage):
            result = snapshot[-1]
            yield TextChunk(text=f"echo: {result.content}")
            yield FinishChunk(stop_reason="stop")
            return

        user_message = next(
            (message for message in reversed(snapshot) if isinstance(message, UserMessage)),
            None,
        )
        if user_message is None:
            yield FinishChunk(
                stop_reason="error",
                error_message="No user message found",
            )
            return

        yield ToolCallChunk(
            tool_call=ToolCall(
                id="echo-1",
                name="echo",
                arguments={"text": user_message.content},
            )
        )
        yield FinishChunk(stop_reason="toolUse")


@dataclass(slots=True)
class EchoToolExecutor:
    """Execute one concrete echo tool from its name and validated arguments."""

    calls: list[ToolCall] = field(default_factory=list, init=False)
    signals: list[CancellationToken | None] = field(default_factory=list, init=False)

    async def execute(
        self,
        tool_call: ToolCall,
        signal: CancellationToken | None = None,
    ) -> ToolExecutionResult:
        self.calls.append(tool_call)
        self.signals.append(signal)

        if tool_call.name != "echo":
            return ToolExecutionResult(
                content=f"unsupported tool: {tool_call.name}",
                is_error=True,
            )

        text = tool_call.arguments.get("text")
        if not isinstance(text, str):
            return ToolExecutionResult(
                content="echo.text must be a string",
                is_error=True,
            )

        return ToolExecutionResult(
            content=text,
            details={"length": len(text)},
        )
