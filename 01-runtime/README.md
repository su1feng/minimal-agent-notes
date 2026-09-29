# Minimal Agent Runtime

## 目标

从最小的模型调用循环开始，逐层实现一个可替换、可取消、可恢复的 Agent 执行内核。

Runtime 负责推进一次 Agent 运行：接收消息、调用模型、执行工具、提交结果、维护状态，并在失败或重启后判断如何继续。

Runtime 的最终目标是实现 DeepSeek Harness 去掉 Cordis 与插件系统后的完整运行时能力，包括 Agent 生命周期、模型请求、工具执行、运行控制、会话事实、持久化恢复和运行时组装；实现方式采用普通模块与稳定接口，不复刻“一切皆插件”的架构。

最终系统的能力范围只排除 Cordis 与插件系统，不排除长期记忆、执行沙箱、链路观测和评测。它们不在 `01-runtime` 内部实现，而是由其他方向提供具体实现，再通过稳定接口接入 Runtime。

## 总体结构

```text
Agent Runtime
├── 1. Agent Loop
│   ├── Turn Lifecycle
│   ├── Step Lifecycle
│   └── Continue / Stop Decision
├── 2. Request and Context
│   ├── Request Assembly
│   ├── Context Projection
│   ├── Prepared Model Call
│   └── Immutable Model Input
├── 3. Model Execution
│   ├── Model Adapter
│   ├── Streaming
│   └── Assistant Attempt Settlement
├── 4. Tool Execution
│   ├── Tool Dispatch
│   ├── Pre-execute Validation and Policy
│   ├── Execute
│   ├── Post-execute Processing
│   └── Tool Call Settlement
├── 5. Execution Control
│   ├── Cancellation
│   ├── Limits and Timeouts
│   └── Retry and Failure Classification
├── 6. Runtime Facts
│   ├── Turn / Step / Attempt Events
│   ├── Durable Facts
│   ├── Ephemeral Events
│   ├── Commit Boundaries
│   └── Runtime State Projection
├── 7. Persistence and Recovery
│   ├── Append-only Event Store
│   ├── Resume and Interrupted-run Repair
│   └── Deterministic History Reconstruction
└── 8. Runtime Assembly
    ├── Dependency Wiring
    ├── Runtime Configuration
    └── Public Run Interface
```

Core Contracts 不是运行流程中的独立层级，而是贯穿各层的稳定边界，包括消息、Prepared Model Call、模型流、工具调用与结果、取消信号、运行事实、持久化存储和运行结果等契约。

Durable Facts 是已经结算、可以持久化与恢复的运行事实；Ephemeral Events 是流式增量、进度和其他仅供实时消费的瞬态事件。两者都不等同于链路观测：Observability 可以订阅它们，但不属于 Runtime 本身。

## 当前进度

- 当前层级：**Level 1 — Agent Loop**。
- 状态：进行中。
- 已完成：Core Contracts 的当前最小集合，Agent Loop 的模型调用、工具执行和结果回填，第一版 Run／Turn／Step 生命周期，以及带 Run／Turn／Step／Attempt 身份的模型请求结算。
- 当前主题：集中 Continue／Stop Decision，明确模型重试与新 Step 的边界，并补齐工具批次的取消结算语义。
- 下一步：将分散的终止判断收敛为显式决策，再区分取消时已 dispatch、尚未 dispatch 和结果未知的工具调用。

## CI

CI 会在 `01-runtime/` 或 Runtime 工作流发生变化时执行格式检查、lint、严格类型检查和测试，并覆盖 Python 3.12 与 3.13。

本地运行同一组质量门禁：

```bash
cd 01-runtime
uv sync --locked --all-groups
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest -q
```

当前阶段只通过 CI 保证学习代码持续可运行，不构建版本或发布制品。等最小 Runtime 达到可生产使用的完成标准后，再设计版本策略、构建产物与发布流程。
