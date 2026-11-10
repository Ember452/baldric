---
title: "Agent Loop"
---

Baldric 的纯 agent loop 由 `baldric_agent.loop` 的 `run_agent_loop()` 实现。

它连接：

```text
transcript + tools + provider
```

并在向 transcript 追加新消息的同时发出 agent 事件。

## 最小形状

```python
async for event in run_agent_loop(
    provider=provider,
    model="...",
    system="...",
    messages=messages,
    tools=tools,
):
    ...
```

循环有意独立于 CLI、Rich、Textual 与 session 文件位置。

当前循环还接受来自 `AgentHarness` 的可选队列排水 hook。
这些 hook 让循环在一轮/一批工具之后注入 steering 消息，
在运行本会停止时注入 follow-up 消息，同时仍发出普通
用户消息事件并改动同一份 transcript 列表。

详细的架构走读见 [Phase 3: Pure Agent Loop](./architecture/phase-3-agent-loop.md)。
