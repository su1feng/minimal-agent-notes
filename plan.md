# Minimal Agent 学习与工程计划

目标：参考 pi 的 minimal 理念，自研可取消、可恢复、可观察、可评测的 Agent 执行内核，并积累实际的开源贡献。

选型依据为源码、文档与测试阅读，核验于 2026-09-26。阅读时固定 commit；工程接入后自行验证目标场景。

## 使用方式

第 1–4 章按能力领域分类，是各阶段的定向阅读索引，不代表实施先后。唯一实施主干以第 5 节的阶段表为准，按阶段 1–7 推进；开源贡献是并行支线，不以章节位置表示开始时间。

每个阶段采用“为当前设计问题阅读 → 形成实现或实验 → 运行验收”的短循环，不先读完全部仓库。只读条目列出的模块及直接相关测试；当本阶段的设计问题已有证据、验收通过后停止扩展阅读。只有验收失败、关键决策缺少证据或下一阶段需要时，才继续读取补充项目。

工程实践采用三层结构：每个阶段保留一个只验证核心机制的微型手搓；学习到相应能力后，优先寻找范围清晰、无人认领且没有重复 PR 的真实开源 issue；最后把各阶段已经验证的部件整合成自己的 Minimal Agent。微型手搓不追求产品功能，禁止提前扩展 CLI、TUI、真实 provider 或与当前验收无关的抽象。

### 测试责任与覆盖规则

- 测试、测试替身和边界用例由 AI 编写和维护；学习者负责理解契约并实现生产代码，除非明确把某段实现委托给 AI。
- 每项行为先建立可复现测试或在实现同时补齐测试。测试失败时优先修生产代码；只有契约本身经讨论发生变化时才能修改既有断言，不能为了转绿而削弱测试。
- 覆盖按风险维度而不是只追求行覆盖率：正常路径、空值和边界值、非法输入、普通失败、取消／超时、顺序与并发、不可变性与别名、资源清理、适配器替换，以及涉及持久化时的崩溃恢复、迁移和重复执行。
- 每个已修复 bug 必须留下回归测试。每天结束时至少运行相关 pytest、Ruff 和 mypy strict；阶段验收时运行全套检查。
- “全面测试”表示覆盖当前已声明契约及已知风险，不表示提前测试尚未进入范围的未来功能。未来功能进入范围时再扩展测试。

### 时间目标

- 学习周期：2026-09-26 至 2026-10-07，共 12 天；最晚在国庆假期结束前完成。
- 总预算：84 小时有效学习时间，平均每天 7 小时；休息不计入有效时间，每天实际预留约 8–9 小时。
- 每日默认结构：源码阅读 3 小时、实现与测试 3 小时、总结与补漏 1 小时。允许按当天任务调整，不记录或累计实际学习时长。
- “完成”指阶段 1–7 按第 5 节规则通过验收；阶段 6 没有明确需求时可以按规则记录后跳过。每日安排和实际用时记录在 `progress.md`。

## 项目总览

每部分学习与工程通常各选 1–2 个项目；特别推荐只读指定模块，并计入总数。Harness 额外加入 Tau 作为从 Python 过渡到 pi 的对照材料，不扩大到其 TUI 和 provider 实现。工程侧按场景选择，不要求全部接入。“去重项目数”按仓库去重，同一项目同时出现在学习与工程栏时只计一次。

| 部分 | 学习目标 | 工程目标 | 特别推荐 | 去重项目数 |
|---|---|---|---|---:|
| Harness | mini-swe-agent、Tau、pi | pi、Maka、DSH 局部 | DSH：流式 attempt／插件生命周期 | 5 |
| Memory | memU、LangMem | Mem0、Hindsight | — | 4 |
| Sandbox | srt、Gondolin | Gondolin、OpenSandbox | Codex：路径与权限策略 | 4 |
| Observability & Evaluation | OpenInference、Inspect AI | Opik、Harbor | OrcaReplay：回放与分叉 | 5 |

## 1. Harness

### 学习目标

#### mini-swe-agent：最小执行闭环

[仓库](https://github.com/SWE-agent/mini-swe-agent)。用它理解 Model、Agent、Environment 的边界。

##### 执行循环与退出

读 [DefaultAgent](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/agents/default.py)：`run → step → query → execute_actions`、预算、格式错误、异常与 trajectory 保存。

##### 执行环境

读 [LocalEnvironment](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/environments/local.py)：命令执行、输出、退出状态和环境替换。

**实践：**用假模型实现正常完成、工具失败、连续格式错误、预算耗尽四条路径。保存轨迹与崩溃恢复分别设计。

#### Tau：用 Python 对照消息、工具、事件与循环

[仓库](https://github.com/huggingface/tau)。它是受 pi 启发的 Python 移植项目，用作理解桥梁，不替代 pi 这个主参考。

##### 可持久化消息与工具边界

读 [messages.py](https://github.com/huggingface/tau/blob/main/src/tau_agent/messages.py) 和 [tools.py](https://github.com/huggingface/tau/blob/main/src/tau_agent/tools.py)：`UserMessage`、`AssistantMessage`、`ToolCall`、`ToolResultMessage`、`AgentTool` 与 `AgentToolResult` 的边界。

##### 事件驱动循环

读 [events.py](https://github.com/huggingface/tau/blob/main/src/tau_agent/events.py)、[loop.py](https://github.com/huggingface/tau/blob/main/src/tau_agent/loop.py) 和 [测试](https://github.com/huggingface/tau/blob/main/tests/test_agent_loop.py)：provider stream 如何变成 agent events，工具结果如何回填 transcript，工具异常如何转成错误结果。

**实践：**只把 Tau 用于概念映射：先用 Python 说明一次“模型请求工具 → 执行 → 结果回填 → 模型完成”，再到 pi 核对并行工具、取消、steering／follow-up 和事件顺序。Tau 与 pi 不一致时，以 pi 的源码和测试为工程语义依据。

#### pi：核心接口与交互语义

[仓库](https://github.com/earendil-works/pi)。主参考，先读 agent 核心，再读必要的 coding-agent 模块。

##### 消息、工具与事件

读 [types.ts](https://github.com/earendil-works/pi/blob/main/packages/agent/src/types.ts)：内部消息、模型输入、工具结果与对外事件的区别。

##### 循环、取消与插入消息

读 [agent-loop.ts](https://github.com/earendil-works/pi/blob/main/packages/agent/src/agent-loop.ts) 和 [测试](https://github.com/earendil-works/pi/blob/main/packages/agent/test/agent-loop.test.ts)：steering／follow-up、并行工具、取消、截断响应、完成顺序与持久化顺序。

### 工程目标

#### pi：可替换、可持久化的内核

##### 会话与上下文投影

读 [session-manager.ts](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/src/core/session-manager.ts)：追加写 JSONL、`parentId` 分支树、版本迁移及上下文构建。

**实践：**实现 ModelAdapter、ToolExecutor、EventStore；模型可替换，取消可传递，完整历史与当前模型输入分离。EventStore 的 v1 事件至少保留 `schema_version`、`event_id`、`run_id`、因果／父级 ID、时间和原始载荷引用，并有版本迁移测试。冻结 v1 前提前核对 OpenInference 的关联标识和 OrcaReplay 的 run 血缘需求，但不把 trace 字段或回放录制正文直接耦合进恢复事件。

#### Maka：事件事实与恢复

[仓库](https://github.com/apache/maka)。只读运行时模块。

##### 事件日志与执行归属

读 [架构](https://github.com/apache/maka/blob/main/ARCHITECTURE.md)、[runtime-event.ts](https://github.com/apache/maka/blob/main/packages/core/src/runtime-event.ts)：单一执行归属，以及上下文、界面、恢复状态如何从日志投影。

##### 崩溃状态分类

读 [agent-run-recovery.ts](https://github.com/apache/maka/blob/main/packages/runtime/src/agent-run-recovery.ts)、[恢复测试](https://github.com/apache/maka/blob/main/packages/runtime/src/__tests__/agent-run-recovery.test.ts)。

**实践：**在工具执行前、执行成功后、结果持久化前分别终止进程；恢复后区分已完成、未执行、结果未知，对未知副作用先核对。

#### DSH：统一流、组装与 attempt settlement

只读 `packages/llm/llm/src/types.ts` 的 `StreamChunk`、`assembler.ts`，以及 `packages/core/agent-loop/src/assistant-stream.ts` 和 `agent.ts` 的模型流 settlement 路径。学习 Adapter 只翻译 Provider 私有协议、Core 统一组装消息，以及成功消息、失败 attempt 和安全中断消息的区别。

**实践：**阶段 2 把当前 `AssistantTextDelta`／`AssistantStreamEnd` 演进为最小 canonical stream；第一版只包含 text、tool call、usage 和 finish。Provider 私有但不影响 Agent 决策的数据放入带 `provider` 与 `schema_version` 的 opaque replay state。Core 通过统一 Assembler 生成 `AssistantMessage`，再以稳定 `attempt_id` settlement 到 EventStore；UI update 不作为恢复事件持久化。

### 特别推荐：DSH——插件生命周期

[仓库](https://github.com/deepseek-ai/deepseek-harness)。在核心运行稳定、确有插件需求后阅读。

#### 作用域、注册与卸载

读 [架构](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.md)、[scope 生命周期测试](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/agent-loop/tests/scope-lifecycle.spec.ts)。

**实践：**插件注册工具、监听器和后台任务；卸载后验证三者全部释放。借鉴生命周期设计，按需引入配置层叠与插件机制。

## 2. Memory

### 学习目标

#### memU：可读记忆与增量提交

[仓库](https://github.com/NevaMind-AI/memU)。学习 Agent 整理 Markdown、存储层负责索引与检索的职责划分。

##### prepare → 整理 → commit

读 [lifecycle.py](https://github.com/NevaMind-AI/memU/blob/main/src/memu/app/memorize/lifecycle.py)：会话物化、已有记忆镜像、变更提交。

##### 失败重试

读 [生命周期测试](https://github.com/NevaMind-AI/memU/blob/main/tests/test_memorize_lifecycle.py)：分页、增量提交、禁止重入、失败后保留重试条件。

**实践：**实现带来源和作用域的可读记忆，支持增量更新与失败重试。

#### LangMem：结构化抽取与后台更新

[仓库](https://github.com/langchain-ai/langmem)。重点读记忆变更机制；其 LangChain／LangGraph 依赖不必进入自己的核心。

##### 抽取、修订与删除

读 [extraction.py](https://github.com/langchain-ai/langmem/blob/main/src/langmem/knowledge/extraction.py) 和 [tools.py](https://github.com/langchain-ai/langmem/blob/main/src/langmem/knowledge/tools.py)：schema、existing memories、增删改开关、namespace 与 store。

##### 后台执行

读 [reflection.py](https://github.com/langchain-ai/langmem/blob/main/src/langmem/reflection.py)：队列、Future、延迟任务和 shutdown。本地线程队列的持久性需要另外解决。

**实践：**验证“新增事实 → 用户纠正 → 删除请求”；比较同步更新与后台更新的延迟、可见性和失败行为。

### 工程目标

#### Mem0：记忆接口与作用域隔离

[仓库](https://github.com/mem0ai/mem0)。适合练习独立记忆层的接入与存储适配。

##### 写入与检索

读 [memory/main.py](https://github.com/mem0ai/mem0/blob/main/mem0/memory/main.py)：提取、过滤、过期、错误传播和后端接口。

##### 用户与会话隔离

读 [test_session_scope.py](https://github.com/mem0ai/mem0/blob/main/tests/memory/test_session_scope.py)。scope 过滤之外，服务端仍需认证与授权。

**实践：**验证用户／项目隔离、删除与过期、模型及 embedding 故障；以实际使用的开源版本测量效果。

#### Hindsight：复杂检索与写入一致性

[仓库](https://github.com/vectorize-io/hindsight)。作为更深入的记忆服务参考。

##### 多路检索

读 [retrieval.py](https://github.com/vectorize-io/hindsight/blob/main/hindsight-api-slim/hindsight_api/engine/search/retrieval.py)：语义、关键词、图、时间相关检索及候选限制。

##### 并发与重复写入

读 [delta retain 测试](https://github.com/vectorize-io/hindsight/blob/main/hindsight-api-slim/tests/test_delta_retain_duplicates.py)：重复 upsert、并发、旧请求及元数据投影。

**实践：**构造事实变化、时间限定和重复写入任务，与无记忆及简单记忆版本比较成功率、过时信息引用、费用和延迟。

## 3. Sandbox

### 学习目标

#### srt：独立进程沙箱

[仓库](https://github.com/anthropics/sandbox-runtime)。理解 CLI／库如何把配置落实为 OS 强制限制。

##### 初始化、包装与清理

读 [sandbox-manager.ts](https://github.com/anthropics/sandbox-runtime/blob/main/src/sandbox/sandbox-manager.ts)：`initialize → wrapWithSandbox → cleanupAfterCommand/reset`，区分共享 runtime 与单命令资源。

##### 隔离与失败处理

结合 [实现说明](https://github.com/anthropics/sandbox-runtime#implementation-details)，读 [配置加载测试](https://github.com/anthropics/sandbox-runtime/blob/main/test/cli-config-loading.test.ts) 和 [客户端中断测试](https://github.com/anthropics/sandbox-runtime/blob/main/test/sandbox/client-abort.test.ts)。关注配置失败、代理中断、文件读写与网络限制。

**实践：**在测试目录验证限制及清理。代理环境变量本身不是安全边界，默认读取权限也不等于仅工作区可读。

#### Gondolin：microVM 与宿主控制

[仓库](https://github.com/earendil-works/gondolin)。

##### 文件、网络与凭据边界

读 [架构](https://github.com/earendil-works/gondolin/blob/main/docs/architecture.md)、[安全设计](https://github.com/earendil-works/gondolin/blob/main/docs/security.md)：宿主策略、客体访问、placeholder 与凭据注入。

##### checkpoint 范围

读 [limitations](https://github.com/earendil-works/gondolin/blob/main/docs/limitations.md)：磁盘 checkpoint、tmpfs 与进程／RAM 状态的区别。

### 工程目标

#### Gondolin：本地隔离执行后端

##### 执行适配

读 [exec.ts](https://github.com/earendil-works/gondolin/blob/main/host/src/exec.ts)、[pi 接入例子](https://github.com/earendil-works/gondolin/blob/main/host/examples/pi-gondolin.ts)。

**实践：**为 ToolExecutor 增加 microVM 后端，验证超时、取消、挂载、网络策略和清理。

#### OpenSandbox：沙箱生命周期服务

[仓库](https://github.com/opensandbox-group/OpenSandbox)。用于服务化阶段，先从单机后端开始。

##### 生命周期 API

读 [lifecycle.py](https://github.com/opensandbox-group/OpenSandbox/blob/main/server/opensandbox_server/api/lifecycle.py)：创建、查询、删除、续租、暂停恢复、快照与 endpoint。

**实践：**模拟客户端掉线、创建失败、worker 重启和任务过期，验证状态核对与资源回收。

### 特别推荐：Codex sandbox——复杂路径与权限策略

#### OS 边界与审批

读 [linux-sandbox README](https://github.com/openai/codex/blob/main/codex-rs/linux-sandbox/README.md)、[bwrap.rs](https://github.com/openai/codex/blob/main/codex-rs/linux-sandbox/src/bwrap.rs) 和 [execpolicy](https://github.com/openai/codex/blob/main/codex-rs/execpolicy/README.md)。

关注只读根、可写子目录、受保护路径、符号链接与子进程。用它对照实际 Coding Agent 的集成方式，区分审批决定与技术强制边界。

## 4. Observability & Evaluation

观测解释运行过程，评测判断任务效果，回放支持复现与调试。三者形成“运行 → 定位失败 → 固定样本 → 比较改动”的循环。

### 学习目标

#### OpenInference：trace 语义与埋点

[仓库](https://github.com/arize-ai/openinference)。

##### 调用关系与数据模型

读 [语义约定](https://github.com/arize-ai/openinference/blob/main/spec/semantic_conventions.md)、[工具调用](https://github.com/arize-ai/openinference/blob/main/spec/tool_calling.md)：span 关系、tool_call_id、模型／工具／检索数据。

##### 字段隐藏与追踪控制

读 [config.py](https://github.com/arize-ai/openinference/blob/main/python/openinference-instrumentation/src/openinference/instrumentation/config.py)。接后端时核对 OpenInference 与 OTel GenAI 字段映射。

**实践：**并发 span 不串线，取消与错误能结束 span，导出故障不改变 Agent 行为。

#### Inspect AI：评测任务与评分协议

[仓库](https://github.com/UKGovernmentBEIS/inspect_ai)。

##### Task 与执行环境

读 [task.py](https://github.com/UKGovernmentBEIS/inspect_ai/blob/main/src/inspect_ai/_eval/task/task.py)：dataset、setup、solver／agent、scorer、sandbox 和重复运行。

##### Scorer

读 [评分协议](https://github.com/UKGovernmentBEIS/inspect_ai/blob/main/src/inspect_ai/scorer/_scorer.py)：目标、结果与汇总指标；区分评分器故障和 Agent 低分。

**实践：**用 20–30 个小任务建立 baseline，优先确定性检查工具参数、状态和产物，再增加经过校准的主观评分。阶段 4 的隔离后端完成前，只允许假工具、无副作用的本地任务或一次性容器；禁止运行不受信任仓库代码、任意访问网络或写入测试目录之外的宿主路径。

### 工程目标

#### Opik：运行记录到回归评测

[仓库](https://github.com/comet-ml/opik)。重点看 Python SDK 的观测与评测链路。

##### 流式追踪

读 [generator_wrappers.py](https://github.com/comet-ml/opik/blob/main/sdks/python/src/opik/decorator/generator_wrappers.py)、[root span 测试](https://github.com/comet-ml/opik/blob/main/sdks/python/tests/unit/decorator/test_tracker_root_span.py)：迭代上下文、span 生命周期、输出与异常。

##### 评测执行与失败语义

读 [evaluator.py](https://github.com/comet-ml/opik/blob/main/sdks/python/src/opik/evaluation/evaluator.py)、[任务执行器](https://github.com/comet-ml/opik/blob/main/sdks/python/src/opik/evaluation/engine/evaluation_tasks_executor.py)：重复试验、线程上下文、`scoring_failed` 与统计处理。

**实践：**失败样本进入固定任务集，对比修改前后并接入 CI。选择一种埋点方式，验证字段映射，避免重复采集。

#### Harbor：执行型 Agent 的环境与验证

[仓库](https://github.com/harbor-framework/harbor)。适合终端／编码任务；业务对话任务可用 Inspect 自建环境与评分器。

##### 环境协议

读 [BaseEnvironment](https://github.com/harbor-framework/harbor/blob/main/src/harbor/environments/base.py)：能力、资源、网络、执行与产物访问。

##### Trial 与 verifier

读 [Trial](https://github.com/harbor-framework/harbor/blob/main/src/harbor/trial/trial.py)：环境启动、Agent、verifier、超时分类和清理。

**实践：**接入自己的 Agent，完成 5–10 个固定容器任务；独立校验产物，分别记录环境、Agent 与验证器失败。

### 特别推荐：OrcaReplay——回放与分叉机制

[仓库](https://github.com/Continuum-AI-Corp/OrcaReplay)。限定为源码学习与隔离实验。

#### 请求匹配与偏差

读 [matching.ts](https://github.com/Continuum-AI-Corp/OrcaReplay/blob/main/packages/proxy/src/matching.ts)：规范化匹配、近似匹配、无法匹配及偏差报告。

#### 回放血缘与错误记录

读 [replay.ts](https://github.com/Continuum-AI-Corp/OrcaReplay/blob/main/packages/cli/src/commands/replay.ts)、[测试](https://github.com/Continuum-AI-Corp/OrcaReplay/blob/main/packages/cli/test/replay-trace.test.ts)：独立 run、parent_run、divergence 与错误保留。

**实践：**区分历史展示、录制响应驱动的重运行、分叉执行。回放可能真实执行工具，不能恢复任意外部系统；在临时隔离环境验证。项目文档存在漂移，按同一版本代码和测试交叉核对。

## 5. 实施顺序与验收

### 开工清单（不设阶段，不阻塞阶段 1）

- 第一版使用 Python 3.12+ CLI，首个外部模型协议采用 OpenAI-compatible Chat Completions（含流式与 tool calls）；provider 类型不得进入核心接口。pi 的 TypeScript 只用于学习语义，不要求自己的实现沿用其语言。
- 阶段 1 出现第一批测试时建立测试、lint 和 CI，不为搭脚手架推迟源码阅读。
- 用 bwrap、容器或 Gondolin 候选执行一次最小命令并记录结果；这只是提前排雷，完整隔离在阶段 4 实现。当前候选不可用时记录可复现失败和备用路线，不阻塞阶段 1。

| 阶段 | 参考与工作 | 可执行验收 |
|---|---|---|
| 1. 最小循环 | mini-swe-agent、Tau（Python 对照）、pi（主参考）；微型实现只含核心类型、FakeModel、FakeTool、约 100 行 AgentLoop 及测试 | 替换第二套假 ModelAdapter 和假 ToolExecutor 后，正常完成、工具失败、连续格式错误达到阈值、预算耗尽四条路径测试全部通过；取消后在设定超时内退出且不再追加执行事件 |
| 2. 持久化与恢复 | pi、Maka、DSH 流式 attempt；先冻结最小 canonical stream、Core Assembler 与 attempt settlement，再核对 OpenInference 关联标识及 OrcaReplay run 血缘 | 不同假 Provider 映射到同一 canonical chunk 后生成相同消息；取消时只提交安全 block，半截 tool call 不进入 transcript；在工具执行前、执行成功后、结果持久化前三个边界注入崩溃，重启后分别判为未执行、结果未知、已完成；结果未知的有副作用工具不会自动重试；旧版事件 fixture 可迁移，trace／录制数据只通过稳定 ID 或载荷引用关联 |
| 3. 观测与基础评测 | OpenInference、Inspect；先使用假工具、良性任务或一次性容器 | 20–30 个固定任务可重复运行并保存 baseline；并发运行的 span 以 `run_id`、`tool_call_id` 正确归属，取消和异常均结束 span；关闭或故障 exporter 后四条阶段 1 路径结果不变 |
| 4. 执行隔离 | srt、Gondolin | 同一阶段 3 任务集切换到一个隔离后端后，确定性结果无非预期变化；测试证明超时和取消能终止子进程、测试目录外写入被拒绝、默认网络策略生效、运行结束后资源被清理 |
| 5. 工程闭环 | Opik、Harbor；服务化时看 OpenSandbox | 至少一个真实失败样本加入回归集并在 CI 中稳定复现；独立 verifier 能区分环境失败、Agent 失败和验证器失败；创建失败、客户端掉线或任务过期后资源最终回收 |
| 6. 专项能力 | 有明确需求时二选一：OrcaReplay 或 DSH | 回放方案能报告无法匹配与 divergence，且分叉保留 parent run；或插件卸载测试证明工具、监听器、后台任务三者全部释放。无需求时明确跳过，不阻塞阶段 7 |
| 7. 长期记忆 | memU、LangMem；工程后端择一 | 在阶段 3 固定任务的记忆子集上，对比无记忆与记忆版本；实验前写明成功率、过时引用、费用和延迟阈值，结果至少满足预先定义的收益条件；新增、纠正、删除、过期、用户／项目隔离测试全部通过 |

第一版范围：Python 3.12+ CLI、单 Agent、本地状态、OpenAI-compatible Chat Completions、一个隔离后端。核心保留 ModelAdapter、最小 canonical stream、Core Assembler、ToolExecutor、AgentLoop、EventStore、ContextBuilder、取消与预算控制；memory、exporter、评测 adapter 按需接入。外部模型协议只是首个 adapter，不是核心消息模型。

流式边界采用折中方案：Provider Adapter 只把私有协议翻译为 canonical chunk；Core Assembler 统一构造 `AssistantMessage` 并决定安全取消边界；EventStore 记录 attempt settlement，不持久化 UI update。只有影响 Agent 行为、恢复或评测的字段进入 canonical 协议；Provider 私有的 response id、签名等通过带归属与版本的 opaque replay state 保存，Core 不解释其内容。第一版不为尚未出现的图片、音频、citation 等能力扩展公共协议。

事件日志负责恢复，trace 负责诊断，长期记忆负责跨任务知识。每读一个模块，留下一个实现、测试或实验结论。

### 阶段停止与记录规则

- 每进入一个阶段，先把验收项写成失败的自动化测试或可重复实验，再按需阅读和实现。
- 阅读一个模块期间保持目标仓库版本不变；把影响实现的结论直接记入 `progress.md` 或对应测试，不单独维护版本清单。
- 阶段验收通过即停止该阶段的扩展阅读；可选项目没有明确问题时不读、不接入。
- 外部服务是否合并 PR、是否在线不作为阶段验收条件；只验收本地可复现的证据和产物。
- 每天结束时更新 `progress.md`：记录实际完成、验证证据，以及所有延期内容。延期项必须包含延期原因、计划完成日期或阶段、届时的验收方式；不得只写“以后再做”。次日开始和阶段结束前先检查到期延期项。

## 6. 开源贡献

贡献是从阶段 1 开始的并行支线，不受上面的学习名单限制，也不阻塞内核阶段验收。开始前复核候选 issue 的最新状态和贡献规则；阶段 1 优先尝试一个与自研内核无依赖、范围小且能补回归测试的问题。之后只在问题与当前阶段能力相符时继续，避免为了贡献扩大核心范围。以下是 2026-09-26 查询到的待复现线索；动手前检查最新讨论与关联 PR。

筛选 issue 时必须依次核对：当前是否仍能复现、是否有人在评论中认领、是否已有开放或近期关闭的关联 PR、维护者是否要求先讨论。开源 issue 可以替代同类的大型工程练习，但不能替代本阶段用于证明理解的微型实现和验收测试。

| 候选 | 适合训练的能力 |
|---|---|
| [mini-swe-agent #970](https://github.com/SWE-agent/mini-swe-agent/issues/970)：`-h` 与文档不一致 | 小范围 CLI 契约与回归测试 |
| [Inspect #5556](https://github.com/UKGovernmentBEIS/inspect_ai/issues/5556)：Windows YAML 编码 | 跨平台读取与可靠复现 |
| [MCPEval #18](https://github.com/SalesforceAIResearch/MCPEval/issues/18)：模型 base URL 配置 | 参数传播、配置优先级与 mock |
| [OpenLLMetry #4502](https://github.com/traceloop/openllmetry/issues/4502)：调用时长计量 | 每调用状态、并发与流式 metrics |
| [OpenLLMetry #4505](https://github.com/traceloop/openllmetry/issues/4505)：装饰器保护范围 | 同步／异步包装与故障隔离 |
| [OpenInference #3774](https://github.com/Arize-ai/openinference/issues/3774)：包装丢失控制方法 | 异步迭代器、取消与接口兼容 |
| [Gondolin #150](https://github.com/earendil-works/gondolin/issues/150)：挂载导致命令行截断 | 宿主／客体协议与启动边界 |

贡献前阅读各项目规则：

- [pi](https://github.com/earendil-works/pi/blob/main/CONTRIBUTING.md)：新贡献者需经过审核，PR 前获维护者批准。
- [DSH](https://github.com/deepseek-ai/deepseek-harness/blob/master/CONTRIBUTING.md)：当前不接受外部 PR，可通过 Discussions 或独立插件参与。
- [Harbor](https://github.com/harbor-framework/harbor/blob/main/CONTRIBUTING.md)：集成需要实际需求，核心接口先讨论。
- [OrcaReplay](https://github.com/Continuum-AI-Corp/OrcaReplay/blob/main/CONTRIBUTING.md)：可从适配器、脱敏规则、分析器或文档一致性切入。

本地交付标准：可复现问题 → 原因分析 → 小范围修复 → 相关测试。已有 issue 补充证据，避免重复创建。提交、维护者反馈和合并属于外部结果，记录但不作为学习阶段是否完成的门槛。
