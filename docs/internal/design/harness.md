---
title: "Agent Harness"
---

`AgentHarness` 是 Baldric 可复用的有状态 agent 大脑。

它位于：

```text
src/baldric_agent/harness.py
```

harness 拥有一份 transcript，把执行委托给纯 agent loop。

## 基本形状

```python
harness = AgentHarness(
    AgentHarnessConfig(
        provider=provider,
        model="...",
        system="...",
        tools=[...],
    )
)

async for event in harness.prompt("Hello"):
    ...
```

## 职责

harness：

- 存储 transcript 消息
- 为新 prompt 追加 `UserMessage`
- 调用 `run_agent_loop()`
- 流式发出 `AgentEvent`
- 暴露 `continue_()` 以不带新用户 prompt 继续运行
- 拒绝重叠的 `prompt()` / `continue_()` 运行
- 为活动运行排队 steering 与 follow-up 消息
- 支持事件监听器
- 支持基本取消

harness 对 CLI 参数、Textual、Rich 渲染、slash 命令与 session 文件一无所知。

## 队列

运行进行中使用队列 API：

```python
harness.steer("Adjust the current plan.")
harness.follow_up("When that is done, summarize the result.")
```

steering 消息在当前 assistant 轮与工具批次之后、下一次 provider 调用之前注入。follow-up 消息只在运行本会停止时注入。`AgentHarnessConfig.queue_mode` 默认
`"one_at_a_time"`；设为 `"all"` 可把每条队列整批排空。

队列变化与消息排空时，harness 发出 `QueueUpdateEvent`。排队的消息只有在注入 loop 时才成为持久的 transcript 消息。

详细的架构走读见 [Phase 4: AgentHarness](./architecture/phase-4-agent-harness.md)。
