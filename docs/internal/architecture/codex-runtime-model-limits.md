# Codex 运行时模型限制

Issue: [#389](https://github.com/huggingface/tau/issues/389)

## 生产事故

一个长运行的 Baldric session 经 `openai-codex` OAuth
provider 使用 `gpt-5.6-sol`。其最后一次成功请求报告约 371,440 cached 加
uncached 输入 token。下一次请求失败于
`context_length_exceeded`。

Baldric 把直连 OpenAI API 的 1.05M context 元数据拷进了 Codex
订阅目录，所以其默认 compaction 阈值是 1,033,616 token。
请求实际发往 `https://chatgpt.com/backend-api/codex/responses`，那里 Codex 订阅限制是独立配置的。服务器下发的 Codex 目录报告显示约 372K 的 profile，后期 rollout 中为 272K。Baldric 因此从未在真实 backend 上限之前 compact。

这是服务面问题，不是公共 API 模型页的自相矛盾：直连 API 访问与 ChatGPT/Codex OAuth 对同一模型 ID 可以用不同限制。

## 考虑过的方向

### 硬编码 500K Codex 窗口

确定性、避免又一次启动请求，但 500K 是总预算，常被描述为 372K 输入加 128K 输出。Baldric 旧的 compaction 公式把 `context_window` 当可用输入预算，只减
16,384 token。500K 条目会在约 483K compact——已经超过报告的 372K 输入上限——修不了事故。

较低的硬编码值可作为安全回退有用。本变更对 GPT-5.6 Codex 变体用 272K，匹配最近观察到的最保守 Codex 目录 profile。直连 OpenAI API 条目保持 1.05M。静态值本身不是长期答案，因为 Codex 在 rollout 期间改过它们，且可按账户变化。

### 发现认证后的 Codex 目录

官方 Codex 客户端请求：

```text
GET <codex-base>/models?client_version=<version>
```

对 Baldric 的默认 base URL，解析为：

```text
https://chatgpt.com/backend-api/codex/models
```

请求使用与响应请求相同的刷新后 OAuth token、ChatGPT 账户 ID 与
originator headers。模型条目可含：

```text
slug
context_window
max_context_window
effective_context_window_percent
auto_compact_token_limit
```

动态发现反映真实服务面与账户。缺点是这是 Codex 产品端点而非公共 OpenAI API 模型契约，schema 或可用性可能变化。

## 决策

用**动态发现加保守静态回退**。

`baldric_ai` 拥有认证请求与防御性解析。它实现可选的 provider 中立 `ModelLimitsProvider` 能力，返回类型化的
`RuntimeModelLimits` 值。忽略畸形条目，每个 provider 实例缓存一份目录。

`baldric_coding` 在 session 加载时、以及 provider 或模型切换后、发送下一条 prompt 前请求限制。它应用实时原始 context
window 与 provider 显式 compaction 限额或 Codex 的 90% 原始窗口默认。发现失败非致命：配置的 provider
目录保持活动，`/session` 报告来源与错误。

`baldric_agent` 不变。它收到就绪 provider，保持对 OAuth、模型目录、Baldric home 路径与 compaction 政策独立。

首个实现刻意避免持久的活动目录缓存。内存缓存防止一个运行时 provider 内的重复请求；
每个新 session 拿到新鲜的账户级值。磁盘缓存需要过期策略、ETag 处理、凭据/账户分区、原子写入，以及"过期值是否比保守内置回退更安全"的明确规则。这些顾虑可以日后加，而不改发现协议。

## 限制语义

`RuntimeModelLimits` 把四个概念分开：

- 原始 context window
- 宣传时的最大输出 token
- 有效 context 百分比
- 宣传时的显式自动 compaction 阈值

没有返回阈值时，Baldric 用原始 context window 的 90% 并钳到有效窗口。这镜像官方 Codex 客户端的默认，为 provider 组帧、工具、指令与输出留余量。

Baldric 按字符的用量估算器仍是近似值。在硬性远程限制附近提早 compaction 是有意的。

## 失败行为

目录发现无法阻止所有溢出：backend 可能在发现与响应之间变化，token 估算也可能低估 provider 组帧。Baldric 既有的溢出路径仍是第二道防线：识别 context 溢出、compact 较旧消息并重试一次。动态发现让主动路径足够准确，紧急恢复应当罕见。

## 测试

确定性测试用 `httpx.MockTransport` 与 fake 模型限制 provider。覆盖：

- 认证后的 Codex 模型目录 URL 与 headers
- 防御性解析与内存缓存
- coding session 中的实时 context/compaction 值
- 发现失败时的非致命回退
- 直连 API 与 Codex 内置元数据的分离

运行：

```bash
uv run pytest tests/test_baldric_ai.py tests/test_coding_session.py \
  tests/test_provider_catalog.py tests/test_provider_runtime.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

## 手动验证

1. 用 `/login openai-codex` 登录。
2. 选一个 GPT-5.6 模型。
3. 开始或恢复一个 session。
4. 运行 `/session`。
5. 确认 `Context window source` 为 `provider live catalog`，且显示的限制/compaction 阈值与同一账户的 `codex debug models` 一致。
6. 阻断 models 请求或用非法发现数据，确认 Baldric 以 `configured catalog` 启动、报告非致命发现失败，且仍能发送正常模型请求。
