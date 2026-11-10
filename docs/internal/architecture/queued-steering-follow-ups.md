---
title: "排队的 steering 与 follow-up"
---

这一片在 agent 运行活动时增加 Pi 式的消息排队。

## 加了什么

`baldric_agent.AgentHarness` 现在拥有两条 prompt 队列：

- steering 消息，在当前 assistant 轮与工具批次之后注入
- follow-up 消息，只在运行本会停止时注入

harness 暴露 `steer()`、`follow_up()`、`clear_queues()`、
`queued_messages`、`pending_message_count` 与 `is_running`。直接重叠的
`prompt()` 与 `continue_()` 调用被拒绝，调用者无法从两个活动运行改动同一份 transcript。

`run_agent_loop()` 接受 provider 中立的队列排水回调。队列排水时，循环把排队的用户消息追加到与普通 prompt 相同的消息列表，并在下一次 provider 调用之前发出普通的用户 `MessageStartEvent` 与
`MessageEndEvent`。

`QueueUpdateEvent` 为 frontend 报告待处理的 steering 与 follow-up 文本。
Textual TUI 用它做状态行的队列计数。

## coding session 边界

`CodingSession.prompt()` 对普通非运行 prompt 保持不变。harness 运行中时，调用者必须传：

```python
session.prompt(text, streaming_behavior="steer")
session.prompt(text, streaming_behavior="follow_up")
```

之一。session 在排队前展开 `/skill:<name>` prompt 文本。排队时不
持久化消息。持久化仍发生在活动运行结束、harness 已把排队的用户消息注入 transcript 之后。

## TUI 行为

内置 Textual frontend 映射：

- 运行中的 `Enter` → steering 排队
- 运行中的 `Alt-Enter` → follow-up 排队
- 运行中空 prompt 上的 `Up` → 编辑最近排队的 follow-up

运行继续时待处理队列显示在 prompt 上方。多个 follow-up 排队时，编辑把最近排队的 follow-up 拉回 prompt 并从队列移除。排队消息一旦注入，就作为普通用户消息出现在 transcript，待处理队列显示随之更新。

## 边界

队列所有权在 `baldric_agent`，prompt 展开与持久化留在
`baldric_coding`，Textual 只决定键位与呈现。provider 适配器不知道排队消息；它们在下一次 provider 调用收到更新后的 transcript。

## 测试

行为覆盖于：

```text
tests/test_agent_loop.py
tests/test_agent_harness.py
tests/test_coding_session.py
tests/test_tui_adapter.py
tests/test_tui_app.py
```
