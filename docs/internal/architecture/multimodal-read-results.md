# read 工具的多模态结果

Baldric 的 `read` 工具现在从文件魔数识别受支持的图片，把它们作为规范 `ImageContent` 块与短文本提示一起返回。处理后的附件上限 5 MB，动画 PNG 不再被视为受支持的静态 PNG 附件。超大的静态图片现在由后续的[有界 read 图片处理](./read-image-processing.md)归一化。
agent loop 本就保留有序的
工具结果内容，所以图片数据在 `baldric_ai`
序列化边界之前保持 provider 中立。

每个 provider 适配器把图片块映射到其 wire 格式：

- Anthropic 把 base64 图片块嵌进 `tool_result.content`。
- OpenAI Responses 与 Codex 在 function-call 输出里用 `input_image` 块。
- OpenAI Chat Completions 与 Mistral 保留文本工具结果，把图片放进随后的用户消息。
- Gemini 3 使用多模态 `functionResponse.parts`；更旧的 Gemini 模型收到单独的用户图片消息。

运行时 provider 配置从所选模型的目录 `input` 元数据推导图片支持。每个 provider 配置——包括独立的
`OpenAICodexProviderConfig`——在运行时创建中保留该元数据。稀疏的 OpenAI Codex、OpenCode Go、OpenCode Zen 与 GitHub Copilot 目录条目现在为每个模型声明输入模态，与 Pi 生成的
provider 目录一致。纯文本模型收到显式的省略标记，避免无效 provider 请求，并让缺失的视觉上下文对模型可见。GitHub Copilot 图片请求还带其必需的
`Copilot-Vision-Request: true` header。

图片 base64 载荷从工具结果 `details` 移入 `content`。这避免重复的 session 存储，并让所有 frontend 继续渲染小文本提示而不暴露 base64 数据。

## 验证

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```
