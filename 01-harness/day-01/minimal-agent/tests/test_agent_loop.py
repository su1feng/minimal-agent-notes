import asyncio
from collections.abc import AsyncIterator, Sequence

import pytest

from minimal_harness.agent_loop import run_agent_loop
from minimal_harness.types import (
    AgentMessage,
    AssistantMessage,
    AssistantStreamEnd,
    AssistantStreamEvent,
    CancellationToken,
    ModelFormatError,
    TextContent,
    ToolCall,
    ToolExecutionResult,
    ToolResultMessage,
    UserMessage,
)
from tests.fakes import FakeCancellationToken, ScriptedModel, ScriptedToolExecutor


def answer(text: str) -> AssistantMessage:
    return AssistantMessage(content=(TextContent(text=text),), stop_reason="stop")


def tool_request(*calls: ToolCall, text: str = "") -> AssistantMessage:
    prefix = (TextContent(text=text),) if text else ()
    return AssistantMessage(content=(*prefix, *calls), stop_reason="toolUse")


@pytest.mark.asyncio
async def test_returns_a_final_answer_without_calling_a_tool() -> None:
    initial = (UserMessage(content="hello"),)
    final = answer("hi")
    model = ScriptedModel([final])
    tools = ScriptedToolExecutor([])

    result = await run_agent_loop(
        model=model,
        tool_executor=tools,
        initial_messages=initial,
    )

    assert result == (*initial, final)
    assert model.calls == [initial]
    assert tools.calls == []


@pytest.mark.asyncio
async def test_executes_a_tool_then_returns_the_models_final_answer() -> None:
    initial = (UserMessage(content="read README"),)
    call = ToolCall(id="call-1", name="read", arguments={"path": "README.md"})
    request = tool_request(call, text="I will read it")
    tool_result = ToolExecutionResult(
        content="file contents",
        details={"path": "README.md", "bytes": 13},
    )
    final = answer("The file contains documentation")
    model = ScriptedModel([request, final])
    tools = ScriptedToolExecutor([tool_result])

    result = await run_agent_loop(
        model=model,
        tool_executor=tools,
        initial_messages=initial,
    )

    expected_result_message = ToolResultMessage(
        tool_call_id="call-1",
        tool_name="read",
        content="file contents",
        details={"path": "README.md", "bytes": 13},
        is_error=False,
    )
    assert result == (*initial, request, expected_result_message, final)
    assert tools.calls == [call]
    assert model.calls[1] == (*initial, request, expected_result_message)


@pytest.mark.asyncio
async def test_preserves_an_error_result_and_gives_the_model_a_chance_to_recover() -> None:
    initial = (UserMessage(content="read missing file"),)
    call = ToolCall(id="call-1", name="read", arguments={"path": "missing.txt"})
    request = tool_request(call)
    failed = ToolExecutionResult(
        content="file not found",
        details={"path": "missing.txt"},
        is_error=True,
    )
    recovered = answer("The requested file does not exist")
    model = ScriptedModel([request, recovered])
    tools = ScriptedToolExecutor([failed])

    result = await run_agent_loop(
        model=model,
        tool_executor=tools,
        initial_messages=initial,
    )

    recorded = result[-2]
    assert isinstance(recorded, ToolResultMessage)
    assert recorded.is_error is True
    assert recorded.content == "file not found"
    assert result[-1] is recovered
    assert len(model.calls) == 2


@pytest.mark.asyncio
async def test_converts_a_tool_exception_into_an_error_result_and_continues() -> None:
    initial = (UserMessage(content="run tool"),)
    call = ToolCall(id="call-1", name="explode", arguments={})
    request = tool_request(call)
    recovered = answer("The tool failed")
    model = ScriptedModel([request, recovered])
    tools = ScriptedToolExecutor([RuntimeError("boom")])

    result = await run_agent_loop(
        model=model,
        tool_executor=tools,
        initial_messages=initial,
    )

    recorded = result[-2]
    assert isinstance(recorded, ToolResultMessage)
    assert recorded.is_error is True
    assert recorded.content == "boom"
    assert recorded.details == {"exception_type": "RuntimeError"}
    assert result[-1] is recovered


@pytest.mark.asyncio
async def test_executes_multiple_tool_calls_in_source_order() -> None:
    initial = (UserMessage(content="read two files"),)
    first_call = ToolCall(id="call-1", name="read", arguments={"path": "a.txt"})
    second_call = ToolCall(id="call-2", name="read", arguments={"path": "b.txt"})
    request = tool_request(first_call, second_call)
    final = answer("done")
    model = ScriptedModel([request, final])
    tools = ScriptedToolExecutor(
        [ToolExecutionResult(content="A"), ToolExecutionResult(content="B")]
    )

    result = await run_agent_loop(
        model=model,
        tool_executor=tools,
        initial_messages=initial,
    )

    assert tools.calls == [first_call, second_call]
    tool_messages = tuple(message for message in result if isinstance(message, ToolResultMessage))
    assert [message.tool_call_id for message in tool_messages] == ["call-1", "call-2"]
    assert [message.content for message in tool_messages] == ["A", "B"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_reason", ["error", "aborted"])
async def test_error_and_aborted_assistant_messages_are_hard_exits(stop_reason: str) -> None:
    initial = (UserMessage(content="run"),)
    call = ToolCall(id="call-1", name="dangerous", arguments={})
    terminal = AssistantMessage(
        content=(call,),
        stop_reason=stop_reason,  # type: ignore[arg-type]
        error_message=stop_reason,
    )
    model = ScriptedModel([terminal])
    tools = ScriptedToolExecutor([ToolExecutionResult(content="must not run")])

    result = await run_agent_loop(
        model=model,
        tool_executor=tools,
        initial_messages=initial,
    )

    assert result == (*initial, terminal)
    assert tools.calls == []
    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_rejects_tool_use_without_a_tool_call() -> None:
    model = ScriptedModel([AssistantMessage(content=(), stop_reason="toolUse")])
    tools = ScriptedToolExecutor([])

    with pytest.raises(ValueError, match="toolUse.*ToolCall"):
        await run_agent_loop(model=model, tool_executor=tools, initial_messages=())


@pytest.mark.asyncio
async def test_rejects_a_normal_stop_that_contains_a_tool_call() -> None:
    call = ToolCall(id="call-1", name="read", arguments={"path": "a.txt"})
    model = ScriptedModel([AssistantMessage(content=(call,), stop_reason="stop")])
    tools = ScriptedToolExecutor([])

    with pytest.raises(ValueError, match="stop.*ToolCall"):
        await run_agent_loop(model=model, tool_executor=tools, initial_messages=())


@pytest.mark.asyncio
async def test_does_not_mutate_the_callers_initial_message_container() -> None:
    initial: list[AgentMessage] = [UserMessage(content="hello")]
    original = tuple(initial)
    model = ScriptedModel([answer("hi")])
    tools = ScriptedToolExecutor([])

    result = await run_agent_loop(
        model=model,
        tool_executor=tools,
        initial_messages=initial,
    )

    assert tuple(initial) == original
    assert result == (*original, answer("hi"))


@pytest.mark.asyncio
async def test_forwards_the_same_cancellation_token_to_model_and_tool() -> None:
    token = FakeCancellationToken()
    call = ToolCall(id="call-1", name="read", arguments={"path": "a.txt"})
    model = ScriptedModel([tool_request(call), answer("done")])
    tools = ScriptedToolExecutor([ToolExecutionResult(content="A")])

    await run_agent_loop(
        model=model,
        tool_executor=tools,
        initial_messages=(),
        signal=token,
    )

    assert model.signals == [token, token]
    assert tools.signals == [token]


@pytest.mark.asyncio
async def test_rejects_a_non_positive_step_limit_before_calling_the_model() -> None:
    model = ScriptedModel([answer("unused")])
    tools = ScriptedToolExecutor([])

    with pytest.raises(ValueError, match="max_steps must be positive"):
        await run_agent_loop(
            model=model,
            tool_executor=tools,
            initial_messages=(),
            max_steps=0,
        )

    assert model.calls == []


@pytest.mark.asyncio
async def test_stops_before_starting_a_model_call_beyond_the_step_limit() -> None:
    call = ToolCall(id="call-1", name="work", arguments={})
    model = ScriptedModel([tool_request(call), answer("must not be requested")])
    tools = ScriptedToolExecutor([ToolExecutionResult(content="done")])

    with pytest.raises(RuntimeError, match="step limit exceeded"):
        await run_agent_loop(
            model=model,
            tool_executor=tools,
            initial_messages=(),
            max_steps=1,
        )

    assert len(model.calls) == 1
    assert tools.calls == [call]


@pytest.mark.asyncio
async def test_pre_cancelled_run_does_not_call_model_or_tool() -> None:
    token = FakeCancellationToken(cancelled=True)
    model = ScriptedModel([answer("must not run")])
    tools = ScriptedToolExecutor([])

    with pytest.raises(asyncio.CancelledError):
        await run_agent_loop(
            model=model,
            tool_executor=tools,
            initial_messages=(),
            signal=token,
        )

    assert model.calls == []
    assert tools.calls == []


@pytest.mark.asyncio
async def test_cancellation_observed_after_model_return_prevents_tool_start() -> None:
    token = FakeCancellationToken()
    call = ToolCall(id="call-1", name="dangerous", arguments={})

    class CancellingModel:
        async def stream(
            self,
            messages: Sequence[AgentMessage],
            signal: CancellationToken | None = None,
        ) -> AsyncIterator[AssistantStreamEvent]:
            del messages, signal
            token.cancel()
            yield AssistantStreamEnd(message=tool_request(call))

    tools = ScriptedToolExecutor([ToolExecutionResult(content="must not run")])

    with pytest.raises(asyncio.CancelledError):
        await run_agent_loop(
            model=CancellingModel(),
            tool_executor=tools,
            initial_messages=(),
            signal=token,
        )

    assert tools.calls == []


@pytest.mark.asyncio
async def test_tool_task_cancellation_is_not_converted_to_an_error_result() -> None:
    call = ToolCall(id="call-1", name="work", arguments={})
    model = ScriptedModel([tool_request(call)])

    class CancellingTool:
        async def execute(
            self,
            tool_call: ToolCall,
            signal: CancellationToken | None = None,
        ) -> ToolExecutionResult:
            del tool_call, signal
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await run_agent_loop(
            model=model,
            tool_executor=CancellingTool(),
            initial_messages=(),
        )


@pytest.mark.asyncio
async def test_format_error_feedback_is_added_before_retrying_the_model() -> None:
    feedback = UserMessage(content="Return a valid tool call")
    final = answer("recovered")
    model = ScriptedModel([ModelFormatError(feedback), final])
    tools = ScriptedToolExecutor([])

    result = await run_agent_loop(
        model=model,
        tool_executor=tools,
        initial_messages=(UserMessage(content="start"),),
    )

    assert result == (UserMessage(content="start"), feedback, final)
    assert model.calls == [
        (UserMessage(content="start"),),
        (UserMessage(content="start"), feedback),
    ]


@pytest.mark.asyncio
async def test_consecutive_format_errors_end_cleanly_at_the_configured_threshold() -> None:
    first = UserMessage(content="First format correction")
    second = UserMessage(content="Second format correction")
    model = ScriptedModel([ModelFormatError(first), ModelFormatError(second), answer("unused")])
    tools = ScriptedToolExecutor([])

    result = await run_agent_loop(
        model=model,
        tool_executor=tools,
        initial_messages=(),
        max_consecutive_format_errors=2,
    )

    terminal = result[-1]
    assert isinstance(terminal, AssistantMessage)
    assert terminal.stop_reason == "error"
    assert terminal.error_message == "RepeatedFormatError"
    assert result == (first, second, terminal)
    assert len(model.calls) == 2
    assert tools.calls == []


@pytest.mark.asyncio
async def test_successful_model_turn_resets_the_consecutive_format_error_counter() -> None:
    first_feedback = UserMessage(content="First correction")
    second_feedback = UserMessage(content="Second correction")
    call = ToolCall(id="call-1", name="read", arguments={"path": "a.txt"})
    request = tool_request(call)
    final = answer("done")
    model = ScriptedModel(
        [
            ModelFormatError(first_feedback),
            request,
            ModelFormatError(second_feedback),
            final,
        ]
    )
    tools = ScriptedToolExecutor([ToolExecutionResult(content="A")])

    result = await run_agent_loop(
        model=model,
        tool_executor=tools,
        initial_messages=(),
        max_steps=4,
        max_consecutive_format_errors=2,
    )

    assert result[-1] is final
    assert second_feedback in result
    assert not any(
        isinstance(message, AssistantMessage) and message.error_message == "RepeatedFormatError"
        for message in result
    )
    assert len(model.calls) == 4


@pytest.mark.asyncio
async def test_format_errors_consume_model_steps() -> None:
    model = ScriptedModel([ModelFormatError(UserMessage(content="correction")), answer("unused")])
    tools = ScriptedToolExecutor([])

    with pytest.raises(RuntimeError, match="step limit exceeded"):
        await run_agent_loop(
            model=model,
            tool_executor=tools,
            initial_messages=(),
            max_steps=1,
            max_consecutive_format_errors=2,
        )

    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_rejects_a_negative_format_error_limit_before_calling_model() -> None:
    model = ScriptedModel([answer("unused")])
    tools = ScriptedToolExecutor([])

    with pytest.raises(ValueError, match="max_consecutive_format_errors must be non-negative"):
        await run_agent_loop(
            model=model,
            tool_executor=tools,
            initial_messages=(),
            max_consecutive_format_errors=-1,
        )

    assert model.calls == []


@pytest.mark.asyncio
async def test_zero_disables_the_consecutive_format_error_limit() -> None:
    feedbacks = tuple(UserMessage(content=f"correction {index}") for index in range(3))
    model = ScriptedModel([*(ModelFormatError(feedback) for feedback in feedbacks), answer("done")])
    tools = ScriptedToolExecutor([])

    result = await run_agent_loop(
        model=model,
        tool_executor=tools,
        initial_messages=(),
        max_steps=4,
        max_consecutive_format_errors=0,
    )

    assert result == (*feedbacks, answer("done"))
