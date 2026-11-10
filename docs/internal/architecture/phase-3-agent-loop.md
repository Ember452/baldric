---
title: "Phase 3：纯 agent loop"
---

Phase 3 加了 Baldric 第一个真正的 agent 引擎：一条连接模型 provider、transcript 与一组工具的纯循环。

循环住在：

```text
src/baldric_agent/loop.py
```

它叫"纯"，因为不知道 CLI、Rich、Textual、slash 命令、本地 session 文件或项目专属资源。它只与 provider 中立的 Baldric 类型协作。

## 加了什么

Phase 3 加了：

- `run_agent_loop()`
- assistant 消息与工具结果的 transcript 变更
- provider 事件到 agent 事件的转换
- 顺序工具执行
- 未知工具处理
- 工具异常处理
- provider 错误处理
- 可选 max-turn 保护

后续加固增加了 steering/follow-up prompt 的队列排水 hook，以及重试与 thinking/reasoning 进度事件的
provider 中立转发。

## 循环的输入

`run_agent_loop()` 接收：

- 一个 `ModelProvider`
- 模型名
- system prompt
- 可变的 `AgentMessage` 列表
- 已注册 `AgentTool` 列表
- 可选最大轮数
- 可选取消 token
- 可选 steering/follow-up 队列排水回调
- 可选的 `QueueUpdateEvent` 队列状态回调

概念上：

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

调用者拥有 transcript。循环在工作完成时向该 transcript 追加。

## 基本纯文本流程

无 tool call 的普通响应流程：

```text
agent_start
turn_start
message_start
message_delta
message_delta
message_end
turn_end
agent_end
```

内部：

1. 循环请 provider 流式返回模型响应。
2. provider 文本 delta 变成 `MessageDeltaEvent`。
3. 最终 provider 响应变成 `AssistantMessage`。
4. assistant 消息追加进 transcript。
5. 没有 tool call，循环停止。

## tool-call 流程

assistant 请求工具时，循环在停止前执行它们。

assistant 消息示例：

```python
AssistantMessage(
    content="I'll inspect that file.",
    tool_calls=[
        ToolCall(id="call-1", name="read", arguments={"path": "README.md"})
    ],
)
```

循环随后：

1. 找到名为 `read` 的已注册 `AgentTool`
2. 发出 `tool_execution_start`
3. 异步执行工具
4. 发出 `tool_execution_end`
5. 追加 `ToolResultMessage`
6. 开始又一轮模型调用

第二次模型轮看到更新后的 transcript：

```text
UserMessage
AssistantMessage with tool call
ToolResultMessage
```

并能产出最终答案。

## 循环为什么改 transcript

循环接受可变的 `messages` 列表并向其追加新消息。

这让循环几乎无状态。之后 `AgentHarness` 可以拥有 transcript 并传入循环。循环不需要知道消息从哪来、如何持久化。

## provider 事件 vs agent 事件

Phase 2 引入了 provider 事件：

- `response_start`
- `text_delta`
- `response_end`
- `error`

Phase 3 把它们转成更高层的 agent 事件：

```text
ProviderResponseStartEvent  -> MessageStartEvent
ProviderTextDeltaEvent      -> MessageDeltaEvent
ProviderResponseEndEvent    -> MessageEndEvent
ProviderErrorEvent          -> ErrorEvent
```

UI 层因此可以监听 agent 事件而不了解 provider 内部。

后续 provider 适配器还翻译：

```text
ProviderRetryEvent         -> RetryEvent
ProviderThinkingDeltaEvent -> ThinkingDeltaEvent
```

loop 转发那些事件而不把 provider 特定载荷嵌进可移植 agent 层。

## 排队的 steering 与 follow-up

`AgentHarness` 拥有 prompt 队列，但 `run_agent_loop()` 拥有注入点。提供队列回调时：

- steering 消息在当前 assistant 轮与工具批次之后排水
- follow-up 消息在运行本会停止时排水
- 排水的消息作为普通用户消息追加进 transcript
- 循环在下一次 provider 调用前为每条注入的用户消息发出 `MessageStartEvent(message_role="user")` 与 `MessageEndEvent`
- 排水后循环发出 `QueueUpdateEvent`，frontend 得以更新待处理消息状态

不传队列回调的直接调用者保持原始行为。

## 错误处理

循环显式处理常见失败场景。

### 未知工具

模型请求未注册的工具时，循环记录失败的工具结果：

```text
Unknown tool: tool_name
```

该结果作为 `ToolResultMessage` 追加，模型可以在后续轮恢复。

### 工具异常

工具抛异常时，循环捕获并转为失败的 `AgentToolResult`。

工具是隔离边界。坏工具默认不应崩溃整个循环。

### provider 错误

provider 发出错误时，循环发出 agent `error` 事件并停止运行。

### 最大轮数

与 Pi 一样，Baldric 的循环不施加默认轮数限制。一直继续，直到 assistant 停止请求工具或出现其他正常停止条件。

想要安全上限的调用者可传 `max_turns`。达到配置限额时，循环发出可恢复错误。

## 重要边界

循环执行已注册的工具，但自己不定义编码工具。

也就是说：

```text
baldric_agent.loop:
  knows how to execute an AgentTool

baldric_coding tools:
  know how to read files, write files, edit files, or run bash
```

这让 Baldric 的可复用 agent 包独立于编码 agent 专属行为。

## Phase 3 如何支撑后续层

### AgentHarness

harness 拥有 transcript、取消 token、监听器与排队的
steering/follow-up prompt。它在 `prompt()` 与 `continue_()` 等方法里调用 `run_agent_loop()`。

### 内置编码工具

编码工具是 `AgentTool` 实例。循环执行它们，
不知道工具是读文件、写文件、编辑文件还是跑 shell 命令。

### print-mode CLI 与 TUI

渲染器与 Textual TUI 消费循环的 `AgentEvent`，决定如何
显示流式文本、工具活动、重试状态、thinking delta、队列状态与错误。

### session

session 存储持久化循环追加的 transcript 消息，包括工具结果与注入后的排队用户 prompt。

## 设计规则

agent loop 只协调 provider 流、消息、工具与事件。

行为需要 CLI 旗标、终端渲染、本地配置路径、slash 命令或项目资源时，属于 `baldric_agent.loop` 之外。
