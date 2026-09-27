# Day 01 关键设计决定（阶段 1：最小循环）

范围：本文件记录 Day-01 微型实现（`src/minimal_harness/`）已经生效的设计决定，每条都给出代码位置与测试证据。
阶段 1 尚未定型的两项——生命周期事件层（D1-01）与流式提交边界（D1-02）——不在本文件内，待 Day 02 定型后追加。

代码基线：本文档与工作区 58 项测试、Ruff、mypy strict 同时通过的状态对应（`progress.md` 阶段记录中的 commit 锚点）。

---

## D-01 消息与运行事件分离，阶段 1 只实现消息

- **决定**：本阶段只维护 `AgentMessage` 历史（`UserMessage` / `AssistantMessage` / `ToolResultMessage`），不实现生命周期事件类型。
- **理由**：消息是可持久化的事实，事件是给调用方的运行信号。阅读 Tau／pi 的结论是二者边界不同，且**完成顺序可以不同于持久化顺序**。
- **证据**：`src/minimal_harness/types.py` 只有消息类型，无任何 Event 类型；`README.md` 范围限制明确"Event 与 Message 保持分离；本练习暂不实现 Event"。
- **影响**：验收项"取消后不再追加执行事件"必须等事件层（延期项 D1-01）才可断言，因此当前无法勾选。

## D-02 全部消息不可变

- **决定**：消息与工具结果统一 `@dataclass(frozen=True, slots=True)`；`AssistantMessage.content` 在 `__post_init__` 中归一为 `tuple`；`ToolCall.arguments`、`ToolExecutionResult.details`、`ToolResultMessage.details` 统一经 `freeze_json` 冻结。
- **理由**：历史一旦写入就不应被后续代码改写；共享可变别名会破坏"完整历史"语义，也让事件顺序断言不可靠。
- **证据**：`tests/test_types.py`（13 项，含不可变性与归一化）；`test_does_not_mutate_the_callers_initial_message_container` 证明调用方传入的容器不被改动。

## D-03 用递归联合类型表达 JSON，不使用 `Any`

- **决定**：`JSONValue = JSONPrimitive | tuple[JSONValue, ...] | Mapping[str, JSONValue]`；`freeze_json` 把 `list`/`tuple` 转 `tuple`、`Mapping` 转 `MappingProxyType`，遇到非字符串键或不支持的类型抛 `TypeError`。
- **理由**：使用 `Any` 会绕过 mypy strict，工具详情（details）会变成不可预期的任意结构。
- **证据**：`tests/test_types.py`；`mypy src tests` strict 通过；`pyproject.toml` 的 ruff 规则集含 `B`、`SIM`。
- **遗留**：循环引用、`NaN`/`Infinity`、以及 `freeze → 序列化 → 读取`往返一致性属于持久化边界，延期项 D1-03（Day 03）。

## D-04 模型与工具只用 Protocol 约束，不要求继承

- **决定**：`ModelAdapter`、`ToolExecutor`、`CancellationToken` 都是 `Protocol`；替换实现不需要继承这些类型。
- **理由**：内核不应要求调用方继承自己的基类；替换成本必须低，否则"可替换"只是声明。
- **证据**：`tests/alternatives.py` 的 `RuleBasedEchoModel` / `EchoToolExecutor` **不继承** Protocol，`tests/test_substitutability.py` 3 项通过，mypy 用结构化类型确认兼容。

## D-05 工具异常是数据，循环契约破坏是异常

- **决定**：`ToolExecutor.execute` 抛出的 `Exception` 由 `_execute_tool` 转成 `ToolExecutionResult(is_error=True)`，追加为 `ToolResultMessage` 后继续循环；模型返回违反契约时（`stop` 却带 `ToolCall`、`toolUse` 却无 `ToolCall`）抛 `ValueError`；步数耗尽抛 `RuntimeError("step limit exceeded")`。
- **理由**：工具失败是运行中的预期事件，应回填给模型自行恢复；契约破坏属于程序错误，必须显式失败而不是伪装成正常完成。
- **证据**：`test_converts_a_tool_exception_into_an_error_result_and_continues`、`test_preserves_an_error_result_and_gives_the_model_a_chance_to_recover`、`test_rejects_tool_use_without_a_tool_call`、`test_rejects_a_normal_stop_that_contains_a_tool_call`、`test_stops_before_starting_a_model_call_beyond_the_step_limit`。

## D-06 取消不是错误结果

- **决定**：取消以 `asyncio.CancelledError` 传播；`_execute_tool` 只捕获 `Exception`，因此 `CancelledError`（Python 3.8+ 起继承 `BaseException`）**不会**被转成错误结果；模型调用前、模型返回后、每个工具执行前各检查一次 `signal.is_cancelled()`。
- **理由**：取消必须能穿透到底层；把取消吞成 `is_error=True` 会让上层误判为可恢复失败。
- **证据**：`test_pre_cancelled_run_does_not_call_model_or_tool`、`test_cancellation_observed_after_model_return_prevents_tool_start`、`test_tool_task_cancellation_is_not_converted_to_an_error_result`。
- **遗留**：事件顺序与"在设定超时内退出"的量化断言属于 D1-01。

## D-07 格式错误通过反馈重试，并计入步数

- **决定**：模型用 `ModelFormatError(feedback: UserMessage)` 表示"输出无法转成合法 assistant 消息"；循环追加该 feedback 后重试，连续计数，成功一轮即清零；`max_consecutive_format_errors` 达到阈值时追加一条 `stop_reason="error"`、`error_message="RepeatedFormatError"` 的 `AssistantMessage` 并正常返回；阈值 `0` 表示不限制；负值在调用模型前抛 `ValueError`。
- **理由**：格式错误应当可恢复，但必须有上限以免空转烧预算；耗尽时也要留下可解释的终止消息，而不是抛未分类异常。
- **证据**：`test_format_error_feedback_is_added_before_retrying_the_model`、`test_consecutive_format_errors_end_cleanly_at_the_configured_threshold`、`test_successful_model_turn_resets_the_consecutive_format_error_counter`、`test_format_errors_consume_model_steps`、`test_zero_disables_the_consecutive_format_error_limit`、`test_rejects_a_negative_format_error_limit_before_calling_model`。

## D-08 同一 assistant 消息内的工具按来源顺序串行执行

- **决定**：对 `AssistantMessage.content` 中出现的 `ToolCall` 逐个 `await`，保持来源顺序，本阶段不做并行。
- **理由**：阶段 1 范围明确排除并行工具；顺序执行让结果顺序与 `tool_call_id` 一一对应，最容易验证。
- **证据**：`test_executes_multiple_tool_calls_in_source_order`。
- **遗留**：并行工具及其事件顺序在后续阶段按需引入（pi 的并行语义作为参考，不在本阶段）。

## D-09 历史以全量快照传入模型，本阶段不做投影

- **决定**：每次模型调用传入 `tuple(messages)` 的完整历史快照；不区分"完整历史"与"当前模型输入"。
- **理由**：投影（截断、系统提示、上下文构建）属于阶段 2 的 ContextBuilder，提前做会把持久化语义混进最小循环。
- **证据**：`ModelAdapter.query(messages, signal)` 签名；`tests/fakes.py` 与 `tests/alternatives.py` 都记录每次收到的快照，可用于断言输入隔离。
- **遗留**：D1-04（编辑旧消息的 `parent_id` 分支与上下文投影，阶段 2）。

---

## 阶段 1 四条验收路径 → 测试对应

| 验收路径 | 代表测试 |
|---|---|
| 正常完成 | `test_executes_a_tool_then_returns_the_models_final_answer`、`test_returns_a_final_answer_without_calling_a_tool` |
| 工具失败 | `test_converts_a_tool_exception_into_an_error_result_and_continues`、`test_preserves_an_error_result_and_gives_the_model_a_chance_to_recover` |
| 连续格式错误达阈值 | `test_consecutive_format_errors_end_cleanly_at_the_configured_threshold` |
| 预算耗尽 | `test_stops_before_starting_a_model_call_beyond_the_step_limit` |
| 替换第二套 ModelAdapter | `test_substitutability.py::test_rule_based_model_and_echo_tool_run_through_the_same_loop` |
| 替换第二套 ToolExecutor | 同上 + `test_echo_tool_reports_an_unknown_tool_as_a_normal_error_result`、`test_echo_tool_reports_invalid_arguments_without_raising` |
| 取消后限时退出且不再追加执行事件 | **未完成**：现有 3 项取消测试只证明不调用模型／工具，事件断言依赖 D1-01 |
