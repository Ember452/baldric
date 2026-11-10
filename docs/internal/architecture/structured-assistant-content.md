# 结构化 assistant 内容与持久化 thinking

## 变更了什么

Baldric 现在把 provider 响应保存为有序的 assistant 内容块：

- 文本
- thinking/reasoning
- tool call

定稿的 Pi 形状 `AssistantMessage.content` 数组持久化在 session
JSONL 里。其 `text`、`thinking_text` 与 `tool_calls` 属性为当前应用与 extension 消费者提供便捷视图。

使用字符串 `content` 加独立 `tool_calls` 的 legacy Baldric session 行在 JSONL 存储边界迁移为规范的 Pi 消息形状。

## 为什么

thinking 以前只以瞬态 `ThinkingDeltaEvent` 存在。它可以在活动响应期间显示，但在 `message_end` 丢失。这让被恢复的 transcript 不完整、妨碍忠实的导出与 provider 回放，并迫使
TUI 猜测 thinking 属于哪里。

Pi 把 thinking、文本与 tool call 保持在同一条有序 assistant 内容数组里。Baldric 现在遵循同一核心不变量，同时为既有 Python API 与 extension 系统保留兼容属性。

## provider 行为

provider 适配器暴露 Pi 兼容的 `AssistantMessageEvent` 流。嵌套
文本/thinking 更新支持响应式 frontend；最终响应是权威的，包含有序块与可用的不透明回放元数据：

- OpenAI 兼容 chat 保留 reasoning 字段名。
- Responses/Codex 在 transport 供给时保留序列化的 reasoning 项。
- Anthropic 保留 thinking 签名。
- Google 保留 thought 签名。
- Mistral 保留 reasoning 文本。

历史序列化器在后续工具循环请求上回放受支持的元数据。

## frontend 与 extension 行为

Textual 状态加载器按序投影持久化块，恢复的 thinking 因此可供 Ctrl+T 使用。活动的临时行在 `message_end` 时经正常 transcript 重绘路径被最终结构化块替换。该路径仍解析
extension 自定义消息、tool call 与工具结果渲染器。

extension 收到与 Baldric 其余部分相同的 Pi 形状消息与嵌套事件协议。extension 驱动的自定义消息与 TUI 渲染 hook 保持独立于
assistant 内容，继续走正常重绘路径。

## 验证

运行：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```
