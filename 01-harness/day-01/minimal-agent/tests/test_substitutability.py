import pytest

from minimal_harness.agent_loop import run_agent_loop
from minimal_harness.types import (
    AssistantMessage,
    ModelAdapter,
    TextContent,
    ToolCall,
    ToolExecutor,
    ToolResultMessage,
    UserMessage,
)
from tests.alternatives import EchoToolExecutor, RuleBasedEchoModel
from tests.fakes import FakeCancellationToken


@pytest.mark.asyncio
async def test_rule_based_model_and_echo_tool_run_through_the_same_loop() -> None:
    model = RuleBasedEchoModel()
    executor = EchoToolExecutor()
    token = FakeCancellationToken()

    model_adapter: ModelAdapter = model
    tool_executor: ToolExecutor = executor
    result = await run_agent_loop(
        model=model_adapter,
        tool_executor=tool_executor,
        initial_messages=(UserMessage(content="hello"),),
        signal=token,
    )

    assert [message.role for message in result] == [
        "user",
        "assistant",
        "toolResult",
        "assistant",
    ]
    tool_result = result[2]
    assert isinstance(tool_result, ToolResultMessage)
    assert tool_result.content == "hello"
    assert tool_result.details == {"length": 5}
    final = result[-1]
    assert isinstance(final, AssistantMessage)
    assert final.content == (TextContent(text="echo: hello"),)
    assert len(model.calls) == 2
    assert len(executor.calls) == 1
    assert model.signals == [token, token]
    assert executor.signals == [token]


@pytest.mark.asyncio
async def test_echo_tool_reports_an_unknown_tool_as_a_normal_error_result() -> None:
    executor = EchoToolExecutor()
    result = await executor.execute(ToolCall(id="call-1", name="read", arguments={}))

    assert result.is_error is True
    assert result.content == "unsupported tool: read"


@pytest.mark.asyncio
async def test_echo_tool_reports_invalid_arguments_without_raising() -> None:
    executor = EchoToolExecutor()
    result = await executor.execute(ToolCall(id="call-1", name="echo", arguments={"text": 123}))

    assert result.is_error is True
    assert result.content == "echo.text must be a string"
