---
title: "Phase 4：AgentHarness"
---

Phase 4 加了 `AgentHarness`——构建在纯 agent loop 之上的可复用有状态大脑。

上一阶段引入了 `run_agent_loop()`，它协调 provider、工具、消息与事件。该循环刻意几乎无状态：调用者传入 transcript 列表，循环追加 assistant 与工具结果消息。

`AgentHarness` 替调用者拥有那份 transcript。

## 加了什么

Phase 4 加了：

```text
src/baldric_agent/harness.py
```

包含：

- `AgentHarnessConfig`
- `AgentHarness`
- `SimpleCancellationToken`
- `EventListener`

## harness 为什么存在

Baldric 的架构分三层：

```text
AgentHarness = reusable brain
AgentSession = coding-agent environment
TUI = one possible frontend
```

harness 是可复用的有状态层。它仍不是完整的编码 agent 应用。

这意味着它可以拥有对话状态并运行循环，但不该知道：

- session 文件存哪里
- slash 命令如何工作
- 项目指令如何发现
- Rich 或 Textual 如何渲染事件
- 默认注册哪些内置编码工具

那些职责属于后续的 `baldric_coding` 阶段。

## harness 配置

`AgentHarnessConfig` 存储运行循环所需的稳定输入：

- provider
- 模型名
- system prompt
- 工具
- 可选最大轮数

概念上：

```python
config = AgentHarnessConfig(
    provider=provider,
    model="gpt-4.1-mini",
    system="You are Baldric.",
    tools=[...],
)
```

harness 接收这份配置，在每次 prompt 或继续运行时使用。

## prompt 流程

调用 `prompt()` 追加一条用户消息并启动循环。

```python
async for event in harness.prompt("Read README.md"):
    ...
```

transcript 如此变化：

```text
before prompt:
  []

after prompt appends user message:
  UserMessage("Read README.md")

after loop runs:
  UserMessage("Read README.md")
  AssistantMessage(...)
  ToolResultMessage(...)   # if tools were used
  AssistantMessage(...)
```

harness 不渲染那些事件，只是 yield 它们。

## continue 流程

调用 `continue_()` 运行循环而不追加新的用户消息。

这对未来的特性有用，例如：

- 还原 session 后继续
- 被打断的运行之后继续
- 让 coding-session 包装决定下一轮模型调用何时发生

```python
async for event in harness.continue_():
    ...
```

## transcript 快照

`messages` 属性返回不可变的元组快照。

这保护 harness transcript 不被外部意外改动：

```python
snapshot = harness.messages
```

未来的 session 层可以用该快照做持久化。受控还原时，`append_message()` 可以追加既有消息。

## 事件监听器

harness 支持事件订阅：

```python
unsubscribe = harness.subscribe(listener)
```

监听器收到与 `prompt()`、`continue_()` yield 的相同的 `AgentEvent`。

这让未来代码可以观察运行而不必成为主事件消费者。例如：

- 日志
- 指标
- session 持久化 hook
- UI 桥

主 API 仍是对事件的异步迭代。

## 取消

Phase 4 加了最小取消 token。

```python
harness.cancel()
```

请求取消时，当前循环可以停止并发出可恢复的取消错误。

刻意简单。后续 UI 层可以把它接到键位、按钮或命令 handler。

## 与循环的关系

harness 委托给 `run_agent_loop()`：

```text
AgentHarness.prompt()
        ↓
append UserMessage
        ↓
run_agent_loop(...)
        ↓
yield AgentEvent objects
        ↓
transcript grows
```

循环仍拥有逐轮机制。harness 拥有持久的内存对话状态。

## Phase 4 如何支撑后续阶段

### Phase 5：内置编码工具

harness 已接受 `AgentTool` 实例。编码工具出现后，编码应用可以把它们传入 harness 配置。

### Phase 6：print-mode CLI

CLI 可以创建 `AgentHarness`、调用 `prompt()` 并打印流式事件。

### Phase 7：session

session 持久化可以把消息还原进 harness 并在事件后保存快照。

### Phase 8：coding session 包装

coding session 包装可以在 harness 周围组合更高层行为：slash 命令、直接 bash 命令、prompt 展开、资源与持久化。

## 设计规则

`AgentHarness` 可以拥有 agent 状态，但必须保持 frontend 无关、编码应用无关。

行为依赖终端渲染、项目文件、用户配置目录或 slash 命令时，属于 `baldric_agent` 之外。
