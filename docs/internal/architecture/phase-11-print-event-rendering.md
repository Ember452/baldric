---
title: "Phase 11：print 与事件渲染模式"
---

Phase 11 为 Baldric 的非交互 CLI 模式加了一个小的渲染边界。

实现位于：

```text
src/baldric_coding/rendering/
```

## 加了什么

Baldric 现在有不依赖可移植 harness 层、消费 `baldric_agent` 事件的事件渲染器：

- `FinalTextRenderer` 只打印最终 assistant 回答。
- `JsonEventRenderer` 把每个 agent 事件写为 JSON Lines。
- `TranscriptRenderer` 保留 Baldric 之前的实时 transcript 行为。
- `PrintOutputMode` 选择 `text`、`json` 或 `transcript` 输出。

CLI 以此暴露：

```bash
baldric --output text "summarize this project"
baldric --output json "summarize this project"
baldric --output transcript "summarize this project"
```

`text` 是默认模式。

## 为什么存在

Pi 把终端输出模式放在可复用 agent 内核之外：

```text
agent/session emits events
print mode consumes events for final text or JSON output
interactive mode uses a separate TUI layer
```

Baldric 现在遵循同一架构边界：

```text
baldric_agent     portable event-producing harness
baldric_coding    CLI mode selection and event rendering
future TUI    another consumer of the same event stream
```

这使 `baldric_agent` 不沾 Typer、Rich、Textual、终端行为与 UI 政策。

## 输出模式

### text 模式

text 模式是 Pi 风格的 print mode。它消费完整事件流，运行结束后只打印最终 assistant 消息。

它忽略工具事件的显示，出现不可恢复的 `ErrorEvent` 时返回失败。

### JSON 模式

JSON 模式每行写一条序列化事件：

```json
{"type":"message_start","message_role":"assistant"}
{"type":"message_delta","delta":"Hello"}
```

脚本与未来集成因此获得稳定的事件流，不依赖人类导向的终端格式化。

### transcript 模式

transcript 模式保留 Baldric 更早的 print mode 行为：

- assistant delta 流式到 stdout
- 工具开始、进度更新与工具结果渲染到 stderr
- 成功与失败的工具结果内容渲染到 stderr
- 错误渲染到 stderr

transcript 渲染器用 Rich 做人类导向的 stderr 输出，同时保持默认
`text` 模式脚本友好。

这在 Baldric 还没有完整交互 TUI 时有用。

## CLI 集成

`run_print_mode()` 现在接受：

```python
output: PrintOutputMode = PrintOutputMode.text
```

它经

```python
create_event_renderer(output)
```

创建渲染器，把 `CodingSession.prompt()` 的每个事件发给渲染器。session
包装持久化一次性 transcript，让 print mode 与 TUI 共用同一 prompt、资源与工具环境。

## 测试

本阶段覆盖于：

```text
tests/test_rendering.py
tests/test_cli.py
```

测试验证：

- transcript 流式行为
- 最终文本行为
- JSON Lines 输出
- 不可恢复错误处理
- CLI 输出模式集成

## 非目标

本阶段不加：

- Textual UI
- 键盘输入
- session picker
- diff 查看器
- markdown 渲染器
- 主题系统

它们属于后续 frontend 阶段。

## 下一阶段

下一阶段可以在同一事件边界后构建 Textual TUI，或先在 `baldric_coding` 内加可选的 Rich 样式而不改 `baldric_agent`。
