---
title: "provider 重试事件"
---

Baldric 在 `baldric_ai` 里重试瞬时 provider 失败——那里看得见 HTTP 状态码与
transport 异常。这把重试分类挡在 `baldric_agent` 之外，同时仍让可移植的 agent loop 呈现进展。

## 加了什么

provider 适配器可以在重试失败请求之前发出 `ProviderRetryEvent`。
事件包含下次尝试编号、总尝试数、延迟、
人类可读消息与结构化诊断数据。

`run_agent_loop()` 把该 provider 事件映射为 `RetryEvent`——一个 provider 中立的
agent 事件，由渲染器与 TUI 适配器消费。

## 行为

OpenAI 兼容、Anthropic 与 OpenAI Codex 订阅 provider 对 `408`、`409`、`429` 与 `5xx` 响应等瞬时状态码重试，之后才呈现最终 provider 错误。默认两次重试，共三次请求尝试。

Anthropic 与 OpenAI Codex 适配器还重试瞬时的**流内**失败。两个 API 都可能返回 HTTP 200 然后发送 SSE 错误事件。对
Anthropic，可重试错误类型是 `api_error`、`overloaded_error` 与
`rate_limit_error`。Codex 对照 overloaded、service unavailable、rate limit、
internal/server errors 与 timeouts 等瞬时标记分类 `error` 与 `response.failed` 事件。

当流内错误在内容或 thinking delta 之前到达时，适配器发出 `ProviderRetryEvent` 并在相同 `max_retries`
预算内重发请求。部分内容之后的错误，以及
`authentication_error` 或 `invalid_api_key` 这类非瞬时错误保持终态，避免重放可见输出或工具调用。

退避短、指数、由 `max_retry_delay_seconds` 封顶。
退避延迟期间检查取消，Escape/TUI 取消不必等完整个重试睡眠。

## 渲染

transcript 与 TUI 渲染器把重试进度显示为含蓄的状态输出。最终
text mode 忽略重试进度，只打印最终 assistant 回复或最终错误。

## 边界

`baldric_agent` 不判断 HTTP 响应是否可重试。它只把
`RetryEvent` 作为可移植进展转发。provider 特定细节留在适配器的 `data` 载荷里供诊断。
