# Minimal Agent 学习进度

本文件只记录进度与证据；学习范围、实施顺序和验收定义以 [plan.md](./plan.md) 为准。

状态标记：`未开始`、`进行中`、`已完成`、`跳过`、`阻塞`。只有对应验收通过后，阶段才能标为“已完成”。

## 时间预算

- 截止日期：2026-10-07（国庆假期结束前）
- 学习周期：2026-09-26 至 2026-10-07，共 12 天
- 计划投入：每天 7 小时有效学习时间，共 84 小时
- 每日参考：源码阅读 3 小时、实现与测试 3 小时、总结与补漏 1 小时

| 日期 | 计划时长 | 状态 | 当日内容／备注 |
|---|---:|---|---|
| 09-26 | 7h | 已完成（跨日） | mini-swe-agent、Tau、pi 核心阅读及最小循环实现全部完成 |
| 09-27 | 7h | 进行中 | Day 02：完成Event层与取消事件顺序，记录设计决定并收尾阶段1 |
| 09-28 | 7h | 未开始 | — |
| 09-29 | 7h | 未开始 | — |
| 09-30 | 7h | 未开始 | — |
| 10-01 | 7h | 未开始 | — |
| 10-02 | 7h | 未开始 | — |
| 10-03 | 7h | 未开始 | — |
| 10-04 | 7h | 未开始 | — |
| 10-05 | 7h | 未开始 | — |
| 10-06 | 7h | 未开始 | — |
| 10-07 | 7h | 未开始 | — |
| **合计** | **84h** | — | — |

## 当前状态

| 当前阶段 | 状态 | 开始日期 | 最近更新 | 下一步 |
|---|---|---|---|---|
| 阶段 1：最小循环 | 进行中 | 2026-09-26 | 2026-09-27 | Day 01已完成；Day 02实现Event层并验证取消后不再产生执行事件 |

## 每日收尾规则

每天结束前必须完成以下记录：

1. 写明实际完成的阅读、实现和测试证据。
2. 将没有完成或有意推迟的内容加入“延期账本”。
3. 每个延期项写明原因、明确的完成日期或阶段、届时的验收方式。
4. 检查今天到期的延期项；未完成则重新排期并说明原因，不能静默顺延。

测试、测试替身和边界用例由 AI 编写与维护；学习者主要实现生产代码并理解测试契约。测试必须覆盖当前范围内的正常、失败、边界、取消、顺序、不可变性、替换性及相关恢复风险。

## 延期账本

| ID | 来源 | 延期内容 | 原因 | 计划完成 | 验收方式 | 状态 |
|---|---|---|---|---|---|---|
| D1-01 | Day 01 | AgentEvent类型、事件sink及取消后的事件顺序 | Day 01限定为消息与最小循环，尚未引入Event层 | Day 02（2026-09-27），阶段1收尾前 | 测试证明生命周期闭合，取消后不再发出新的模型／工具执行事件 | 待完成 |
| D1-02 | Day 01 | 流式草稿、文本delta和最终不可变AssistantMessage提交边界 | 当前只有一次性FakeModel返回，缺少流式协议 | Day 02（2026-09-27），与Event层一起完成 | 流式测试证明partial不进入正式历史，完成或取消后只提交一个final／aborted消息 | 待完成 |
| D1-03 | Day 01 | lossless JSON严格校验、循环引用／非有限浮点拒绝及freeze对应的序列化转换 | 属于EventStore持久化边界，不应塞进最小循环 | Day 03（2026-09-28），阶段2开始时 | 循环、NaN／Infinity、非法对象测试；freeze→序列化→读取往返一致 | 待完成 |
| D1-04 | Day 01 | 用户编辑旧消息时的`parent_id`分支与当前上下文投影 | 依赖EventStore和ContextBuilder | 阶段2持久化与恢复期间 | 原分支保留，新分支不包含旧回复；两条分支均可独立恢复 | 待完成 |
| D1-05 | Day 01 | CI workflow 首次运行确认 | 需推送到远程后由 GitHub Actions 执行，推送属外部动作 | Day 02 内（推送后） | workflow `day-01-minimal-agent` 首次运行三步全绿（Ruff／mypy／pytest） | 待完成 |

## 开工清单

- [x] 确认 Python 3.12+ 与首个 OpenAI-compatible 模型协议选择
- [x] 在出现第一批测试时配置 test、lint 和 CI
      - lint／类型检查在 `pyproject.toml`：Ruff（E/F/I/UP/B/SIM）+ mypy strict；CI 见 `.github/workflows/day-01-minimal-agent.yml`。
      - 本地以 CI 的同一组命令验证通过：`uv sync --locked`、`uv run ruff check .`、`uv run mypy src tests`、`uv run pytest -q`（58 passed）。
      - 该 workflow 尚未在 GitHub 上运行过（未推送），首次运行确认见延期账本 D1-05。
- [ ] 对一个隔离候选执行最小 smoke test，并记录结果或备用路线

开工清单不构成独立阶段，未全部完成不妨碍开始阶段 1。

## 阶段 1：最小循环

状态：进行中

### 今日清单：2026-09-26

1. [x] 学习 mini-swe-agent
   - 阅读 `src/minisweagent/agents/default.py`：重点看 `run → step → query → execute_actions`，以及完成、工具失败、格式错误、预算耗尽和 trajectory 保存分别如何退出或继续。
   - 阅读 `src/minisweagent/environments/local.py`：重点看命令如何执行，stdout／stderr、退出状态、异常和环境变量如何返回给 Agent。
2. [x] 学习 Tau（Python 理解桥梁）
   - 阅读 `src/tau_agent/messages.py`：看 `UserMessage`、`AssistantMessage`、`ToolCall` 与 `ToolResultMessage` 如何组成 transcript。
   - 阅读 `src/tau_agent/tools.py`：看工具定义、异步 `execute`、结构化结果和错误边界。
   - 阅读 `src/tau_agent/events.py`：区分消息历史与供 UI／调用方消费的生命周期事件。
   - 阅读 `src/tau_agent/loop.py`：只跟 `run_agent_loop → _assistant_events → _execute_tool_call → _run_tool` 主线。
   - 阅读 `tests/test_agent_loop.py` 中正常流式回答、一次工具调用、未知工具和工具异常测试；不读 TUI、provider 实现与配置系统。
3. [x] 学习 pi，并与 Tau 对照
   - 阅读 `packages/agent/src/types.ts`：区分内部消息、模型输入、工具调用／结果和对外事件。
   - 阅读 `packages/agent/src/agent-loop.ts` 与 `packages/agent/test/agent-loop.test.ts`：重点看主循环如何推进、工具结果如何回填，以及正常完成和工具失败的测试写法。
   - 重点记录 pi 相比 Tau 增加或不同的语义：并行工具、取消、steering／follow-up、事件发出顺序和持久化顺序。
4. [x] 微型实现目标
   - 不复制参考实现，写出核心消息类型、最小 `ModelAdapter`、`ToolExecutor` 和约 100 行的 `AgentLoop`：FakeModel 能请求一次工具并在拿到结果后给出最终答案；同时用测试证明正常路径可以完成、工具抛错时不会被误判为正常完成。
   - 本阶段不实现 CLI、TUI、真实模型请求、真实 shell、持久化、并行工具或插件系统。

今日完成标准：能解释三个项目的循环边界以及 Tau 与 pi 的关键差异，并提交一个通过“正常完成”和“工具失败”两条测试的最小执行循环。

Day 01 状态：已完成。三个项目的核心阅读、不可变消息类型、两套可替换Adapter、最小AgentLoop及58项测试均已完成。

手搓目录：`01-harness/day-01/minimal-agent/`。按 `types → fakes → agent-loop → tests` 的顺序推进，每一关完成后先检查再继续。

### 阅读

- [x] 阅读 `DefaultAgent` 的 `run → step → query → execute_actions`
- [x] 阅读 `LocalEnvironment` 的命令、输出、退出状态和环境处理
- [x] 阅读 Tau 的消息、工具、事件、loop 及相关测试
- [x] 阅读 pi 的消息、工具与事件类型
- [x] 阅读 pi 的 agent loop 及相关测试

### 产出

- [x] 实现最小 `ModelAdapter`
- [x] 实现最小 `ToolExecutor`
- [x] 实现最小 `AgentLoop`
- [x] 记录本阶段的关键设计决定：见 `01-harness/day-01/minimal-agent/DECISIONS.md`（D-01～D-09，每条含代码位置与测试证据）
- [ ] 阶段 1 验收后筛选一个无人认领、没有重复 PR 的 Tau 或其他 Harness issue

### 验收

- [x] 正常完成路径通过
- [x] 工具失败路径通过
- [x] 连续格式错误达到阈值后退出
- [x] 预算耗尽路径通过
- [x] 更换第二套假 ModelAdapter 后以上测试仍通过
- [x] 更换第二套假 ToolExecutor 后以上测试仍通过
- [ ] 取消后在设定超时内退出，且不再追加执行事件

### 阶段记录

- 开始日期：2026-09-26
- 完成日期：—（等待 Day 02 的最后一项验收）
- commit／产物：Day 01 微型实现（58 项测试）+ `DECISIONS.md` + CI workflow；commit 锚点 `e782430`（见下方日志）
- 结论与遗留问题：核心循环与四条验收路径已通过，第二套 Adapter／ToolExecutor 替换已验证；最后一项"取消后不再追加执行事件"依赖事件层（D1-01），流式提交边界为 D1-02，均在 Day 02 完成

## 阶段 2：持久化与恢复

状态：未开始

- [ ] 阅读 pi session manager、Maka runtime event 与恢复测试
- [ ] 冻结事件 v1 前核对 OpenInference 关联标识和 OrcaReplay run 血缘
- [ ] 实现 EventStore、上下文投影和 schema 迁移
- [ ] 完成三个工具边界的崩溃注入测试
- [ ] 验证未知副作用不会自动重试
- [ ] 通过阶段 2 的全部验收

产物与结论：—

## 阶段 3：观测与基础评测

状态：未开始

- [ ] 阅读 OpenInference 指定语义与 Inspect 任务、评分协议
- [ ] 建立 20–30 个固定任务及 baseline
- [ ] 验证并发 trace 关联、取消与异常结束 span
- [ ] 验证 exporter 故障不改变 Agent 行为
- [ ] 确认任务仅使用假工具、良性输入或一次性容器
- [ ] 通过阶段 3 的全部验收

产物与结论：—

## 阶段 4：执行隔离

状态：未开始

- [ ] 阅读 srt 与 Gondolin 指定模块
- [ ] 接入一个隔离执行后端
- [ ] 用阶段 3 任务集比较切换前后的确定性结果
- [ ] 验证超时、取消、路径、网络和资源清理
- [ ] 通过阶段 4 的全部验收

产物与结论：—

## 阶段 5：工程闭环

状态：未开始

- [ ] 阅读 Opik 与 Harbor 指定模块
- [ ] 将至少一个真实失败样本加入 CI 回归集
- [ ] 独立区分环境、Agent 与 verifier 失败
- [ ] 验证异常生命周期下的资源回收
- [ ] 通过阶段 5 的全部验收

产物与结论：—

## 阶段 6：专项能力

状态：未开始

- [ ] 明确是否存在回放或插件需求
- [ ] 有回放需求时验证匹配偏差、divergence 和 parent run
- [ ] 有插件需求时验证工具、监听器和后台任务全部卸载
- [ ] 无明确需求时记录原因并标记跳过

产物与结论：—

## 阶段 7：长期记忆

状态：未开始

- [ ] 阅读 memU、LangMem 指定模块并选择一个工程后端
- [ ] 在实验前确定成功率、过时引用、费用和延迟阈值
- [ ] 对比无记忆和记忆版本
- [ ] 验证新增、纠正、删除、过期及用户／项目隔离
- [ ] 通过阶段 7 的全部验收

产物与结论：—

## 开源贡献支线

| 候选 | 状态 | 复现证据 | 提交／讨论 | 备注 |
|---|---|---|---|---|
| 待选择 | 未开始 | — | — | 阶段 1 优先选择范围小、可补回归测试的问题 |

## 学习日志

按日期追加简短记录，链接到代码、测试、笔记或实验结果，避免只记录“读过”。

### 2026-09-26

- 建立学习进度表，当前准备从阶段 1 开始。
- 完成 mini-swe-agent 的最小循环、Environment、退出、失败分类和 trajectory 学习。

### 2026-09-27

- 完成 Tau 的消息、工具、事件、主循环与核心测试阅读。
- 关键结论：完整历史与运行事件分离；工具结果通过 `tool_call_id` 关联；普通工具异常转为错误结果；当前 Tau 工具批次实际顺序执行，且 `on_update` 在工具结束后才集中发出。
- 完成 pi 的消息投影、并行工具、取消、steering／follow-up、截断响应和流式消息持久化边界阅读。
- 对照结论：事件完成顺序可以不同于持久化顺序；取消必须传到底层；partial只存在于运行状态与update事件，正式增量只记录final message。
- 第一日阅读结束时将微型实现顺延到恢复后继续，随后已经完成。
- 实践策略调整为“每阶段微型手搓 + 对应开源 issue + 最终整合项目”；开源贡献替代大型练习，但不替代核心机制测试。
- 核对 Tau #382：与刚学的实时工具进度高度匹配，但已有认领者和开放 PR #519，因此不重复实现。
- 确定自己的微型练习和后续 `minimal-harness` 先使用 Python 3.12+；pi 的 TypeScript 保留为语义参考。
- 完成 Day 01 第一关：不可变消息、工具调用／结果、取消与 ModelAdapter／ToolExecutor 协议；导入、Ruff、mypy和运行时不可变性检查通过。
- 测试由助教侧编写和维护，生产代码由学习者手搓；当前类型层覆盖 23 个测试，pytest、Ruff和mypy strict全部通过。
- 助教完成 ScriptedModel、ScriptedToolExecutor、FakeCancellationToken 及其 10 项自测试；完成 AgentLoop 第一批 12 项行为测试，目前因 `run_agent_loop()` 尚未实现而处于预期红灯。
- 完成最小 AgentLoop及取消检查；当前49项测试、Ruff和mypy strict全部通过，覆盖正常完成、顺序工具、工具异常隔离、硬退出、输入隔离、步数上限和取消传播。
- 完成连续格式错误反馈、阈值、成功清零、步数计费及阈值0语义；当前55项测试、Ruff和mypy strict全部通过。
- 完成行为驱动的 RuleBasedEchoModel 与 EchoToolExecutor 替换验证；两者不继承 Protocol，mypy 通过结构化类型确认兼容，当前58项测试全绿。
- Day 01 收尾：补齐 `.gitignore`（此前 `__pycache__/*.pyc` 会被误提交）、`DECISIONS.md`（D-01～D-09 关键设计决定，含代码位置与测试证据）与 CI workflow（`.github/workflows/day-01-minimal-agent.yml`）。
- 以 CI 的同一组命令在本地验证通过：`uv sync --locked`、`uv run ruff check .`、`uv run mypy src tests`、`uv run pytest -q`（58 passed）。
- 建立 Day 01 commit 锚点：`e782430`（微型实现、设计决定、CI 随此提交入库）。
- 遗留：CI 尚未在 GitHub 首次运行（未推送），见 D1-05；阶段 1 最后一项验收"取消后不再追加执行事件"依赖 Day 02 的事件层（D1-01）。
- 环境备注：本地 `uv` 默认缓存目录不可写，运行 `uv` 需设置 `UV_CACHE_DIR` 指向工作区内目录（如项目下的 `.uv-cache`，已加入 `.gitignore`）。
