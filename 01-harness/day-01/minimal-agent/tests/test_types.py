from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from minimal_harness.types import (
    AssistantMessage,
    JSONValue,
    TextContent,
    ToolCall,
    ToolExecutionResult,
    ToolResultMessage,
    UserMessage,
    freeze_json,
)


@pytest.mark.parametrize("value", [None, True, False, 0, 1, -1, 1.5, "", "text"])
def test_freeze_json_preserves_primitive_values(value: JSONValue) -> None:
    assert freeze_json(value) == value


def test_freeze_json_detaches_and_recursively_freezes_nested_values() -> None:
    source = {
        "path": "README.md",
        "options": {
            "lines": [1, 2],
            "metadata": {"enabled": True},
        },
    }

    frozen = freeze_json(source)

    source["path"] = "changed.txt"
    cast(dict[str, object], source["options"])["lines"] = [99]

    assert isinstance(frozen, Mapping)
    assert frozen["path"] == "README.md"
    options = frozen["options"]
    assert isinstance(options, Mapping)
    assert options["lines"] == (1, 2)
    metadata = options["metadata"]
    assert isinstance(metadata, Mapping)
    assert metadata["enabled"] is True


def test_freeze_json_rejects_non_string_mapping_keys() -> None:
    with pytest.raises(TypeError, match="keys must be strings"):
        freeze_json({1: "invalid"})


@pytest.mark.parametrize("value", [object(), {1, 2}, b"bytes"])
def test_freeze_json_rejects_non_json_values(value: object) -> None:
    with pytest.raises(TypeError, match="Unsupported JSON value"):
        freeze_json(value)


def test_tool_call_detaches_arguments_from_the_caller() -> None:
    source = {"path": "README.md", "lines": [1, 2]}

    call = ToolCall(
        id="call-1",
        name="read",
        arguments=cast(Mapping[str, JSONValue], source),
    )
    source["path"] = "changed.txt"
    cast(list[int], source["lines"]).append(3)

    assert call.type == "toolCall"
    assert call.arguments["path"] == "README.md"
    assert call.arguments["lines"] == (1, 2)


def test_tool_call_arguments_cannot_be_mutated() -> None:
    call = ToolCall(id="call-1", name="read", arguments={"path": "README.md"})

    with pytest.raises(TypeError):
        call.arguments["path"] = "changed.txt"  # type: ignore[index]


def test_tool_call_requires_a_json_object_at_the_top_level() -> None:
    with pytest.raises(TypeError, match="must be a JSON object"):
        ToolCall(id="call-1", name="read", arguments=cast(object, ["README.md"]))  # type: ignore[arg-type]


def test_assistant_message_preserves_mixed_content_order() -> None:
    first = ToolCall(id="call-1", name="read", arguments={"path": "a.txt"})
    second = ToolCall(id="call-2", name="read", arguments={"path": "b.txt"})

    message = AssistantMessage(
        content=(TextContent(text="Reading files"), first, second),
        stop_reason="toolUse",
    )

    assert message.role == "assistant"
    assert message.content == (TextContent(text="Reading files"), first, second)


def test_assistant_message_detaches_an_untyped_list_input() -> None:
    source = [TextContent(text="hello")]

    message = AssistantMessage(content=source, stop_reason="stop")  # type: ignore[arg-type]
    source.append(TextContent(text="changed"))

    assert isinstance(message.content, tuple)
    assert message.content == (TextContent(text="hello"),)


def test_message_dataclasses_are_frozen_and_slotted() -> None:
    message = UserMessage(content="hello")

    with pytest.raises(FrozenInstanceError):
        message.content = "changed"  # type: ignore[misc]

    assert not hasattr(message, "__dict__")


def assert_details_are_detached_and_frozen(
    details: JSONValue,
    source: dict[str, object],
) -> None:
    source["items"] = ["changed"]

    assert isinstance(details, Mapping)
    assert details["items"] == ("a",)
    with pytest.raises(TypeError):
        cast(dict[str, JSONValue], details)["items"] = ("changed",)


def test_tool_execution_result_details_are_detached_and_frozen() -> None:
    source: dict[str, object] = {"stats": {"count": 1}, "items": ["a"]}
    result = ToolExecutionResult(content="ok", details=cast(JSONValue, source))

    assert_details_are_detached_and_frozen(result.details, source)


def test_tool_result_message_details_are_detached_and_frozen() -> None:
    source: dict[str, object] = {"stats": {"count": 1}, "items": ["a"]}
    result = ToolResultMessage(
        tool_call_id="call-1",
        tool_name="read",
        content="ok",
        details=cast(JSONValue, source),
    )

    assert_details_are_detached_and_frozen(result.details, source)


def test_message_discriminators_are_fixed() -> None:
    assert TextContent(text="hello").type == "text"
    assert UserMessage(content="hello").role == "user"
    assert (
        ToolResultMessage(
            tool_call_id="call-1",
            tool_name="read",
            content="ok",
        ).role
        == "toolResult"
    )
