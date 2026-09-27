# Day 01–02 关键设计决定（阶段 1：最小循环）

范围：本文件记录阶段 1 微型实现（`src/minimal_harness/`）已经生效的设计决定，每条都给出代码位置与测试证据。
Day 02 已完成生命周期事件层（D1-01）与流式提交边界（D1-02），对应决定见 D-10 与 D-11。

代码基线：本文档与工作区 67 项测试、Ruff、mypy strict 同时通过的状态对应。

---

## D-01 消息与运行事件分离

- **决定**：Day 01 只维护 `AgentMessage` 历史；Day 02 新增的生命周期事件仍是独立运行信号，不进入消息历史。
- **理由**：消息是可持久化的事实，事件是给调用方的运行信号。阅读 Tau／pi 的结论是二者边界不同，且**完成顺序可以不同于持久化顺序**。
- **证据**：消息定义在 `types.py`，生命周期事件定义在 `events.py`；流式测试证明 `AssistantDraft` 只出现在事件中。
- **影响**：后续 EventStore 只持久化消息与恢复事实，不直接把 UI 更新事件当作恢复日志。

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

- **决定**：取消以 `asyncio.CancelledError` 传播；`_execute_tool` 只捕获 `Exception`，因此 `CancelledError`（Python 3.8+ 起继承 `BaseException`）**不会**被转成错误结果；模型流启动前、每个 stream event 到达后、每个工具执行前各检查一次 `signal.is_cancelled()`。
- **理由**：取消必须能穿透到底层；把取消吞成 `is_error=True` 会让上层误判为可恢复失败。
- **证据**：`test_pre_cancelled_run_does_not_call_model_or_tool`、`test_cancellation_observed_after_model_return_prevents_tool_start`、`test_tool_task_cancellation_is_not_converted_to_an_error_result`。
- **证据补充**：`test_cancellation_during_a_tool_closes_promptly_without_result_events` 量化验证 0.1 秒内退出；`test_pre_cancelled_run_only_emits_the_lifecycle_boundary` 验证取消后没有模型／工具执行事件。

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
- **证据**：`ModelAdapter.stream(messages, signal)` 签名；`tests/fakes.py` 与 `tests/alternatives.py` 都记录每次收到的快照，可用于断言输入隔离。
- **遗留**：D1-04（编辑旧消息的 `parent_id` 分支与上下文投影，阶段 2）。

## D-10 可等待事件 sink 固定生命周期顺序

- **决定**：`AgentEventSink.emit()` 为异步接口，循环逐个等待事件；参数校验通过后发出 `agent_start`，所有已开始运行都在 `finally` 中以唯一的 `agent_end` 收尾。
- **理由**：等待 sink 可以提供明确的事件先后关系；`finally` 保证正常返回、步数耗尽、契约异常和取消共享同一个生命周期闭合规则。
- **顺序**：工具路径固定为 assistant 消息结束 → `tool_execution_start` → `tool_execution_end` → tool result 消息开始／结束；工具取消只保留 start，不伪造 end 或结果消息。
- **证据**：`tests/test_events.py` 覆盖直接回答、工具调用、工具异常、预取消、工具中取消及步数耗尽，共 6 项。

## D-11 流式草稿只存在于事件，正式历史只提交终态

- **决定**：`ModelAdapter.stream()` 只返回 `AsyncIterator[AssistantStreamEvent]`；一次性响应也表示为只含一个 `AssistantStreamEnd` 的短流。文本 delta 累积为不可变 `AssistantDraft` 并通过 `message_update` 发出，不加入 `AgentMessage` 历史。
- **完成边界**：收到 `AssistantStreamEnd` 时只提交其 final message；流式过程中取消时只提交一条包含现有文本的 `stop_reason="aborted"` 消息，然后继续传播 `CancelledError`。
- **理由**：partial 是随时会变化的运行视图，不能污染可恢复历史；final／aborted 才是稳定事实。
- **证据**：`tests/test_streaming.py` 覆盖两段 delta 合并、final 单次提交、取消后 aborted 单次提交，以及缺少终止事件的契约错误。

## D-12 ModelAdapter 统一为 stream-only，与 pi／DSH 的单路径契约对齐

- **决定**：删除 `AssistantMessage | AsyncIterator[...]` 双返回类型和直接消息分支。所有 ModelAdapter——包括一次性测试替身——都实现同一个 `stream()` 协议；AgentLoop 始终消费事件流并等待 `AssistantStreamEnd`。
- **与 pi 的关系**：pi 的 Agent `StreamFn` 只返回 `AssistantMessageEventStream`，其 `complete()` 也是消费 stream 后取 `result()` 的便利包装。当前实现与它保持相同的单路径 Adapter 形状，但没有复制低层 `context.messages` 尾项替换；partial 仍只存在于运行事件。
- **与 DSH 的关系**：DSH Adapter 唯一必需方法也是 `stream()`，返回 `AsyncIterable<StreamChunk>`。当前实现与它保持相同的单路径入口，但暂未实现 `AssistantStreamAttempt`、原始 stream、block assembler 和 attempt settlement。
- **阶段 1 取舍**：内核累积文本 draft，adapter 在 `AssistantStreamEnd` 中给出权威 final，当前不要求二者内容相等。这保持协议最小，但意味着本层暂不负责 reasoning／tool-call delta 的完整组装，也不能独立重放 provider stream。
- **阶段 2 演进**：EventStore 设计时再引入稳定 `attempt_id`、revision 和 settlement 事件；只持久化 settlement 或原始流引用，不持久化 UI update。需要恢复失败尝试时新增非消息型 attempt record，并区分用户取消、provider 失败与无安全可见内容的取消。

## D-13 阶段 2 采用 DSH 主干 + pi 局部扩展的流式折中方案

- **决定**：Provider Adapter 只负责把供应商私有协议翻译为最小 canonical chunk；Core Assembler 统一构造 `AssistantMessage`、判断安全取消内容，并通过稳定 `attempt_id` settlement 到 EventStore。
- **最小公共协议**：第一版只覆盖 text、tool call、usage 和 finish。只有影响 Agent 控制流、恢复或跨 Provider 评测的字段才能进入 canonical 协议；图片、音频、citation 等没有当前需求时不提前加入。
- **局部扩展**：Provider 私有但 Core 不需要解释的数据，放入包含 `provider`、`schema_version` 和 JSON `data` 的 opaque replay state。Core 只校验、保存和回传；对应 Adapter 负责解释，避免每个私有字段都扩张公共协议。
- **持久化边界**：UI draft/update 是瞬时信号，不直接作为恢复日志；EventStore 记录 attempt start／settlement、正式或安全中断消息，以及按需保存的压缩原始流或引用。失败或无安全内容的 attempt 不伪装成 `AssistantMessage`。
- **限制**：该方案能在已实现范围内获得 DSH 类似的取消、恢复和观察边界，但不会自动拥有 DSH 全部功能；一旦 Provider 新字段会影响 Agent 行为，就必须显式扩展 canonical 协议和 Core，而不能藏进 opaque metadata。

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
| 取消后限时退出且不再追加执行事件 | `test_cancellation_during_a_tool_closes_promptly_without_result_events`、`test_pre_cancelled_run_only_emits_the_lifecycle_boundary` |
