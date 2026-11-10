# 被截断的响应绝不执行 tool call

**状态：** 已接受 —— 2026-11-06（分支 `chore/p0-contract-baselines`）

## 变更了什么

当 assistant 轮因输出 token 上限而停止
（`stop_reason == "length"`）且携带 tool call 时，循环不再执行其中任何一个。每个调用改报为可恢复错误：

- `tool_execution_start` / `tool_execution_end` 带 `is_error=true`；
- 每个调用一条 `ToolResultMessage`，文本说明该调用未执行、应以完整参数重发；
- 照常 `turn_end`，然后再来一轮让模型重发。

纯文本的截断轮不变：仍照旧结束运行。

## 为什么

流式工具参数以尽力而为的 JSON 抢救定稿。被切断的响应可能携带能解析、能通过校验但悄悄不完整的参数。schema 校验抓不住这类错误，因为截断值仍是形状正确的合法 JSON。故障模式是部分命令或部分 patch 产生的真实副作用，所以唯一安全的默认是什么都不执行。

## 界限

只有模型能产出完整响应时重发才有用，所以循环在连续三次截断工具轮之后停止。计数器在任何正常轮上重置；没有界限，总是截断的模型会永远循环，因为截断轮不推进 provider 失败计数。

## 测试

`tests/agent/test_agent_loop.py`：

- `test_length_truncated_tool_calls_are_not_executed` —— 两个调用，工具从不运行，两个结果都是错误，模型收到第二次请求；
- `test_length_without_tool_calls_ends_normally` —— 纯文本对照；
- `test_repeated_truncated_tool_turns_stop_the_run` —— 恰好三次请求后到达界限；
- `test_a_normal_tool_turn_resets_the_truncation_budget` —— 两次截断、一个正常工具轮、再两次截断仍允许最后一次请求。

测试直接构建 `AssistantDoneEvent(reason="length", ...)`：共享的
`assistant_done` helper 会把任何带 tool call 的消息映射为 `toolUse`，从而掩盖被测场景。

## 参考

Pi 在
`packages/agent/src/agent-loop.ts:488-513` 的 `failToolCallsFromTruncatedMessage` 对该批次同样处理。连续轮界限是 Baldric 特有的：Pi 此处没有无限循环守卫，因为其持久内核把轮次调度为有各自限额的任务。
