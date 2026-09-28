import math
from collections.abc import Mapping
from typing import cast

import pytest

from minimal_harness.types import deserialize_json, freeze_json, serialize_json


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_freeze_json_rejects_non_finite_floats(value: float) -> None:
    with pytest.raises(TypeError, match="finite"):
        freeze_json(value)


def test_freeze_json_rejects_a_self_referential_list() -> None:
    source: list[object] = []
    source.append(source)

    with pytest.raises(TypeError, match="Circular"):
        freeze_json(source)


def test_freeze_json_rejects_an_indirect_mapping_cycle() -> None:
    first: dict[str, object] = {}
    second = {"first": first}
    first["second"] = second

    with pytest.raises(TypeError, match="Circular"):
        freeze_json(first)


def test_frozen_json_serializes_and_reads_back_without_mutable_aliases() -> None:
    source = {
        "tool": {"name": "read", "arguments": {"lines": [1, 2]}},
        "enabled": True,
        "nothing": None,
    }

    frozen = freeze_json(source)
    encoded = serialize_json(frozen)
    decoded = deserialize_json(encoded)

    tool_source = cast(dict[str, object], source["tool"])
    arguments_source = cast(dict[str, list[int]], tool_source["arguments"])
    arguments_source["lines"].append(3)

    assert decoded == frozen
    assert isinstance(decoded, Mapping)
    tool = decoded["tool"]
    assert isinstance(tool, Mapping)
    arguments = tool["arguments"]
    assert isinstance(arguments, Mapping)
    assert arguments["lines"] == (1, 2)


@pytest.mark.parametrize(
    "encoded",
    ["NaN", "Infinity", "-Infinity", '{"value": NaN}'],
)
def test_deserialize_json_rejects_non_standard_non_finite_literals(encoded: str) -> None:
    with pytest.raises(ValueError, match="non-finite"):
        deserialize_json(encoded)
