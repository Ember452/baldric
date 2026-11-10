# provider 目录活动验证 runbook

本 runbook 说明我们如何验证 Pi 衍生的 API provider 目录，以及增改 provider/模型时如何重复该流程。

目标不是为回答质量做基准。目标是证明 Baldric 显示的每个模型、每个 thinking/reasoning 级别都能被 provider API 以 Baldric 发送的载荷接受。

## 何时使用本 runbook

以下情况运行活动验证：

- 导入或重新生成 provider 目录元数据
- 添加 provider 运行时适配器
- 更改 reasoning/thinking 载荷
- 更改模型清单或默认模型
- 看到 provider 错误，如弃用模型 ID 或不受支持的 reasoning 级别

不要随意对大目录运行。即使 tiny prompt 在数百个模型与推理级别上重复也会消耗额度。

## 什么算验证通过

本轮用了 tiny prompt：

```text
Reply with exactly: OK
```

Baldric 收到 provider `response_start` 事件即算有效。意味着：

1. Baldric 成功构建了运行时 provider。
2. 凭据被足够好地接受、请求已发出。
3. provider 接受该模型 ID。
4. provider 接受该级别的 reasoning/thinking 载荷。
5. 端点开始了流式响应。

有意早早停止。等完整文本输出验证更多流内容，但花费更多 token。完整响应验证只对小样本或测试流解析行为使用。

## 验证矩阵

矩阵是：

```text
credentialed providers
  × provider.models
  × provider_thinking_levels(provider, model)
```

非推理模型用无 thinking 级别验证一次请求。

Baldric 有两个有用的目录范围：

- **有效目录**：内置目录加 `~/.baldric/catalog.toml` 用户叠加。与特定机器上 UI 显示一致。
- **打包目录**：仅内置目录。PR 验证用这个，本地用户叠加不会掩盖或重新引入过期模型。

本轮先验证有效目录以抓住本地 UI 所见，再用 `--builtins-only` 重跑摘要与重试验证 PR 目录本身。

## 本地验证 helper

我们用了临时 helper 脚本：

```text
~/.baldric/provider-validation/validate_provider_catalog.py
```

脚本有意可续跑。每次尝试向以下文件追加一个 JSON 对象：

```text
~/.baldric/provider-validation/pi-api-provider-catalog/results.jsonl
```

关键字段：

| 字段 | 含义 |
|---|---|
| `provider` | Baldric provider 名 |
| `model` | 发给 provider 的模型 ID |
| `thinking_level` | Baldric thinking 级别，非推理验证为 `null` |
| `status` | `ok` 或 `error` |
| `message` | 失败尝试的 provider/运行时错误消息 |
| `data.status_code` | 可用时的 HTTP 状态 |
| `data.body` | 可用时的截断 provider 错误响应体 |

脚本支持三种操作：

```bash
# 显示有凭据 provider、缺失凭据与总尝试数。
uv run python ~/.baldric/provider-validation/validate_provider_catalog.py plan

# 运行活动验证。
uv run python ~/.baldric/provider-validation/validate_provider_catalog.py run \
  --builtins-only \
  --concurrency 4 \
  --provider-concurrency 2 \
  --timeout-seconds 30 \
  --max-retries 0

# 汇总已记录结果。
uv run python ~/.baldric/provider-validation/validate_provider_catalog.py summarize \
  --results-file ~/.baldric/provider-validation/pi-api-provider-catalog/results.jsonl \
  --builtins-only
```

- `plan` 列出带凭据与无凭据的 provider 及每 provider 计划尝试数。
- `run` 以并发执行。`--builtins-only` 只加载打包目录。
  `--concurrency` 是每 provider 的并发请求；`--provider-concurrency`
  是并发 provider 数。`--max-retries 0` 让失败快速呈现而不是重试。
- `summarize` 聚合 `results.jsonl`：每 provider 的
  ok/failed、每个失败尝试的模型/级别/状态码/消息，加总尝试数。

## 脚本发现

迭代期间脚本暴露了：

1. **打包资源访问**：从安装的 wheel 里读取 `catalog.toml` 而非仅 checkout 路径。
2. **thinking 级别枚举**：对每个 provider/model 用公开 helper 而不是硬编码级别清单。
3. **Codex 授权标头**：Codex OAuth provider 需要官方客户端发送的 identity/originator headers。
4. **provider 并发**：按 provider 限制并发，避免 OpenRouter/DeepSeek 之类聚合器端到端串行化。

## 本次通过的结果摘要

针对 Pi 衍生目录的验证运行覆盖 20 个 provider 家族：

- 13,434 次成功请求；
- 1,717 次失败；
- 已修复问题：

  - `zai-org/GLM-5.2`：仅在支持处为 thinking 发送 `reasoning_effort`；`medium` 从该模型的 thinking 级别里移除。
  - Kimi K3：thinking 字段形状错误；模型仅支持 `low`/`high`/`max`。
  - DeepSeek：thinking 默认、`developer` role、`cacheWrite` 计价与明确的 token 上限。
  - MiniMax：兼容性形状、上下文窗口与-thinking 级别。
  - Gemini 3 Pro：仅接受 `high`/`low` reasoning effort；不支持 `minimal`/`medium`。

## 修复后的最终摘要

最后目录对有凭据 provider 有 1,193 次预期验证尝试。所有可修的模型/推理不匹配已清零。

剩余失败不是全局目录/运行时 bug：

- DeepSeek 对可用 API key 返回 `402 Insufficient Balance`。
- OpenAI Codex 对 `gpt-5.3-codex` 与 `gpt-5.2`（用已登录 ChatGPT 账户）返回账户权益错误，其他 Codex 模型正常。
- 若干 OpenRouter 免费/共享上游路由返回 `429` 限速。

无凭据 provider 本轮未做活动验证：Cerebras、Fireworks、
Mistral、Moonshot、Together、Vercel AI Gateway、xAI、Xiaomi、Z.ai 与地区变体。

最终本地项目验证：

```bash
uv run pytest -q
uv run ruff check .
uv run mypy
```

```text
677 passed
All checks passed!
Success: no issues found in 64 source files
```
