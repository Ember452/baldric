# Z.AI thinking 序列化

## 变更了什么

当 `supportsReasoningEffort` 为 false 时，Z.AI 的 OpenAI 兼容请求现在保留 Baldric 的逻辑 thinking 状态。请求使用 Z.AI 文档记载的 `thinking` 对象：

```json
{"thinking": {"type": "enabled"}}
```

Baldric 的 `off` 模式发送 `type: "disabled"`。不再发送无法识别的 `enable_thinking` 字段。

Z.AI 文档把 `reasoning_effort` 记为独立字段，仅 GLM-5.2 及更新版本支持，取值随模型而定。Baldric 只在兼容性元数据声明所选模型支持时才发送该字段。这保住了针对 GLM-5.1 之类模型的 provider 级守卫，同时允许在目录证据支持时的显式模型级选择加入。

## 为什么

旧的请求构建器在 `supportsReasoningEffort` 为 false 时，会在 provider 序列化之前把逻辑 effort 过滤为 `None`。于是 Z.AI 的序列化器把 thinking 视为禁用，即使用户选了 `high`。把逻辑开关处理与原始 effort 字段支持分开，修复了状态丢失，又不会为其他 provider 启用不支持的字段。

## 验证

离线 `httpx.MockTransport` 测试覆盖：

- Z.AI 启用与禁用 thinking 的载荷；
- 有/无独立支持 effort 字段的 Z.AI 模型；以及
- 既有的、省略不受支持 OpenAI `reasoning_effort` 字段的守卫。

协议证据：

- <https://docs.z.ai/guides/capabilities/thinking>
- <https://docs.z.ai/api-reference/llm/chat-completion>
