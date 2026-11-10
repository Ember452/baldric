---
title: "Phase 1：核心类型与事件"
---

Phase 1 创建 Baldric 未来 agent loop 的共享词汇。

在 Baldric 能与模型对话、执行工具、保存 session 或渲染 UI 之前，每个层需要就流经系统的数据形状达成一致。这就是核心 message、tool、JSON 与 event 类型提供的东西。

## 加了什么

Phase 1 在 `baldric_agent` 加了四个模块：

```text
src/baldric_agent/types.py      JSON-like shared type aliases
src/baldric_agent/messages.py   transcript message models
src/baldric_agent/tools.py      tool calls, tools, and tool results
src/baldric_agent/events.py     event models emitted by the agent layer
```

这些模块 provider 中立、UI 中立。不提 Anthropic、OpenAI、Rich、Textual、Typer、本地文件或终端渲染。

## 消息为什么存在

消息代表 transcript：agent 与模型协作的对话状态。

Baldric 目前定义：

- `UserMessage`
- `AssistantMessage`
- `ToolResultMessage`
- `AgentMessage`

### `UserMessage`

`UserMessage` 存储用户写的文本。

```python
UserMessage(content="Read README.md")
```

之后，harness 会在用户提交 prompt 时追加一条。

### `AssistantMessage`

`AssistantMessage` 存储 assistant 文本与可选 tool call。

```python
AssistantMessage(
    content="I'll inspect the README.",
    tool_calls=[...],
)
```

这很重要，因为 assistant 一轮可以做两件事：

1. 产出可见文本
2. 请求工具执行

未来的 agent loop 会把流式模型输出收集进 `AssistantMessage`。
消息带 tool call 时，循环执行那些工具并继续。

### `ToolResultMessage`

`ToolResultMessage` 存储一次具体 tool call 的结果。

```python
ToolResultMessage(
    tool_call_id="call-1",
    name="read",
    content="file contents...",
    ok=True,
)
```

模型需要 transcript 里的工具结果，才能在工具运行后继续推理。例如：

```text
User asks to read README.md
Assistant calls read
Baldric executes read
Baldric appends ToolResultMessage
Assistant sees file contents and answers
```

### `AgentMessage`

`AgentMessage` 是所有消息类型的联合。它让后续 API 以

```python
list[AgentMessage]
```

接受 transcript，而不必关心每条来自用户、assistant 还是工具。

## 工具类型为什么存在

工具是 assistant 请 Baldric 与环境交互的方式。

Baldric 目前定义：

- `ToolCall`
- `AgentTool`
- `AgentToolResult`

### `ToolCall`

`ToolCall` 不是工具本身。它是用类 JSON 参数运行某个具名工具的请求。

```python
ToolCall(
    id="call-1",
    name="read",
    arguments={"path": "README.md"},
)
```

未来的 provider 适配器把 provider 特定的 tool call 载荷翻译成这个中立的 Baldric 形状。

### `AgentTool`

`AgentTool` 描述一个 Baldric 可以暴露给模型的工具。

它包含：

- `name`
- 人类可读的 `description`
- `input_schema`
- 异步 `executor`

编码 agent 层之后会注册内置工具：

- `read`
- `write`
- `edit`
- `bash`

但可移植的 agent loop 只需要知道 `AgentTool` 能带参数执行并返回 `AgentToolResult`。

### `AgentToolResult`

`AgentToolResult` 是工具执行的结构化输出。

```python
AgentToolResult(
    tool_call_id="call-1",
    name="read",
    ok=True,
    content="file contents...",
)
```

之后，loop 把工具结果转成 `ToolResultMessage` 并追加进 transcript。

## JSON 类型为什么存在

工具参数与 provider 载荷需要类 JSON，因为模型 API 以 JSON 交换结构化数据。

Baldric 定义共享别名：

- `JSONPrimitive`
- `JSONValue`
- `JSONObject`

这让工具 schema、工具参数、事件数据与 provider 中立载荷保持类型安全，而不绑定特定 provider SDK。

## 事件为什么存在

事件是可复用 agent 层报告进展、却不知道谁在监听的方式。

这是关键设计：

```text
Agent loop emits events
        ↓
CLI print mode consumes events
Rich renderers consume events
Textual TUI consumes events
Tests can inspect events
```

Baldric 目前为以下内容定义事件：

- agent start/end
- turn start/end
- assistant 消息 start/delta/end
- 工具执行 start/update/end
- 错误

## 事件未来如何流动

未来的一次 prompt 运行可能产生这样的序列：

```text
agent_start
turn_start
message_start
message_delta       "I'll inspect the file."
message_end         AssistantMessage(... tool_calls=[read])
tool_execution_start
tool_execution_end  AgentToolResult(...)
turn_end
turn_start
message_start
message_delta       "The README says..."
message_end         AssistantMessage(... no tool calls)
turn_end
agent_end
```

要点是同一条事件流可以驱动多个 frontend。
内核循环不需要 `print()`、Rich 面板或 Textual 组件。

## Phase 1 如何支撑后续阶段

### Phase 2：provider 层

provider 把外部模型流翻译成 Baldric 消息、tool call 与
provider 中立事件。

### Phase 3：纯 agent loop

loop 用这些类型：

1. 向 provider 发送消息
2. 收集 assistant 输出
3. 检测 tool call
4. 执行 `AgentTool`
5. 追加 `ToolResultMessage`
6. 全程发出 `AgentEvent`

### Phase 4：harness

harness 维护一份 `AgentMessage` transcript 并暴露
`prompt()` 与 `continue_()` 这类更高层方法。

### Phase 6 及以后：UI

print mode、Rich 渲染、JSON 事件流与 Textual 消费
`AgentEvent`，而不伸进 loop、provider 或 harness 内部。

### Phase 7：session

session 持久化保存并回放消息对象与相关状态变更。
消息模型给那层持久化一个稳定基底。

## 设计规则

类型属于可复用 agent 大脑，就住在 `baldric_agent`。
类型知道命令行行为、项目文件、slash 命令、prompt 或 UI 渲染，就属于内核 agent 包之外。
