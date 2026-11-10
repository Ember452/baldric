# 恢复被拒的图片工具结果

## 行为

即使经过 read 工具的本地缩放，provider 仍可能拒绝一张或一批图片。此前，assistant 收不到有用的工具反馈、运行直接结束。可移植的 agent loop 现在会立即恢复紧跟图片工具批次之后的空 provider 失败：

1. 原样持久化失败的 assistant 消息与原始工具结果。
2. 把被拒图片结果投影为纯文本、`is_error=True` 的工具
   响应，保留调用 ID、文本输出与工具元数据。附上 provider 的错误并建议更小的图片或另一方案。
3. 继续 provider 循环而不重新执行任何工具。连续第三次失败的 provider 响应时停止。成功响应重置计数。

恢复刻意是尽力而为，不绑定特定厂商的图片错误字符串。图片工具响应之后的宕机同样受同一条三次失败限制约束。既有的适配器级网络重试保持独立。没有近期图片工具批次的错误、部分流式输出与被中止的请求保持其终态行为。取消与 `max_turns` 仍然获胜。

## 架构与回放

这遵循 Pi 的大脑/环境/frontend 分离：`baldric_agent` 拥有
provider 中立的工具反馈与有界循环控制，`baldric_ai` 保留 wire
序列化/重试，`baldric_coding` 呈现恢复进度。

`_provider_context` 从持久的失败 assistant 轮推导安全 context。
它只拷贝被拒的工具结果，绝不改动原始消息。
这保持 append-only JSONL 持久化，并让回放/resume 重建出
同一份安全 context。只有最近一次工具批次的图片被移除；
先前接受的图片与纯文本结果保持完好。对被拒批次，其全部图片结果都被降级，因为 provider 中立的错误无法可靠识别是哪个附件引起的拒绝。

在发出可恢复失败的 `message_end` 之前，循环追加一条
`tool_result_recovery` assistant 诊断。frontend 把该失败渲染为进展而非终态错误，print 渲染器不让命令失败，
coding-session 编排不为该中间失败启动溢出 compaction 或路由
failover。最后一次失败请求没有恢复诊断，走正常的终态错误处理。

## 验证

```bash
uv run pytest tests/agent/test_image_tool_recovery.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

聚焦测试用 fake provider 错误，包括超过三次请求的宕机、成功的计数重置、取消、max-turn 上限、
无关的后续错误与 JSONL 回放往返。

手动验证：用一个有严格图片或请求大小限制的视觉模型/provider，让 Baldric 读一张超过该 provider 限制的图片，确认先出现恢复进度、随后模型回复引用 API 错误或换一种方案。图片读取之后 provider 不可用时，验证运行在三次高层 provider 失败后停止而不是永远重试。回归测试不需要活动凭据。
