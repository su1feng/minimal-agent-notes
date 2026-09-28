"""Assemble a provider-neutral model stream into an assistant message."""

from minimal_harness.model_stream import (
    FinishChunk,
    ModelStreamChunk,
    ProviderReplayState,
    TextChunk,
    ToolCallChunk,
    UsageChunk,
)
from minimal_harness.types import AssistantMessage, TextContent, ToolCall


class AssistantMessageAssembler:
    def __init__(self) -> None:
        self._content: list[TextContent | ToolCall] = []
        self._usage: UsageChunk | None = None
        self._finish: FinishChunk | None = None

    def push(self, chunk: ModelStreamChunk) -> None:
        if self._finish is not None:
            raise RuntimeError("assembler is already finished")

        if isinstance(chunk, TextChunk):
            self._append_text(chunk.text)
            return

        if isinstance(chunk, ToolCallChunk):
            self._content.append(chunk.tool_call)
            return

        if isinstance(chunk, UsageChunk):
            self._usage = chunk
            return

        if isinstance(chunk, FinishChunk):
            self._finish = chunk
            return

        raise AssertionError(f"Unsupported model stream chunk: {chunk!r}")

    @property
    def usage(self) -> UsageChunk | None:
        return self._usage

    @property
    def replay_state(self) -> ProviderReplayState | None:
        if self._finish is None:
            return None
        return self._finish.replay_state

    def interrupted_message(self) -> AssistantMessage | None:
        safe_content = tuple(
            block
            for block in self._content
            if isinstance(block, TextContent) and block.text.strip()
        )

        if not safe_content:
            return None
        return AssistantMessage(
            content=safe_content,
            stop_reason="aborted",
            error_message="Cancelled",
        )

    def message(self) -> AssistantMessage:
        if self._finish is None:
            raise RuntimeError("cannot create a formal message before finish")

        return AssistantMessage(
            content=tuple(self._content),
            stop_reason=self._finish.stop_reason,
            error_message=self._finish.error_message
        )

    def _append_text(self, text: str) -> None:
        if self._content and isinstance(self._content[-1], TextContent):
            previous = self._content[-1]
            self._content[-1] = TextContent(text=previous.text + text)
            return

        self._content.append(TextContent(text=text))
