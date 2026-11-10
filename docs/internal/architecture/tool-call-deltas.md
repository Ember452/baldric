# 流式 tool-call 参数

**状态：** 已接受 —— 2026-11-06（分支 `reliability/p3-and-followups`，#52）

## 变更了什么

`ToolCallDeltaEvent`（`toolcall_delta`）在公开 assistant 流契约里却从未被生产：每个解析器累积参数片段、发出一条完整的 `ProviderToolCallEvent`，所以 `stream.py` 把
`toolcall_start` 与 `toolcall_end` 背靠背 yield，中间什么都没有。消费者无法在参数到达时渲染它们。

Pi 的每个适配器在片段文本流入时发出 `toolcall_delta`。同样的信息现在经 Baldric 传递：

- `ProviderToolCallStartEvent(index)` 标记一次调用的第一个片段。
- `ProviderToolCallDeltaEvent(index, delta)` 携带一段原始 JSON 片段。
- 完整的 `ProviderToolCallEvent` 仍终结该调用。

适配器按"首片段发 start、每片段发 delta"发射：OpenAI 兼容
chat 与 Mistral 来自 `tool_calls[].function.arguments`，Anthropic 来自
`input_json_delta`（在 `content_block_start` 发 start），OpenAI Codex 来自
`response.function_call_arguments.delta`。Google 的 Gemini 流一次性送达整个
`functionCall`，因此保持仅完整路径——没有 delta 是合法的。

## 流组装

`baldric_ai/stream.py` 在 start 时分配占位 `ToolCall` 块，把每个片段
追加进缓冲，在 complete 事件上用最终解析的调用替换该块。多调用响应按 start 顺序以 FIFO
队列配对，因此交错的调用按开始顺序结束——即使 complete 事件不带索引。

## 测试

- `tests/ai/test_stream_tool_deltas.py`：一次流式调用产出
  start → deltas → end，片段拼接等于最终参数，仅完整路径仍产出 start/end，两个交错调用按序配对。
- `tests/ai/test_baldric_ai.py::test_openai_compatible_provider_streams_tool_calls`
  现在断言适配器真的在 start 与 end 之间发出 `toolcall_delta`。
