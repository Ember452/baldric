---
title: 构建你自己的 frontend
description: 进阶——通过消费 Baldric 的事件流，用你自己的 UI 驱动它的 coding session。
---

> [!CAUTION] 进阶
> 本页面向在 Baldric 内核之上构建*新 frontend*的人。如果你只是想使用
> Baldric，见[交互式会话](/how-to/tui/)。这里的 API 是 Python 的，并假设你已读过[架构总览](/explanation/architecture/)。

Baldric 的 Textual 应用是 frontend 之一，不是架构本身。自定义 UI 接入与内置 TUI 相同的原语：

```text
CodingSession   — 拥有编码 agent 环境
AgentEvent      — 描述 assistant 文本、tool 调用、结果、错误
Frontend 状态    — 属于你的 UI
```

可复用的 `baldric.agent` 包保持对终端框架、组件、键位、配置路径与 slash 命令 UX 的独立。针对 `baldric.runtime.session.session.CodingSession` 构建，而不是 Textual 组件。

`CodingSession` 提供环境（provider/model、tools、持久化、skill、prompt template、项目 context、slash 命令处理、compaction）。你的 frontend 提供界面（prompt 输入、transcript 渲染、命令入口、取消、picker）。

## 最小事件循环

```python
async for event in session.prompt(user_text):
    render_event(event)
```

这个流产出 provider 中立的 `CodingSessionEvent`：来自 `baldric.agent.events` 的可移植 `AgentEvent`，加上来自 `baldric.runtime.events` 的 session 级值（见 [agent loop](/explanation/agent-loop/)）。从这些事件渲染，绝不从 provider 特定的分块渲染。用 `agent_start` 进入运行状态，用 `agent_settled`——而不只是 `agent_end`——离开它，因为自动 compaction、重试或排队续跑可能跟在 `agent_end` 之后。provider 失败以 `stop_reason` 为 `"error"` 的 assistant 消息到达，随后是正常的轮次/运行生命周期。

## steering 与 follow-up

如果用户在运行中提交，排队而不是启动第二个运行：

```python
async for event in session.prompt(user_text, streaming_behavior="steer"):
    adapter.apply(event); redraw(state)
```

`streaming_behavior="follow_up"` 用于等待当前运行本会结束之后才执行的 prompt。不带 `streaming_behavior` 的重叠 `session.prompt(...)` 调用会被拒绝，两个运行不能同时改动一份 transcript。`QueueUpdateEvent` 携带排队文本供徽标/状态使用。

## slash 命令

slash 命令属于 `baldric.runtime`。在把输入当作 prompt 之前：

```python
result = session.handle_command(text)
```

若 `result.handled`，执行请求的效果（`exit_requested`、`clear_requested`、`new_session_requested`、`compact_summary`、`message`），并把参考/状态输出显示在*持久对话之外*。若 `result.compact_summary is not None`，调用 `await session.compact(result.compact_summary)`（空字符串表示"直接使用内置 prompt"）。

`/skill:<name>` 有意**不是**命令——把它传给 `session.prompt(...)`，它会在运行前展开。

## 恢复与切换 session

从 `session.messages` 初始化可见 transcript（内置的 `TuiState.load_messages()` 是参考实现）。`ToolResultMessage` 保留结构化元数据（例如 edit patch），所以不读 JSONL 也能渲染已恢复的工具结果。

切换 session 用 `baldric.runtime.session.manager.SessionManager`——`list_sessions(session.cwd)`，然后 `await session.resume(session_id)`（或用 `storage=jsonl_session_storage(record.path)` 载入一个全新 `CodingSession`），再从 `session.messages` 重建 transcript。

## 取消、picker、键位

- 用 `session.cancel()` 取消——持续消费事件直到流结束。
- 直接从 session 读取 picker 数据：`command_registry.list_commands()`、`skills`、`prompt_templates`、`available_model_choices`、`available_models`、`available_providers`、`thinking_level`、`available_thinking_levels`、`session_manager`。来自其他 provider 的模型变更，先调 `set_provider(...)` 再 `set_model(...)`。
- 键位与主题是 **frontend 政策**。内置应用通过 `baldric.runtime.frontends.tui.load_tui_settings()` 读 `~/.baldric/tui.json`，你的 UI 可以无视它。

## 不要依赖什么

避免耦合私有的 `CodingSession` 属性、provider 特定的响应分块、Textual 内部结构，或原始 JSONL 结构（用 `SessionManager` / `CodingSession`）。只依赖事件、消息、tool、harness 与 session 这些原语。

> [!NOTE]
> 这些系统的完整逐阶段构建日志在仓库的 `docs/internal/` 里（见[贡献](/contributing/)）。
