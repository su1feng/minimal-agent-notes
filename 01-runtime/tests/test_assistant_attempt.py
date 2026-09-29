import pytest

from src.assistant_attempt import finalize_attempt
from src.assistant_message_assembler import AssistantMessageAssembler
from src.model_stream import FinishChunk, TextChunk, ToolCallChunk
from src.types import AssistantMessage, TextContent, ToolCall


def test_completed_attempt_contains_evidence_and_a_formal_message() -> None:
    chunks = (TextChunk(text="Hello"), FinishChunk(stop_reason="stop"))
    assembler = AssistantMessageAssembler()
    for chunk in chunks:
        assembler.push(chunk)

    result = finalize_attempt(
        attempt_id="attempt-1",
        run_id="run-1",
        turn_id="turn-1",
        step_id="step-1",
        status="completed",
        chunks=chunks,
        assembler=assembler,
    )

    assert result.message == AssistantMessage(
        content=(TextContent(text="Hello"),),
        stop_reason="stop",
    )
    assert result.attempt.attempt_id == "attempt-1"
    assert result.attempt.run_id == "run-1"
    assert result.attempt.turn_id == "turn-1"
    assert result.attempt.step_id == "step-1"
    assert result.attempt.status == "completed"
    assert result.attempt.chunks == chunks


def test_cancelled_attempt_only_projects_safe_text_into_its_message() -> None:
    tool_call = ToolCall(id="call-1", name="write", arguments={"path": "notes.txt"})
    chunks = (TextChunk(text="Starting."), ToolCallChunk(tool_call=tool_call))
    assembler = AssistantMessageAssembler()
    for chunk in chunks:
        assembler.push(chunk)

    result = finalize_attempt(
        attempt_id="attempt-2",
        run_id="run-1",
        turn_id="turn-1",
        step_id="step-1",
        status="cancelled",
        chunks=chunks,
        assembler=assembler,
    )

    assert result.message == AssistantMessage(
        content=(TextContent(text="Starting."),),
        stop_reason="aborted",
        error_message="Cancelled",
    )
    assert result.attempt.chunks == chunks


def test_failed_attempt_has_evidence_but_no_message() -> None:
    chunks = (TextChunk(text="partial"),)
    assembler = AssistantMessageAssembler()
    for chunk in chunks:
        assembler.push(chunk)

    result = finalize_attempt(
        attempt_id="attempt-3",
        run_id="run-1",
        turn_id="turn-1",
        step_id="step-1",
        status="failed",
        chunks=chunks,
        assembler=assembler,
    )

    assert result.message is None
    assert result.attempt.status == "failed"
    assert result.attempt.chunks == chunks


def test_model_error_is_recorded_as_a_failed_attempt_without_a_message() -> None:
    chunks = (
        TextChunk(text="Partial answer"),
        FinishChunk(stop_reason="error", error_message="Provider disconnected"),
    )
    assembler = AssistantMessageAssembler()
    for chunk in chunks:
        assembler.push(chunk)

    result = finalize_attempt(
        attempt_id="attempt-4",
        run_id="run-1",
        turn_id="turn-1",
        step_id="step-1",
        status="failed",
        chunks=chunks,
        assembler=assembler,
    )

    assert result.message is None
    assert result.attempt.status == "failed"
    assert result.attempt.chunks == chunks


def test_model_error_cannot_be_classified_as_a_completed_attempt() -> None:
    chunks = (FinishChunk(stop_reason="error", error_message="Provider disconnected"),)
    assembler = AssistantMessageAssembler()
    for chunk in chunks:
        assembler.push(chunk)

    with pytest.raises(ValueError):
        finalize_attempt(
            attempt_id="attempt-5",
            run_id="run-1",
            turn_id="turn-1",
            step_id="step-1",
            status="completed",
            chunks=chunks,
            assembler=assembler,
        )


def test_completed_tool_call_is_a_formal_message_for_the_next_model_request() -> None:
    tool_call = ToolCall(id="call-2", name="weather", arguments={"city": "Shanghai"})
    chunks = (ToolCallChunk(tool_call=tool_call), FinishChunk(stop_reason="toolUse"))
    assembler = AssistantMessageAssembler()
    for chunk in chunks:
        assembler.push(chunk)

    result = finalize_attempt(
        attempt_id="attempt-6",
        run_id="run-1",
        turn_id="turn-1",
        step_id="step-1",
        status="completed",
        chunks=chunks,
        assembler=assembler,
    )

    assert result.message == AssistantMessage(content=(tool_call,), stop_reason="toolUse")
