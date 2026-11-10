---
title: "Phase 2：AI provider 层"
---

Phase 2 在 `baldric_ai` 创建 Baldric 的 provider/model 流式层。

这一层的目的是让 Baldric 与模型 API 对话，而不让 provider 特定细节泄漏进可复用的 agent loop。

## 加了什么

Phase 2 加了这些模块：

```text
src/baldric_ai/events.py              provider-neutral stream events
src/baldric_ai/provider.py            ModelProvider protocol
src/baldric_ai/fake.py                deterministic fake provider for tests
src/baldric_ai/env.py                 environment-based provider configuration
src/baldric_ai/openai_compatible.py   OpenAI-compatible chat completions adapter
```

## provider 层为什么存在

模型 API 的流式方式各不相同。每个 provider 有自己的请求格式、响应分块、tool call 编码、错误形状与认证规则。

Baldric 不想让 agent loop 知道那些细节。

切分是：

```text
Provider API payloads
        ↓
baldric_ai adapter
        ↓
ProviderEvent stream
        ↓
baldric_agent loop
```

未来的 agent loop 无论背后是哪家模型，都消费同一条 Baldric 事件流。

## provider 事件

provider 事件比 agent 事件更低层。

它们描述模型正在流式输出什么，而不是整个 agent 在做什么。

当前的 provider 事件：

- `ProviderResponseStartEvent`
- `ProviderTextDeltaEvent`
- `ProviderToolCallEvent`
- `ProviderResponseEndEvent`
- `ProviderErrorEvent`

一次简单的文本响应可能像这样：

```text
response_start
text_delta       "Hel"
text_delta       "lo"
response_end     AssistantMessage(content="Hello")
```

带 tool call 的响应可能像这样：

```text
response_start
text_delta       "I'll inspect that file."
tool_call        ToolCall(name="read", arguments={"path": "README.md"})
response_end     AssistantMessage(... tool_calls=[...])
```

## `ModelProvider`

`ModelProvider` 是每个模型适配器必须满足的协议。

概念上它说：

```python
provider.stream_response(
    model="...",
    system="...",
    messages=[...],
    tools=[...],
)
```

并返回 provider 事件的异步流。

这就是让 Baldric 日后支持多 backend 的接缝。

## fake provider

`FakeProvider` 回放脚本化的 provider 事件。

这很重要，因为 Baldric 的测试应不依赖：

- 网络访问
- API key
- 非确定性模型输出
- provider 限速

之后，纯 agent loop 可以用一个 fake provider 测试——它精确发出测试需要的文本与 tool call。

## OpenAI 兼容 provider

第一个真实适配器面向 OpenAI 兼容 `/chat/completions` API。

它处理：

- bearer token 认证
- chat 消息格式化
- 工具 schema 格式化
- server-sent event 流式
- 流式文本 delta
- 流式 tool call 参数组装
- provider 错误

配置经以下方式加载：

```python
openai_compatible_config_from_env()
```

使用：

```text
OPENAI_API_KEY
OPENAI_BASE_URL
```

`OPENAI_BASE_URL` 默认：

```text
https://api.openai.com/v1
```

## 重要边界

`baldric_ai` 不执行工具。

模型请求工具时，provider 层只发出携带中立 `ToolCall` 的 `ProviderToolCallEvent`。

工具执行属于未来的 `baldric_agent` loop：

```text
baldric_ai:
  "The model requested this tool call."

baldric_agent:
  "Find the registered AgentTool, execute it, append the result, continue."
```

保持这条边界干净，让同一 provider 层能被 CLI、测试、Rich 输出、Textual 与其他 frontend 复用。

## Phase 2 如何支撑后续阶段

### Phase 3：纯 agent loop

loop 消费 `ProviderEvent`，转成更高层的
`AgentEvent`，执行工具，并判断是否需要另一轮模型调用。
后续的 provider 加固在同一条转换路径上加了重试与 thinking delta 事件，而没有让 provider 知道 CLI 或 TUI。

### Phase 4：harness

harness 拥有一个 provider 实例，把当前 transcript 传入
`stream_response()`，并暴露 print mode、JSON 事件流、Rich 渲染与 Textual 都能用的 prompt/continue API。

### Phase 6：print-mode CLI

CLI 从配置或命令行旗标选择 provider/model，然后随输出到达流式显示。

### 未来的 provider

更多 provider 可以实现同一 `ModelProvider` 协议，而不改 agent loop。
