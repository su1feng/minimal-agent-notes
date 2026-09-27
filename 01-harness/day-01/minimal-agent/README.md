# Day 01：最小 Agent Loop 手搓

目标：不用真实模型和真实工具，实现并测试下面的最小闭环。

```text
UserMessage
→ FakeModel 请求工具
→ FakeToolExecutor 执行
→ ToolResultMessage 写入历史
→ FakeModel 读取结果
→ AssistantMessage 最终回答
```

## 实现顺序

1. `src/minimal_harness/types.py`：消息、工具调用／结果、ModelAdapter、ToolExecutor。
2. `tests/fakes.py`：可编排的 FakeModel 与 FakeToolExecutor。
3. `src/minimal_harness/agent_loop.py`：实现 `run_agent_loop()`，使助教提供的测试通过；核心逻辑不超过约 100 行。
4. `tests/test_agent_loop.py`：由助教维护，覆盖正常完成、工具失败、异常隔离、消息顺序、硬退出、输入隔离、取消传播和步数上限。

## 范围限制

- 不接真实模型、HTTP或shell。
- 不实现CLI、TUI、持久化、并行工具、steering或follow-up。
- 不使用 `Any`。
- Event与Message保持分离；本练习暂不实现Event。

## 最终验收

- FakeModel请求一次工具，得到结果后返回最终答案。
- 工具抛出异常时生成 `isError: true` 的工具结果消息。
- 工具失败不会被当成Agent正常完成。
- `uv run mypy src tests`与`uv run pytest`通过。
