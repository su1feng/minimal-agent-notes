"""Consume a provider-neutral model stream into one assistant message."""

from collections.abc import AsyncIterator

from .assistant_message_assembler import AssistantMessageAssembler
from .model_stream import ModelStreamChunk
from .types import AssistantMessage


async def assemble_model_stream(
    stream: AsyncIterator[ModelStreamChunk],
) -> AssistantMessage:
    assembler = AssistantMessageAssembler()

    async for chunk in stream:
        assembler.push(chunk)

    return assembler.message()
