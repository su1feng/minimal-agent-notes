"""Stable identifiers and terminal reasons for runtime lifecycle boundaries."""

from typing import Literal, Protocol
from uuid import uuid4

type RunId = str
type TurnId = str
type StepId = str
type LifecycleIdKind = Literal["run", "turn", "step", "attempt"]

type StepEndReason = Literal[
    "completed",
    "tool_results",
    "format_error",
    "model_error",
    "cancelled",
]

type TurnEndReason = Literal[
    "completed",
    "failed",
    "cancelled",
    "step_limit",
]


class IdGenerator(Protocol):
    def new_id(self, kind: LifecycleIdKind) -> str: ...


class UUIDIdGenerator:
    """Generate process-independent identifiers for production runs."""

    def new_id(self, kind: LifecycleIdKind) -> str:
        return f"{kind}-{uuid4()}"
