# 能打断停滞流的取消

**状态：** 已接受 —— 2026-11-06（分支 `chore/p0-contract-baselines`）

## 变更了什么

取消过去是两条 SSE 行之间的布尔轮询。只有行最终会到达时它才有用：provider 挂着连接不放（排队请求、沉默上游）时没有行可查，运行只能等 HTTP 读超时——默认 60 秒。Ctrl+C 看起来像卡死。

现在三件事让取消及时：

1. `CancellationToken` 增加 `async def wait_cancelled()`。`SimpleCancellationToken`
   用 `asyncio.Event` 实现。
2. `baldric_ai.http.iter_sse_lines(response, signal)` 让每次行读取与
   `wait_cancelled()` 竞速，token 一触发立即停止。五个适配器都经它读取并在定稿前返回，被取消的流绝不产出 `done` 事件。
3. provider 流在 token 已取消时失败，循环把该轮报告为 `aborted` 而非 `error`。没有这条，用户取消会呈现为 "Provider stream ended without a terminal event"。

## 为什么 waiter 按次创建

跨生成器保留单个 waiter 会在每个正常结束的请求上保持 pending：离开 `async for` 的调用者不会关闭这个生成器，其 `finally` 可能永不运行。每次读取创建 waiter、读取获胜立即取消，让成本与读取行数成比例且不留下任何东西。

## 与 Pi 对比

Pi 把 `AbortSignal` 一路传进 provider SDK 及其 SSE 迭代
（`packages/ai/src/api/openai-completions.ts:378`、
`anthropic-messages.ts:775`），中止信号直接取消 transport 读取；SDK 还把它映射为 `stopReason: "aborted"`
（`openai-completions.ts:700`）。

Baldric 的 transport 是 `httpx`，对已在读取中的流没有按请求的中止信号。两个选项：由观察者关闭响应——抛出的 `StreamClosed` 不在可重试 transport 集合里，会呈现为 provider 错误；或让读取与 token 竞速。本变更选竞速，它让失败路径与正常的流结束完全一致。

结果语义与 Pi 一致：运行以 `aborted` 结束，不是 `error`。只有机制不同——那是 transport 层差异，不是设计差异。

## 仍在轮询的部分

- 工具保持同步 `ToolCancellationToken` 契约；运行被取消时循环取消工具任务。
- 超时时杀 POSIX/Windows 进程树是独立事项：shell 工具自己的超时路径拥有它。

## 测试

- `tests/ai/test_cancellation.py` —— 永不产出的读取在取消后 100 ms 内返回；已取消的 token 读不到任何东西；无 token 时行直接通过；空闲流正常结束。
- `tests/agent/test_agent_loop.py::test_cancel_during_a_stalled_stream_ends_as_aborted`
  —— 被取消的轮以 `aborted` 加 `Operation aborted` 结束，不是 provider 错误。
- `tests/ai/test_baldric_ai.py` 保留既有重试退避取消
  覆盖；其 token 替身子类化 `SimpleCancellationToken`，继承新方法。
