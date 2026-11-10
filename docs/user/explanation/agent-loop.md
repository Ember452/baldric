---
title: agent loop 与事件
description: Baldric 中心的小引擎，以及每个 frontend 都在渲染的事件流。
---

**agent loop** 是那个小而可复用的引擎：它把消息、工具和 provider 流变成一串**事件**形式的进展。正是它让一个东西成为 *agent* 而不是聊天框。

## 循环做什么

每一轮，循环会：

1. 取当前的 system prompt、transcript、tools 和模型选择；
2. 请 provider 流式返回一个回复；
3. 在文本与 tool 调用到达时发出事件；
4. 收集 assistant 消息；
5. 执行所有被请求的工具；
6. 把工具结果追加进 transcript；
7. 重复，直到 assistant 不再发起 tool 调用。

那个"调用工具、把结果喂回去、继续"的循环，就是让模型能读一个文件、看到内容、然后决定怎么编辑的原因。

## 循环*不*做什么

循环对 CLI 参数、Textual 组件、session 文件位置、资源发现一无所知。它们属于 `baldric.runtime`。把它们排除在外，正是循环能在每个 frontend 复用的原因。

## 事件优先的设计

每个有意义的步骤都可以作为事件被观察，所以 print mode、Rich 渲染和 Textual TUI 共享同一个内核。frontend 从这些 provider 中立的事件渲染——绝不从原始 provider 分块渲染。可移植的 `baldric.agent.events.AgentEvent` 流包含：

- `AgentStartEvent` / `AgentEndEvent` — 一次运行开始 / 结束
- `TurnStartEvent` / `TurnEndEvent` — 一次 assistant 回复及其工具结果
- `MessageStartEvent` / `MessageUpdateEvent` / `MessageEndEvent` — 一条消息的
  Pi 兼容生命周期
- `ToolExecutionStartEvent` / `ToolExecutionUpdateEvent` / `ToolExecutionEndEvent`
  — 一个工具在运行

流式细节嵌套在 `MessageUpdateEvent.assistant_message_event` 之下。这些 provider 中立的嵌套事件覆盖文本、thinking 与 tool 调用的 start/delta/end 更新。provider 的完成或失败由通过 `MessageEndEvent` 送达的最终 assistant 消息表达。

`baldric.runtime.events.CodingSessionEvent` 为 frontend 与 SDK 用户扩展了这条可移植流：`agent_settled`、队列更新、compaction、session entry/session 信息变更、thinking 级别变更与自动重试事件。Extension 观察相同的事件名，但 session 到 extension 的适配器会给 `turn_start` 附加零基的 `turn_index` 与毫秒 `timestamp`，给 `turn_end` 附上匹配的索引。完整的载荷表见 [Extensions](/how-to/extensions/#事件)。

最终态的 `AssistantMessage` 是权威：它把文本、thinking 与 tool 调用按序持久化为内容块。嵌套的更新事件提供响应式渲染，而已保存 session 与 provider 历史回放使用定稿的结构化消息。它还携带可选的单调响应计时：等待 provider 事件直到完成、以及直到第一个文本/thinking/工具调用输出的累计时间。只计量 provider 事件的等待，排除了流拉取之间的 frontend 渲染与持久化工作。已保存的用量与计时保持配对，用于有效输出速度与 TTFT 统计。它的 `provider` 字段记录 Baldric 配置的 provider。当网关报告更具体的后端时，`response_provider` 记录实际服务该请求的后端。例如 Hugging Face 的响应在那里暴露被选中的 Inference Provider，而 `provider` 保持 `huggingface`。

因为契约是*事件*，frontend 的职责被缩减为：发送 prompt、消费流、画你所见。

→ 见[构建你自己的 frontend](/explanation/custom-frontend/) 了解具体 API，[架构总览](/explanation/architecture/) 了解循环所在的位置。
