# Pi 风格事件迁移审计

**Worktree：** `~/.agents/worktrees/baldric/pi-event-extension-parity`
**分支：** `feat/pi-event-extension-parity`
**日期：** 2026-07-16

## 执行摘要

`baldric_ai` 与 `baldric_agent` 的事件模型已大幅切换到 Pi 风格。但迁移在四个主要方面不完整且不一致：

1. **`baldric_ai`** 内部仍使用过渡性的 `_provider_events.py`；公开的 Pi 事件只经 `canonicalize_provider_stream()` 产出。
2. **`baldric_agent`** 不再发出多个旧事件（`retry`、`queue_update`、`message_delta`、`thinking_delta`、`error`），但替代语义只接了一部分。
3. **`baldric_coding`** 定义了新的 session 级事件（`agent_settled`、`auto_retry_start/end`、`compaction_start/end` 等），但大多数从未真正发出。
4. **extension API** 仍在宣传旧的 Baldric-v1 事件名与 handler 签名，尽管内核已不再产生那些事件。

此外，PR #332 / issue #317 处理过的 `baldric_agent` 与 `baldric_ai` 循环依赖又出现了。

---

## 1. `baldric_ai` 层

### 变了什么

- 新的规范公开事件定义在 `src/baldric_ai/events.py`：
  - `AssistantStartEvent`、`AssistantDoneEvent`、`AssistantErrorEvent`
  - `TextStartEvent`、`TextDeltaEvent`、`TextEndEvent`
  - `ThinkingStartEvent`、`ThinkingDeltaEvent`、`ThinkingEndEvent`
  - `ToolCallStartEvent`、`ToolCallDeltaEvent`、`ToolCallEndEvent`
- provider 协议现在返回 `AsyncIterator[AssistantMessageEvent]`（`src/baldric_ai/provider.py`）。

### 不一致之处

- **过渡性内部协议仍存在。** 每个 provider 实现（`anthropic.py`、`google.py`、`mistral.py`、`openai_compatible.py`、`openai_codex.py`）仍发出 `src/baldric_ai/_provider_events.py` 的旧 `ProviderResponseStartEvent`、`ProviderTextDeltaEvent`、`ProviderToolCallEvent`、`ProviderResponseEndEvent` 等，再由 `src/baldric_ai/stream.py` 的 `canonicalize_provider_stream()` 适配。
- **没有真正的流式 tool-call delta。** 解析器只发出一条完成的 `ProviderToolCallEvent`。`canonicalize_provider_stream()` 把它映射为紧挨着的 `ToolCallStartEvent` + `ToolCallEndEvent`，中间没有 `ToolCallDeltaEvent`。Pi 期望 tool-call 参数经 `toolcall_delta` 流式传输。
- **tool-call 内容没有插入到正确的内容索引。** `stream.py:112-120` 在追加块之前 yield start 事件，所以 `ToolCallStartEvent` 的 `partial` 快照还不含该 tool call。
- **重试事件被吞。** `canonicalize_provider_stream()` 丢弃 `ProviderRetryEvent`（`stream.py:71-73`）。Pi 在 coding-session 层暴露重试，但 Baldric 目前在 `baldric_ai` 与 `baldric_coding` 之间完全丢失它。
- **`AssistantErrorEvent` 与 `AssistantDoneEvent` 含义含混。** `AssistantDoneEvent` 带 `reason: StopReason`，`AssistantErrorEvent` 也带 `reason`。消费者必须同时检查事件类型与消息 `stop_reason` 才能判定失败。
- **provider 最终消息重建脆弱。** `stream.py:145-158` 用流式 thinking、最终文本与最终工具重建 `final.content`。相对 provider 实际的交错顺序，这可能重排内容。

---

## 2. `baldric_agent` 层

### 变了什么

- `src/baldric_agent/events.py` 的新事件模型：
  - `AgentStartEvent`、`AgentEndEvent`
  - `TurnStartEvent`、`TurnEndEvent`
  - `MessageStartEvent`、`MessageUpdateEvent`、`MessageEndEvent`
  - `ToolExecutionStartEvent`、`ToolExecutionUpdateEvent`、`ToolExecutionEndEvent`
- `MessageDeltaEvent` 与 `ThinkingDeltaEvent` 没了。文本/thinking delta 现在以 `MessageUpdateEvent` 包裹 `baldric_ai` 的 `TextDeltaEvent`/`ThinkingDeltaEvent` 到达。
- `ErrorEvent` 没了。错误是 `stop_reason == "error"` 的终结 `AssistantMessage`。
- `RetryEvent` 与 `QueueUpdateEvent` 从 `AgentEvent` 移除。

### 不一致之处

- **`AgentEndEvent` 载荷与 Pi 不符。** Pi 的 `agent_end` 携带生成的 `messages`。Baldric 的 `AgentEndEvent` 目前没有字段（`loop.py:19`、`events.py:19`）。messages 计算了但没挂到事件上（`loop.py:168` yield 无参 `AgentEndEvent()`）。
- **`TurnEndEvent` 载荷不完整。** 它带 `message` 与 `tool_results`，但 Pi 的 turn end 还带最终状态如权威 assistant 消息与工具结果。`events.py:28` 展示的定义里没有 `tool_results` 字段，而 loop 构造 `TurnEndEvent(message=assistant, tool_results=tool_results)`（`loop.py:158`）。只因模型宽容才工作，schema 并不显式。
- **工具执行更新语义变了而消费者没跟上。** `ToolExecutionUpdateEvent` 现在携带 `partial_result: AgentToolResult`（`events.py:60`），旧字段是 `str` 消息。TUI 适配器用 `.text`（`adapter.py:82`），碰巧能用，但这是隐式契约。
- **工具结果消息不发 `message_start`/`message_end`。** `loop.py:255-260` 在 `ToolExecutionEndEvent` 之后追加 `ToolResultMessage`，但不为它 yield `MessageStartEvent`/`MessageEndEvent`。Pi 为工具结果发出消息生命周期事件。
- **取消不产生显式事件。** loop 在工具执行内检查 `signal.is_cancelled()` 但不发专门的取消事件；它依赖一个错误结果。
- **循环依赖重现。** `baldric_agent` 导入 `baldric_ai`：
  - `src/baldric_agent/loop.py:29-35` 从 `baldric_ai.events` 与 `baldric_ai.provider` 导入。
  - `src/baldric_agent/events.py:12` 从 `baldric_ai.events` 导入 `AssistantMessageEvent`。
  - `src/baldric_agent/harness.py:22` 从 `baldric_ai.provider` 导入 `ModelProvider`。

  同时 `baldric_ai` 几乎每个模块都导入 `baldric_agent.messages`、`baldric_agent.tools`、`baldric_agent.types`。这与 PR #332 通过把 provider 协议移进 `baldric_agent` 所反转的循环如出一辙。

---

## 3. `baldric_coding` 层

### 变了什么

- 新的 `src/baldric_coding/events.py` 定义 session 级事件：
  - `AgentSettledEvent`
  - `QueueUpdateEvent`
  - `CompactionStartEvent`、`CompactionEndEvent`
  - `EntryAppendedEvent`
  - `SessionInfoChangedEvent`
  - `ThinkingLevelChangedEvent`
  - `AutoRetryStartEvent`、`AutoRetryEndEvent`
- `CodingSessionEvent = AgentEvent | SessionOwnEvent`。

### 不一致之处

- **`AgentSettledEvent` 有定义但从不发出。** 在 `src/baldric_coding/session.py` 中找不到 `AgentSettledEvent(...)` 的 yield。TUI 适配器处理它（`adapter.py:34-37`）但因它永不到达而回退 `AgentEndEvent`。
- **`AutoRetryStartEvent` / `AutoRetryEndEvent` 从不发出。** `session.py:1492-1518` 的溢出重试路径重跑 harness 但不发重试生命周期事件。
- **`CompactionStartEvent` / `CompactionEndEvent` 从不发出。** compaction 在 `_append_compaction`（`session.py:1903-1925`）与 `_try_overflow_compact` 中运行但不 yield 事件。
- **`EntryAppendedEvent` 从不发出。** session entry 追加时不发持久化事件。
- **`SessionInfoChangedEvent` 与 `ThinkingLevelChangedEvent` 从不发出。** 模型/thinking 变更静默更新持久状态。
- **`QueueUpdateEvent` 不从 `prompt()` / `continue_()` yield。** `session.py:778-783` 把 `queue_update_event()` 暴露为方法，`harness.steer()` / `harness.follow_up()` 返回 `QueuedMessages`，但流中不 yield `QueueUpdateEvent`。TUI 适配器导入并处理 `QueueUpdateEvent`，但 session 从不产生它。（运行中的 steering 当前提前返回原始 `QueuedMessages` 对象而非事件——`session.py:1444-1448`。）
- **`SessionAgentEndEvent` 与 `AgentEndEvent` 重复。** `events.py:14` 定义了带 `will_retry` 的 session 级 `agent_end` 事件，但 agent 层已发 `AgentEndEvent`。coding 流可能携带两种不同的 `agent_end` 形状。
- **`CodingSession.prompt()` 与 `continue_()` 类型标为 `AsyncIterator[AgentEvent]`**（`session.py:1412`、`1529`）而非 `AsyncIterator[CodingSessionEvent]`，尽管目标就是暴露 session 级事件。

---

## 4. Extension API

### 现状

`src/baldric_coding/extensions/api.py:22-39` 仍在宣传旧的 Baldric-v1 观察集：

```python
AGENT_EVENT_TYPES = {
    "agent_start", "agent_end", "turn_start", "turn_end",
    "retry",          # no longer emitted by baldric_agent
    "queue_update",   # no longer emitted by baldric_agent
    "message_start", "message_delta", "thinking_delta", "message_end",
    "tool_execution_start", "tool_execution_update", "tool_execution_end",
    "error",          # no longer emitted by baldric_agent
}
```

### 不一致之处

- **`retry`、`message_delta`、`thinking_delta`、`error` 在允许列表里但永不产生。** 订阅它们会静默地永不触发。
- **缺 `message_update`**，尽管它是 agent 层现在流式传输文本/thinking/tool delta 的唯一途径。
- **`AGENT_EVENT_TYPES` 缺 session 级事件**：`agent_settled`、`compaction_start`、`compaction_end`、`auto_retry_start`、`auto_retry_end`、`entry_appended`、`session_info_changed`、`thinking_level_changed`。
- **handler 签名仍是单参。** `ExtensionHandler = Callable[[object], object | Awaitable[object]]`（`api.py:404`）。计划的 Pi 风格 API 是 `handler(event, context)`，但 handler 以 `handler(event)` 调用（`runtime.py:812`、`819`）。
- **`ToolCallHookEvent` / `ToolResultHookEvent` 用新的 `AgentToolResult` 但隐式暴露旧形状字段。** `ToolResultHookResult` 仍返回 `content: str | None`、`ok: bool | None`、`details: dict | None`（`api.py:399-401`），假设旧结果信封。runtime 必须把它转换为新 `AgentToolResult` 形状。
- **`InputEvent` 仍是旧 `streaming_behavior` 字符串**而非类型化枚举，且 handler 调用无 context。
- **`ExtensionCommandHandler` 仅同步**（`api.py:407`），而 Pi 风格计划要求异步命令 handler。

---

## 5. 消息与工具模型不一致

### `UserMessage`

- 旧 Baldric 允许 `UserMessage` 携带自定义消息的 `custom_type` 与 `details`。
- 新 `UserMessage`（`messages.py:110-118`）只有 `content` 与 `timestamp`。自定义消息现在是独立的 `CustomMessage` 类。
- 若干代码路径仍假设 `UserMessage.custom_type` 存在。例如 `TuiState.load_messages()` 最近改为按类分发，但 `session.py:1459-1465` 在提供 `custom_type` 时构造 `CustomMessage`。这个拆分原则正确，但必须传播到各处。

### `AgentToolResult`

- 旧字段移除：`tool_call_id`、`name`、`ok`、`data`、`error`。
- 新字段：`content`（块列表）、`details`、`added_tool_names`、`terminate`。
- 校验器静默丢弃旧字段（`tools.py:40-44`），掩盖迁移问题而不是快速失败。
- `ToolResultRenderer` 协议不接受工具名（`tools.py:58-60`），但 TUI 与 extension runtime 现在需要名字查找渲染器。runtime 目前把 `tool_name` 作为单独参数传给 `render_tool_result()`（`runtime.py:406-410`），而 `AgentTool.render_result` 字段仍遵循双参协议。这是类型/模型不匹配。

### `AssistantMessage`

- `content` 现在是块列表。校验器为方便接受 `str` 与 `tool_calls`（`messages.py:165-189`），有帮助但也掩盖了仍把 `content` 当字符串的地方。
- `ToolResultMessage` 现在把 `tool_name` 与 `tool_call_id` 作为顶层字段，但旧 `name` 别名只在校验期接受。一些消费者仍引用 `.name`。

---

## 6. TUI 与 frontend 不一致

### `TuiEventAdapter`

- 处理 `AgentStartEvent`、`AgentEndEvent`、`agent_settled`、`QueueUpdateEvent`、`MessageStartEvent`、`MessageUpdateEvent`、`MessageEndEvent`、工具事件与 `AutoRetryStartEvent`。
- 它现在在 `AgentEndEvent` 上冲刷并清空 `state.running`（`adapter.py:30-33`），因为 `AgentSettledEvent` 从不发出。这是权宜，不是预期设计。

### `TuiState`

- `load_messages()` 最近改为按消息类分发（`state.py`），修复了 `UserMessage.custom_type` 崩溃。
- `record_tool_result()` 现在单独接收 `tool_name`，匹配新结果模型。

### 遗留问题

- 适配器不处理 `CompactionStartEvent`、`CompactionEndEvent`、`AutoRetryEndEvent`、`SessionInfoChangedEvent`、`ThinkingLevelChangedEvent`。
- `MessageStartEvent` 设 `state.assistant_buffer = event.message.text`（`adapter.py:42-43`）。空 assistant 消息没问题，但只有 tool call 的 assistant 消息会让缓冲为空，随后的工具调用在没有任何 assistant 文本收尾的情况下渲染。
- `MessageUpdateEvent` 处理只认 `TextDeltaEvent` 与 `ThinkingDeltaEvent`。不处理 `message_update` 内的 `ToolCallStartEvent`/`ToolCallDeltaEvent`/`ToolCallEndEvent`，TUI 靠 `MessageEndEvent` 发现 tool call。

---

## 7. 测试套件状态

- 11 个测试模块在收集期失败，因为导入了已移除的符号：
  - 来自 `baldric_agent` 的 `ErrorEvent`、`RetryEvent`、`QueueUpdateEvent`、`MessageDeltaEvent`、`ThinkingDeltaEvent`
  - 旧形态的 `ProviderEvent`、`ProviderErrorEvent`、`ProviderRetryEvent` 等
- 受影响文件包括 `tests/test_agent_harness.py`、`tests/test_agent_loop.py`、`tests/test_agent_types.py`、`tests/test_cli.py`、`tests/test_coding_session.py`、`tests/test_extensions.py`、`tests/test_rendering.py`、`tests/test_baldric_ai.py`、`tests/test_tui_adapter.py`、`tests/test_tui_app.py`、`tests/test_tui_components.py`。
- 只有 340 个测试成功收集；套件其余被这些导入错误阻塞。

---

## 8. 循环依赖回归

PR #332 之后的预期架构是：

```
baldric_agent defines provider protocol and events
baldric_ai implements them
baldric_coding consumes them
```

当前 worktree：

```
baldric_agent/loop.py       -> baldric_ai.events, baldric_ai.provider
baldric_agent/events.py     -> baldric_ai.events
baldric_agent/harness.py    -> baldric_ai.provider
baldric_ai/*                -> baldric_agent.messages, baldric_agent.tools, baldric_agent.types
```

这在 `baldric_agent` 与 `baldric_ai` 之间造成双向导入图。导入目前能成功是因为 `baldric_agent.types` 与 `baldric_agent.messages` 先于 `baldric_ai` 加载，但 PR #332 的分层测试会失败。

---

## 最关键不一致摘要

| 区域 | 不一致 | 严重度 |
|---|---|---|
| `baldric_ai` | provider 内部仍发旧 `_provider_events` | 中（过渡） |
| `baldric_ai` | 无真实 `toolcall_delta` 流式 | 中 |
| `baldric_agent` | `AgentEndEvent` 不带 `messages` | 高 |
| `baldric_agent` | `TurnEndEvent(tool_results=...)` 未反映在 schema | 高 |
| `baldric_agent` | 工具结果消息缺 `message_start`/`message_end` | 中 |
| `baldric_coding` | `AgentSettledEvent` 有定义从不发出 | 高 |
| `baldric_coding` | `AutoRetry*`、`Compaction*`、`EntryAppended*`、`SessionInfoChanged*`、`ThinkingLevelChanged*` 从不发出 | 高 |
| `baldric_coding` | `QueueUpdateEvent` 不从 session 流 yield | 高 |
| Extension | `AGENT_EVENT_TYPES` 列着已不存在的事件 | 高 |
| Extension | handler 签名仍是单参 | 高 |
| 架构 | `baldric_agent` ↔ `baldric_ai` 循环依赖重现 | 高 |
| 测试 | 11 个测试模块导入失败 | 高 |

纯文本核心路径端到端可用，但任何涉及 session 级生命周期、重试、compaction、tool-call 流式或 extension 的路径都只迁移了一半。


## 整改更新

后续实现处理了审计的多项发现：

- 把 provider 契约与规范 assistant 事件移进 `baldric_agent`，`baldric_ai` 保留保持身份的公开再导出。分层测试现在阻止 `baldric_agent -> baldric_ai` 导入。
- 增加了针对性的规范事件顺序与工具结果生命周期测试。
- 保留流式块顺序并修复 tool-call start 快照。
- 增加 coding-session 的 `agent_end`（`willRetry`）与 `agent_settled` 事件、队列更新、溢出 compaction/重试生命周期事件。
- 用规范事件名替换 extension 事件允许列表，handler 以全新的 `(event, context)` 参数派发，包括 session 自有事件。
- 迁移内置工具、session 专属消息的 provider 载荷转换、print frontend 与 hello-tool 示例到规范模型。
- 在 JSON 与 text 模式手动验证了真实文本与 tool-call 流。

切换在每个公开边界完成：

- 完整 Baldric 套件在规范模型与事件上通过；mypy 与 Ruff 干净。
- Extension handler 一致接收全新 `(event, context)` 参数，随发示例与已发布指南使用规范工具定义/结果。
- 持久化的 Baldric-v1 JSONL 消息在存储边界迁移，重写为规范 assistant 块、`toolResult` 消息与专属自定义消息。
- 运行时模型拒绝已移除的 Baldric-v1 字段而不是静默丢弃。
- print、JSON、TUI、导出器、分支摘要与 provider 测试消费同一协议。

provider 实现仍以 `_provider_events.py` 加 `stream.py` 作为**私有的解析器归一化实现**。这不是对外宣传的剖面：
`ModelProvider`、`baldric_ai.events` 与每个 provider 的 `stream_response()` 只暴露保持身份的规范 `baldric_agent` 事件。移除那个解析器 helper 是可选的内部简化，不是发布或兼容阻塞项。
