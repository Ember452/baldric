---
title: "Phase 20.2：thinking mode 控制"
---

Phase 20.2 让 thinking mode 成为显式的 Baldric coding-session 设置，并加了
更改它的 TUI 控件。

## 加了什么

`baldric_coding.thinking` 定义 Baldric 支持的 thinking 模式：

```text
off
minimal
low
medium
high
xhigh
```

默认 `medium`，匹配 Pi 的默认推理深度偏好。Baldric 对照 provider/model 能力校验可见控件，并在配置的 provider 声明支持时传递
OpenAI 兼容的 `reasoning_effort`。不支持的模型把 thinking 控件显示为不可用，而不是呈现 Baldric 无法安全发送的模式。

## session 持久化

新 session 在初始 model entry 之后追加一条初始 `thinking_level_change` entry。显式变更追加另一条 `thinking_level_change` entry。作为最后一条非 legacy 叶 entry 它成为活动尖，resume 因此从 session 树重建活动 thinking 模式。

`CodingSession` 暴露：

```python
session.thinking_level
session.available_thinking_levels
await session.set_thinking_level("high")
await session.cycle_thinking_level()
```

这把 thinking 状态留在 `baldric_coding`，而 `baldric_agent.session` 保持为知道如何重建 `ThinkingLevelChangeEntry`
值的可移植回放层。

## 命令与 TUI

Textual TUI 默认把 thinking 轮换绑到 `Shift-Tab`。键位可在 `~/.baldric/tui.json` 配置：

```json
{
  "keybindings": {
    "thinking_cycle": "f3"
  }
}
```

侧栏与紧凑 session 行先读 `session.available_thinking_levels`。活动 provider 或 model 没有 thinking 能力元数据时，
TUI 把控件显示为不可用。用户仍尝试轮换或设置 thinking mode 时，session 抛出面向用户的理由。

Baldric 不在默认命令注册表注册独立的 `/thinking` 命令。命令面与 Pi/Codex 保持一致：模型选择与推理控制属于模型选择与 session 状态。活动
provider/model 无法变更 thinking mode 时，`/session` 报告 `Thinking mode: unavailable` 加原因。

## provider 能力

provider 设置可用以下方式声明 thinking 支持：

```json
{
  "thinking_levels": ["off", "low", "medium", "high"],
  "thinking_models": ["gpt-5.5"],
  "thinking_default": "medium",
  "thinking_parameter": "reasoning_effort"
}
```

`thinking_models` 可选。省略时声明的级别适用于该 provider 的全部模型。Baldric 内置 provider 只对加入模型时核实过推理控件的模型声明 thinking 支持。
添加新目录模型时，先核对 provider 文档/API，只为确实支持 Baldric 配置的 thinking 参数的模型更新
`thinking_models`。

支持的参数映射：

- `reasoning_effort`：顶层 OpenAI 兼容 chat-completions 字段。
- `reasoning.effort`：嵌套 Responses API 形状，显式选择加入的 provider 配置以
  `{ "reasoning": { "effort": "...", "summary": "auto" } }` 发送。
- `anthropic.thinking`：Anthropic 扩展 thinking，以
  `{ "thinking": { "type": "enabled", "budget_tokens": ... } }` 发送。

控件不可用时 Baldric 记录显式原因：

- 无 `thinking_levels` 的 provider 报告 provider 未声明 thinking 能力元数据。
- 有 `thinking_models` 的 provider 在模型不在能力集内时报告活动模型未列出。
- 活动 model 声明为有能力时，provider 特定配置使用上表映射的运行时参数。

这让持久 provider 元数据留在 `baldric_coding`，provider 特定的运行时旋钮在 `baldric_ai`，显示选择在 CLI/TUI 代码。

## provider 对照

OpenAI 公共 API 为 chat completions 暴露 `reasoning_effort`，为 Responses API 推理模型暴露
`reasoning.effort`。支持的值随模型而定；当前文档列 `none`、`minimal`、`low`、`medium`、`high`、
`xhigh`，默认与支持因模型而异。Baldric 的直连 OpenAI 条目只对配置为推理可用的模型把
Baldric 归一化级别映射到 `reasoning_effort`。

Codex 客户端为受支持模型暴露 `model_reasoning_effort`。Baldric 镜像
Pi 的 Codex 订阅映射：`off` 省略 `reasoning` 字段，`minimal`
请求 `low`，启用的级别发送 `reasoning.effort` 加
`reasoning.summary: "auto"`。内置 `openai-codex` 模型只对已验证的 GPT-5.x Codex 模型清单声明该支持。

Anthropic 用过显式扩展 thinking token 预算与较新的 adaptive/effort 控件，支持随模型家族变化。Baldric 为声明支持扩展 thinking 的
内置 Claude 模型把归一化 thinking 级别映射为显式 Anthropic `budget_tokens`。`off` 省略
`thinking` 载荷。

没有声明能力元数据的模型或 provider 被视为没有可配置 thinking mode。控件隐藏期间保留其既有 session thinking 设置，切回有能力的模型时若设置有效可以复用。有能力的目标模型不支持当前级别时，Baldric 收敛到该模型/provider 默认。

## 边界

thinking 控件留在 Textual 专属渲染之外。provider 适配器
把受支持的推理流转为 provider 中立 thinking 事件，
`baldric_agent` 转发那些事件而不记录为持久 assistant 消息，Textual TUI 决定显示或隐藏。内置
TUI 默认隐藏 thinking token，暴露 `Ctrl+T` 作为 frontend 开关。

## 测试

本阶段覆盖于：

```text
tests/test_thinking.py
tests/test_commands.py
tests/test_coding_session.py
tests/test_agent_loop.py
tests/test_baldric_ai.py
tests/test_tui_adapter.py
tests/test_tui_config.py
tests/test_tui_app.py
```
