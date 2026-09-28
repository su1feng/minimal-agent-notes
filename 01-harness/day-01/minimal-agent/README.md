# Day 01–03：最小 Agent Loop 与模型流

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

## Day 02 扩展

- `events.py` 定义与消息历史分离的生命周期事件，以及可等待的事件 sink。
- `ModelAdapter.stream()` 只有一条异步流路径；一次性 FakeModel 也通过包含 `FinishChunk` 的短流表达。
- 流式草稿只出现在 `MessageUpdateEvent`，正式历史只提交最终消息。
- 流式取消只在已有安全文本时提交一条 `stop_reason="aborted"` 消息，然后继续传播 `CancelledError`。
- 工具取消不伪造执行结果，并以 `AgentEndEvent` 闭合已经开始的生命周期。

## Day 03 扩展

- Provider Adapter 输出 text、tool call、usage、finish 四种 `ModelStreamChunk`；`AssistantMessageAssembler` 统一构造正式消息，Provider 私有 replay state 保持不透明。
- `AssistantAttempt`／`AttemptResult` 在内存中区分完成、取消、失败。模型接口报错不会形成正式 assistant 消息；已经完成的工具调用及其结果仍保留，工具执行失败仍以错误工具结果回填给模型。
- 严格 JSON 边界拒绝循环引用及非有限数字，并支持冻结值的序列化往返。
- `AttemptResult` 的持久化、恢复和分支投影留给后续 EventStore／ContextBuilder；本阶段不把 UI draft/update 当作恢复事实。

## 范围限制

- 不接真实模型、HTTP或shell。
- 不实现CLI、TUI、持久化、并行工具、steering或follow-up。
- 不使用 `Any`。
- Event 与 Message 保持分离；Event 不作为可恢复历史持久化。

## 最终验收

- FakeModel请求一次工具，得到结果后返回最终答案。
- 工具抛出异常时生成 `isError: true` 的工具结果消息。
- 工具失败不会被当成Agent正常完成。
- 取消在设定超时内退出，且取消后不再追加工具结果或消息事件。
- 流式 partial 不进入正式历史；完成提交一条 final 消息，取消仅在有安全文本时提交一条 aborted 消息，模型接口报错不提交正式消息。
- `uv run mypy src tests`与`uv run pytest`通过。
