---
title: "Phase 20.1：context 计量刷新"
---

Phase 20.1 收紧 Baldric 的 context 计量，并让 TUI 刷新跟随更新活动 agent transcript 的同一条事件流。

## 加了什么

`baldric_coding.context_window` 现在暴露 `ContextUsageEstimate`——一个结构化快照：

```text
total_tokens
system_tokens
message_tokens
tool_tokens
message_count
tool_count
```

`CodingSession.context_usage` 为活动 provider context 返回该快照。较旧的 `context_token_estimate` 属性保留为兼容捷径，供只需要总数的命令、组件与测试使用。

`/status` 仍打印：

```text
Estimated context tokens: <count>
```

还包括 system prompt、消息与工具定义的稳定 token 构成。

## prompt 消息事件

prompt 运行现在为用户 prompt 发出可移植消息事件：

```text
agent_start
turn_start
message_start user
message_end user
...
```

这镜像 Pi 的循环行为：prompt 先加入 context，事件流在 assistant 流式开始之前报告该消息。直接调用低层
`run_agent_loop()` 的调用者不变；它们仍传入已准备好的消息列表，只收到 assistant/工具循环事件。

## TUI 刷新边界

Textual 应用不再把已提交的用户 prompt 预加进可见 transcript。`TuiEventAdapter` 改为从流式事件渲染用户、assistant 与工具消息。`_refresh()` 在每个事件后运行，侧栏与紧凑 session 行因此在以下时点观察到 context 变化：

- 提交的用户消息
- assistant 消息完成
- 工具结果插入
- 手动或自动 compaction
- session resume/new-session 替换

这让可复用的 `baldric_agent` 包保持无 UI：它只发出可移植事件。Textual 专属渲染留在 `baldric_coding.tui`。

## 测试

本阶段覆盖于：

```text
tests/test_agent_harness.py
tests/test_context_window.py
tests/test_coding_session.py
tests/test_tui_adapter.py
tests/test_tui_app.py
```

测试验证 context 用量在正常轮、compaction 与被恢复 session 后重算，且 TUI 刷新在每个流式消息/工具边界看到变化的 context 估算。
