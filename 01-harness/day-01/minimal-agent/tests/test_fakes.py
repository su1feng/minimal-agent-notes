import pytest

from minimal_harness.types import (
    AgentMessage,
    AssistantMessage,
    AssistantStreamEnd,
    ModelAdapter,
    TextContent,
    ToolCall,
    ToolExecutionResult,
    ToolExecutor,
    UserMessage,
)
from tests.fakes import FakeCancellationToken, ScriptedModel, ScriptedToolExecutor


def final_answer(text: str) -> AssistantMessage:
    return AssistantMessage(content=(TextContent(text=text),), stop_reason="stop")


@pytest.mark.asyncio
async def test_scripted_model_returns_outcomes_in_order_and_records_snapshots() -> None:
    first = final_answer("first")
    second = final_answer("second")
    model = ScriptedModel([first, second])
    history: list[AgentMessage] = [UserMessage(content="hello")]

    assert [event async for event in model.stream(history)] == [AssistantStreamEnd(message=first)]
    history.append(first)
    assert [event async for event in model.stream(history)] == [AssistantStreamEnd(message=second)]

    assert model.calls == [
        (UserMessage(content="hello"),),
        (UserMessage(content="hello"), first),
    ]


@pytest.mark.asyncio
async def test_scripted_model_raises_scripted_exception() -> None:
    failure = RuntimeError("provider failed")
    model = ScriptedModel([failure])

    with pytest.raises(RuntimeError, match="provider failed") as captured:
        _ = [event async for event in model.stream([])]

    assert captured.value is failure


@pytest.mark.asyncio
async def test_scripted_model_fails_loudly_when_script_is_exhausted() -> None:
    model = ScriptedModel([])

    with pytest.raises(AssertionError, match="no response left"):
        _ = [event async for event in model.stream([])]


@pytest.mark.asyncio
async def test_scripted_model_records_the_same_cancellation_token() -> None:
    token = FakeCancellationToken()
    model = ScriptedModel([final_answer("done")])

    _ = [event async for event in model.stream([], token)]

    assert model.signals == [token]


@pytest.mark.asyncio
async def test_scripted_tool_returns_outcomes_in_order_and_records_calls() -> None:
    first = ToolExecutionResult(content="a")
    second = ToolExecutionResult(content="b")
    executor = ScriptedToolExecutor([first, second])
    call_a = ToolCall(id="call-1", name="read", arguments={"path": "a.txt"})
    call_b = ToolCall(id="call-2", name="read", arguments={"path": "b.txt"})

    assert await executor.execute(call_a) is first
    assert await executor.execute(call_b) is second
    assert executor.calls == [call_a, call_b]


@pytest.mark.asyncio
async def test_scripted_tool_raises_scripted_exception() -> None:
    failure = OSError("disk failed")
    executor = ScriptedToolExecutor([failure])
    call = ToolCall(id="call-1", name="read", arguments={"path": "a.txt"})

    with pytest.raises(OSError, match="disk failed") as captured:
        await executor.execute(call)

    assert captured.value is failure


@pytest.mark.asyncio
async def test_scripted_tool_fails_loudly_when_script_is_exhausted() -> None:
    executor = ScriptedToolExecutor([])
    call = ToolCall(id="call-1", name="read", arguments={"path": "a.txt"})

    with pytest.raises(AssertionError, match="no result left"):
        await executor.execute(call)


@pytest.mark.asyncio
async def test_scripted_tool_records_the_same_cancellation_token() -> None:
    token = FakeCancellationToken()
    executor = ScriptedToolExecutor([ToolExecutionResult(content="ok")])
    call = ToolCall(id="call-1", name="read", arguments={"path": "a.txt"})

    await executor.execute(call, token)

    assert executor.signals == [token]


def test_fakes_structurally_satisfy_runtime_protocols() -> None:
    model: ModelAdapter = ScriptedModel([final_answer("done")])
    executor: ToolExecutor = ScriptedToolExecutor([ToolExecutionResult(content="ok")])

    assert isinstance(model, ScriptedModel)
    assert isinstance(executor, ScriptedToolExecutor)


def test_cancellation_token_can_be_changed_by_the_test() -> None:
    token = FakeCancellationToken()

    assert token.is_cancelled() is False
    token.cancel()
    assert token.is_cancelled() is True
