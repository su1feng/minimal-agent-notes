from dataclasses import FrozenInstanceError, dataclass

import pytest

from src.assistant_message_assembler import AssistantMessageAssembler
from src.model_stream import (
    FinishChunk,
    ProviderReplayState,
    TextChunk,
    ToolCallChunk,
    UsageChunk,
)
from src.types import AssistantMessage, TextContent, ToolCall


def test_model_stream_chunks_have_fixed_discriminators_and_preserve_data() -> None:
    tool_call = ToolCall(id="call-1", name="read", arguments={"path": "README.md"})

    text = TextChunk(text="Hello")
    tool = ToolCallChunk(tool_call=tool_call)
    usage = UsageChunk(input_tokens=3, output_tokens=5)
    finish = FinishChunk(stop_reason="toolUse")

    assert text.type == "text"
    assert text.text == "Hello"
    assert tool.type == "tool_call"
    assert tool.tool_call == tool_call
    assert usage.type == "usage"
    assert (usage.input_tokens, usage.output_tokens) == (3, 5)
    assert finish.type == "finish"
    assert finish.stop_reason == "toolUse"


def test_model_stream_chunks_are_immutable() -> None:
    chunk = TextChunk(text="Hello")

    with pytest.raises(FrozenInstanceError):
        chunk.text = "Changed"  # type: ignore[misc]


def test_replay_state_is_versioned_immutable_and_preserved_by_the_assembler() -> None:
    source = {"response_id": "provider-response-1"}
    replay_state = ProviderReplayState(
        provider="fake-provider",
        schema_version=1,
        payload=source,
    )
    source["response_id"] = "changed-after-construction"
    assembler = AssistantMessageAssembler()

    assembler.push(
        FinishChunk(
            stop_reason="stop",
            replay_state=replay_state,
        )
    )

    assert replay_state.payload == {"response_id": "provider-response-1"}
    assert assembler.replay_state == replay_state


def test_assembler_preserves_block_order_and_merges_adjacent_text() -> None:
    tool_call = ToolCall(id="call-1", name="read", arguments={"path": "README.md"})
    assembler = AssistantMessageAssembler()

    assembler.push(TextChunk(text="I will "))
    assembler.push(TextChunk(text="read it."))
    assembler.push(ToolCallChunk(tool_call=tool_call))
    assembler.push(TextChunk(text="Done."))
    assembler.push(UsageChunk(input_tokens=3, output_tokens=5))
    assembler.push(FinishChunk(stop_reason="toolUse"))

    assert assembler.message() == AssistantMessage(
        content=(
            TextContent(text="I will read it."),
            tool_call,
            TextContent(text="Done."),
        ),
        stop_reason="toolUse",
    )
    assert assembler.usage == UsageChunk(input_tokens=3, output_tokens=5)


def test_assembler_refuses_to_create_a_formal_message_before_finish() -> None:
    assembler = AssistantMessageAssembler()
    assembler.push(TextChunk(text="unfinished"))

    with pytest.raises(RuntimeError, match="finish"):
        assembler.message()


def test_assembler_rejects_chunks_after_finish() -> None:
    assembler = AssistantMessageAssembler()
    assembler.push(FinishChunk(stop_reason="stop"))

    with pytest.raises(RuntimeError, match="finished"):
        assembler.push(TextChunk(text="too late"))


def test_interrupted_message_keeps_text_but_discards_tool_calls() -> None:
    tool_call = ToolCall(id="call-1", name="write", arguments={"path": "notes.txt"})
    assembler = AssistantMessageAssembler()
    assembler.push(TextChunk(text="I will write the note. "))
    assembler.push(ToolCallChunk(tool_call=tool_call))
    assembler.push(TextChunk(text="The request was interrupted."))

    assert assembler.interrupted_message() == AssistantMessage(
        content=(
            TextContent(text="I will write the note. "),
            TextContent(text="The request was interrupted."),
        ),
        stop_reason="aborted",
        error_message="Cancelled",
    )


def test_interrupted_message_is_absent_when_only_a_tool_call_was_received() -> None:
    assembler = AssistantMessageAssembler()
    assembler.push(
        ToolCallChunk(
            tool_call=ToolCall(id="call-1", name="write", arguments={"path": "notes.txt"})
        )
    )

    assert assembler.interrupted_message() is None


def test_different_provider_translations_produce_the_same_message() -> None:
    tool_call = ToolCall(id="call-1", name="read", arguments={"path": "README.md"})
    provider_a_chunks = translate_provider_a(
        ProviderAResponse(
            text="I will read it.",
            tool_call=tool_call,
            response_id="a-1",
        )
    )
    provider_b_chunks = translate_provider_b(
        ProviderBResponse(
            content="I will read it.",
            action=tool_call,
            generation="b-9",
        )
    )

    message_a, replay_state_a = assemble_provider_chunks(provider_a_chunks)
    message_b, replay_state_b = assemble_provider_chunks(provider_b_chunks)

    assert message_a == message_b
    assert replay_state_a is not None
    assert replay_state_b is not None
    assert replay_state_a != replay_state_b
    assert replay_state_a.provider == "provider-a"
    assert replay_state_b.provider == "provider-b"


@dataclass(frozen=True, slots=True)
class ProviderAResponse:
    text: str
    tool_call: ToolCall
    response_id: str


@dataclass(frozen=True, slots=True)
class ProviderBResponse:
    content: str
    action: ToolCall
    generation: str


def translate_provider_a(
    response: ProviderAResponse,
) -> tuple[TextChunk | ToolCallChunk | FinishChunk, ...]:
    return (
        TextChunk(text=response.text),
        ToolCallChunk(tool_call=response.tool_call),
        FinishChunk(
            stop_reason="toolUse",
            replay_state=ProviderReplayState(
                provider="provider-a",
                schema_version=1,
                payload={"response_id": response.response_id},
            ),
        ),
    )


def translate_provider_b(
    response: ProviderBResponse,
) -> tuple[TextChunk | ToolCallChunk | FinishChunk, ...]:
    return (
        TextChunk(text=response.content),
        ToolCallChunk(tool_call=response.action),
        FinishChunk(
            stop_reason="toolUse",
            replay_state=ProviderReplayState(
                provider="provider-b",
                schema_version=7,
                payload={"generation": response.generation},
            ),
        ),
    )


def assemble_provider_chunks(
    chunks: tuple[TextChunk | ToolCallChunk | FinishChunk, ...],
) -> tuple[AssistantMessage, ProviderReplayState | None]:
    assembler = AssistantMessageAssembler()
    for chunk in chunks:
        assembler.push(chunk)
    return assembler.message(), assembler.replay_state
