# 契约债务：没有生产者或消费者的字段

**状态：** 开放台账 —— 审计跟进后更新于 2026-11-07

P0 契约工作钉住了形状；本笔记记录契约存在而机制缺席之处。每行要么已接线、要么已删除、要么有具名所有者与退出条件。

| 字段 / 类型 | 评审后状态 |
| --- | --- |
| `AgentTool.execution_mode` | **以拒绝方式接线。** Pi 的循环经其 `toolExecution` 选项并发跑 `parallel` 批次；本 harness 逐个运行工具，因此 `AgentHarness` 现在拒绝声明 `parallel` 的工具，而不是静默串行。实现并行执行仍是独立特性。 |
| `AgentToolResult.added_tool_names` | 端到端传递（`tools.py` → `ToolResultMessage` → JSONL）。Pi 携带同一字段标记迟到工具何时可用；这里的消费者随动态工具装载落地。作为 wire 对齐保留。 |
| `ToolCallDeltaEvent` | **生产者已落地**（#52）：流式参数到达时 `openai_compatible`、`openai_codex`、`anthropic` 与 `mistral` 都发出它，`tests/ai/test_stream_tool_deltas.py` 覆盖。早先的"无生产者"行已过期。 |
| `ProviderRetryEvent`（AI 内部） | 已呈现：`stream.py` 转为 `AssistantRetryEvent`，loop 转为 `RetryAttemptEvent`，coding 层转为 `auto_retry_start` / `auto_retry_end`（#47）。审计之后，事件的 `data`（HTTP 状态与响应体）也落到 assistant 消息诊断，截断且永不对模型可见。 |
| `Usage.cost` | **仍是债务。** `sum_usage` 与 `session/stats.py` 读它，没有东西生产它：每个适配器都报零。移除它改变 wire 形状；接线它需要在 provider 层做定价，而定价不属于那里。退出条件：第一个需要成本在导出中存活的消费者。 |
| `EntryAppendedEvent` | **已删除**，连同 extension 事件白名单里的 `entry_appended`：没有东西发出或消费它，extension 订阅的是一个永不触发的事件。守卫测试现在会在白名单列出事件模块未声明的任何事件时失败。 |
| `BashExecutionMessage` | **已接线。** `run_terminal_command(add_to_context=True)` 现在持久化一条，`provider_context` 把它渲染为模型之前看到的同样纯文本，`exclude_from_context` 让一次执行留在 transcript 但不进请求，transcript 加载器在 resume 时渲染它。 |
| `sum_usage` | 已接线（`session/branch_summary.py`、`session/session.py`）。不是债务。 |

## 规则

从 Pi 移植的每个字段或类型落地时必须带生产者、消费者与测试，否则不落地。移除死字段永远属于触碰其文件的变更范围。

## 退出标准

- 每行要么已接线（带一个没有它会失败的测试）要么已删除。
- `tests/agent/test_wire_contract.py` 与
  `tests/agent/test_session_entry_contract.py` 与改变形状的变更在同一提交中变更，让移除成为被评审的 diff 而非静默变更。

跟踪：#51。
