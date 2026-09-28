"""Classify the final result of one model-stream attempt."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from minimal_harness.assistant_message_assembler import AssistantMessageAssembler
from minimal_harness.model_stream import ModelStreamChunk
from minimal_harness.types import AssistantMessage

type AttemptStatus = Literal["completed", "cancelled", "failed"]


@dataclass(frozen=True, slots=True)
class AssistantAttempt:
    """Evidence captured from one request to a model."""

    attempt_id: str
    run_id: str
    status: AttemptStatus
    chunks: tuple[ModelStreamChunk, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "chunks", tuple(self.chunks))


@dataclass(frozen=True, slots=True)
class AttemptResult:
    """The attempt evidence and an optional safe message for history."""

    attempt: AssistantAttempt
    message: AssistantMessage | None


def finalize_attempt(
    *,
    attempt_id: str,
    run_id: str,
    status: AttemptStatus,
    chunks: Sequence[ModelStreamChunk],
    assembler: AssistantMessageAssembler,
) -> AttemptResult:
    """Create the durable facts allowed by a finished model attempt."""
    attempt = AssistantAttempt(
        attempt_id=attempt_id,
        run_id=run_id,
        status=status,
        chunks=tuple(chunks),
    )

    if status == "completed":
        message = assembler.message()
        if message.stop_reason in {"error", "aborted"}:
            raise ValueError("A failed or aborted model response cannot be completed")
        return AttemptResult(
            attempt=attempt,
            message=message,
        )

    if status == "cancelled":
        return AttemptResult(
            attempt=attempt,
            message=assembler.interrupted_message(),
        )

    return AttemptResult(
        attempt=attempt,
        message=None,
    )
