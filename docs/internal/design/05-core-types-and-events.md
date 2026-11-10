---
title: "05 — 核心类型与事件"
---

Phase 1 定义后续 Baldric 阶段共享的 provider 中立对象。

## 这些类型为什么存在

provider 层、agent loop、harness、工具、session 与 UI 不应交换 provider 特定对象。
它们使用 Baldric 自己的 message、tool、result 与 event 模型。

## 消息

消息位于 `baldric_agent.messages`：

- `UserMessage` 记录用户输入。
- `AssistantMessage` 记录 assistant 文本与可选 tool 调用。
- `ToolResultMessage` 记录一次具体 tool call 的结果。
- `AgentMessage` 是所有 transcript 消息类型的联合。

这些就是最终会传给模型 provider 并持久化进 session 的对象。

## 工具

工具位于 `baldric_agent.tools`：

- `ToolCall` 是 assistant 执行某个具名工具的请求，带类 JSON 参数。
- `AgentTool` 描述一个可执行工具：名字、描述、输入 schema 与异步执行器。
- `AgentToolResult` 是运行工具后的结构化响应。

内核类型不实现编码工具。`read`、
`write`、`edit`、`bash` 等内置工具位于编码 agent 应用层的
`baldric_coding`。

## 事件

事件位于 `baldric_agent.events`。它们描述可移植 agent 层的进展：

- `agent_start`
- `agent_end`
- `turn_start`
- `turn_end`
- `queue_update`
- `retry`
- `message_start`
- `message_delta`
- `thinking_delta`
- `message_end`
- `tool_execution_start`
- `tool_execution_update`
- `tool_execution_end`
- `error`

print mode、Rich 渲染器、JSON 事件流与 Textual TUI 都
消费同一条事件流。

`queue_update` 报告待处理的 steering/follow-up prompt。`retry` 报告
provider 重试进度。`thinking_delta` 携带暴露该能力的 provider 的可选流式推理
文本；是否显示由 frontend 决定，它
不会记录为持久的 assistant 消息文本。

## 设计边界

这些模型刻意保持小而 provider 中立。provider 适配器在 agent loop 或 frontend 看到之前，把 Anthropic、OpenAI 兼容、OpenAI Codex 订阅或其他 API
载荷翻译成 Baldric 类型。
