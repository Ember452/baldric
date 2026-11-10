# provider 重试策略

**状态：** 已接受 —— 2026-11-06（分支 `chore/p0-contract-baselines`）

## 变更了什么

四个适配器各带同一份 `_should_retry` 拷贝，没有读 `Retry-After`，`retry_delay_seconds` 总用固定指数延迟。要求等 60 秒的
`429` 在 250 毫秒后就被重试——那是在拉长限速而不是熬过它。

现在一份策略住在 `baldric_ai/retry.py`：

| 行为 | 规则 |
| --- | --- |
| 可重试状态 | 408、409、425、429 与 >= 500 |
| 服务器指引 | `retry-after-ms`，然后 `retry-after`（秒数或 HTTP 日期），精确使用 |
| 服务器覆盖 | `x-should-retry: true/false` 胜过状态默认 |
| 超过上限的延迟 | 请求立即失败并附注记，而不是阻塞 |
| 回退延迟 | 指数、封顶、最多 25% 抖动 |
| context 溢出 | 绝不重试，即使以 400 到达 |
| 认证失败 | 绝不重试 |

每次失败还携带稳定代码：`auth`、`timeout`、`conflict`、
`too_early`、`rate_limit`、`context_overflow`、`server_error`、
`invalid_request`、`retry_after_too_long`（Codex 的终态配额错误为 `rate_limit_exhausted`）。代码经 `ProviderErrorEvent.data["code"]`
传递并因此到达持久化的 provider 诊断，loop 与 UI 可以按代码分支，而不是匹配消息文本。

## 参考

Pi 的 `packages/ai/src/utils/provider-retry.ts` 是本策略遵循的形状：
先 `retry-after-ms` 再 `retry-after`、超过预算的服务器延迟直接失败而非睡眠、`x-should-retry` 覆盖状态默认、带抖动的指数回退。两处刻意差异：

- Pi 默认预算 60 秒；Baldric 一秒，所以更多服务器延迟在这里快速失败。
- Pi 保留 408/409/429/5xx；Baldric 也重试 425——其早期政策覆盖了它。

Pi 包裹请求 promise（`retryProviderRequest`）；Baldric 的流是异步
生成器，所以同样的决策在每个失败点应用。

## 刻意选择

- **服务器长延迟快速失败。** Baldric 默认
  `max_retry_delay_seconds` 一秒，要求 60 秒的服务器被报为 `retry_after_too_long` 而不是重试三次。Pi 面对 60 秒预算做同样判断：调用者预算内无法重试的请求就该直说。
- **只在回退上加抖动。** 服务器提供的延迟被精确使用；抖动是为了并发客户端不同步重试。
- **425 保持可重试。** 罕见，但移除它会静默停止重试一个原本有效的场景。
- **流级重试保持指数延迟。** 那些路径没有响应 header 可遵守；只有 HTTP 失败路径获得了服务器指引。

## 可见性

重试不再静默。适配器仍发内部
`ProviderRetryEvent`；`baldric_ai/stream.py` 现在把它转成公开的
`AssistantRetryEvent`，loop 转成 agent 级
`RetryAttemptEvent`（`provider_retry`），`baldric_coding/session/retry_events.py`
把它与 transcript、JSON、TUI 已在渲染的 `auto_retry_start` / `auto_retry_end` 事件配对。失败的运行因此显示 "retrying (2/3) in 1s" 而不是在退避期间看似挂死。

Pi 在其重试 helper 上以重试回调（`onRetryScheduled` /
`onRetryFinished`）声明同样的信息并在 coding session 消费。Baldric 的流是异步生成器，所以它以事件而非回调携带通知；行为一致，机制不同。

## 不覆盖的范围

- provider 特定的流错误（Anthropic `overloaded_error`、Codex 瞬时
  标记）保留各自谓词；只有 HTTP 路径被集中化。
- `ToolCallDeltaEvent` 仍从不生产：解析器只发一条完整的
  `ProviderToolCallEvent`，流式工具参数片段尚未呈现（另行跟踪）。

## 测试

- `tests/ai/test_retry_policy.py`：确切 `Retry-After` 秒数、`retry-after-ms`
  优先、HTTP 日期解析、超限快速失败、抖动带、稳定
  代码、context 溢出与认证拒绝、`x-should-retry` 覆盖、尝试
  上限、不可解析值、零延迟预算。
- `tests/ai/test_retry_http.py`：带 `Retry-After: 0.01` 的 `429` 第二次请求成功；60 秒请求一次后失败、诊断含
  `retry_after_too_long`；context 溢出响应体不重试。
- 既有适配器测试断言整个诊断对象，现在含 `code`；那些期望被扩展而非放宽。
