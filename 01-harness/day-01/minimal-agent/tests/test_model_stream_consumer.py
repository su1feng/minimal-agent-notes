from collections.abc import AsyncIterator

import pytest

from minimal_harness.model_stream import FinishChunk, ModelStreamChunk, TextChunk
from minimal_harness.model_stream_consumer import assemble_model_stream
from minimal_harness.types import AssistantMessage, TextContent


async def chunks() -> AsyncIterator[ModelStreamChunk]:
    yield TextChunk(text="Hello, ")
    yield TextChunk(text="world!")
    yield FinishChunk(stop_reason="stop")


@pytest.mark.asyncio
async def test_assembles_an_async_model_stream_into_a_final_message() -> None:
    assert await assemble_model_stream(chunks()) == AssistantMessage(
        content=(TextContent(text="Hello, world!"),),
        stop_reason="stop",
    )
