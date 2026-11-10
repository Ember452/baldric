---
title: "Phase 18：provider 配置基础"
---

本阶段启动 Baldric 的持久 provider 配置工作，不加 extension 系统。

实现位于：

```text
src/baldric_coding/provider_config.py
src/baldric_coding/cli.py
src/baldric_coding/tui/app.py
src/baldric_coding/commands.py
src/baldric_coding/session.py
```

## 加了什么

Baldric 现在在 `baldric_coding` 下有 provider 设置模型：

```python
ProviderSettings
OpenAICompatibleProviderConfig
ProviderSelection
```

设置存放在：

```text
~/.baldric/providers.json
```

该文件不存在时，Baldric 使用 OpenAI 兼容默认：

```text
provider: openai
model: gpt-4.1-mini
api key env var: OPENAI_API_KEY
base URL env var: OPENAI_BASE_URL
timeout env var: OPENAI_TIMEOUT_SECONDS
retry env vars: OPENAI_MAX_RETRIES, OPENAI_MAX_RETRY_DELAY_SECONDS
```

API key 不存在配置文件里。内置 provider 用
`credential_name` 从 `~/.baldric/credentials.json` 读 key；没有凭据名的自定义 provider 读 `api_key_env` 指名的环境变量。

## 配置示例

```json
{
  "default_provider": "local",
  "providers": [
    {
      "name": "local",
      "type": "openai-compatible",
      "base_url": "http://localhost:11434/v1",
      "api_key_env": "LOCAL_API_KEY",
      "models": ["qwen", "llama"],
      "default_model": "qwen",
      "timeout_seconds": 120,
      "max_retries": 2,
      "max_retry_delay_seconds": 0.5
    }
  ]
}
```

## 运行时解析

print mode 与 TUI 启动现在从持久设置解析 provider/model 选择：

```text
baldric --provider local --model qwen
baldric -p "review this" --provider local
```

`--model` 省略时，Baldric 用配置 provider 的默认模型。
`--provider` 省略时，Baldric 用 `default_provider`。

## CLI 命令

Baldric 可以列出已配置 provider：

```text
baldric providers
```

Baldric 还可以创建或更新 OpenAI 兼容 provider 条目：

```text
baldric --provider local \
  --base-url http://localhost:11434/v1 \
  --api-key-env LOCAL_API_KEY \
  --timeout-seconds 120 \
  --max-retries 2 \
  --max-retry-delay-seconds 0.5 \
  --model qwen \
  setup
```

setup 选项是 `setup` 命令词之前的顶层选项。这既保留了
Pi 风格的 `baldric "prompt"` 形式（带初始 prompt 启动 TUI），又加了一条轻量 setup 流程。setup 只写 provider
元数据；对自定义 provider，指名的 API key 环境变量当前未设置时发出警告。

provider HTTP 超时经 `~/.baldric/providers.json` 的 `timeout_seconds` 可配置。默认 OpenAI 兼容 provider 还可读
`OPENAI_TIMEOUT_SECONDS`。配置值传给 HTTPX 流式客户端，超时行为不再硬编码在 provider 适配器里。

瞬时重试行为经 `max_retries` 与
`max_retry_delay_seconds` 可配置；默认 provider 也可用 `OPENAI_MAX_RETRIES` 与
`OPENAI_MAX_RETRY_DELAY_SECONDS`。Baldric 对 429、5xx 响应等瞬时 HTTP 状态重试，在任何部分流内容发出之前还对 HTTP transport 错误重试。

## slash 命令

slash 命令暴露活动模型配置：

```text
/model
/model <name>
/login
```

活动 provider 已知该模型时，`/model <name>` 为运行中进程的后续轮次切换活动模型。

TUI 里，`/model` 打开交互 picker。picker 可以包含每个已配置 provider 的模型，选择模型可以在幕后切换活动 provider。model 命令在校验或显示选项前刷新 provider 设置。`/login` 是添加或刷新内置 provider 的 TUI 路径，凭据保存后它会刷新 provider 设置。

同一份 provider 设置文件还可以存 scoped model：

```json
{
  "scoped_models": [
    {"provider": "openai", "model": "gpt-5.5"},
    {"provider": "local", "model": "qwen"}
  ]
}
```

Baldric 把它们当作 TUI 收藏。coding session 在暴露前先对照当前可用 provider 过滤存储列表，过期条目在 JSON 文件里保持无害。这镜像 Pi 的 scoped-model 思路，同时把持久配置留在 `baldric_coding`、可复用 harness 不知 provider 设置。

## 边界

provider 设置属于 `baldric_coding`，不属于 `baldric_agent`。

可复用 harness 仍只收到就绪的 `ModelProvider` 与模型名。它不知道 Baldric home、JSON 配置文件、凭据、
环境变量或 CLI/TUI setup 行为。

## 限制

Phase 18 刻意让 setup 保持最小。provider 元数据经 CLI setup 命令编辑，不是交互式 TUI 表单。后续登录工作为内置 provider API key 加了
`~/.baldric/credentials.json`；自定义 provider 在 Baldric 有自定义 provider 凭据表单之前仍用环境变量。

## 测试

本阶段覆盖于：

```text
tests/test_provider_config.py
tests/test_cli.py
tests/test_commands.py
tests/test_tui_app.py
```

测试验证：

- 缺失配置回退 OpenAI 兼容默认
- provider 设置经 `~/.baldric/providers.json` 往返
- provider setup 与列表 CLI 行为
- provider HTTP 超时与重试解析加运行时配置转发
- 默认 provider/model 选择
- 配置的 API key 环境变量与已存凭据
- CLI 的 provider/model 转发
- TUI 启动选择
- `/login` 与 `/model` 命令行为
