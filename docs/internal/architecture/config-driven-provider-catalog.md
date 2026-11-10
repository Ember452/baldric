---
title: "配置驱动的 provider 目录"
---

Issue: https://github.com/huggingface/tau/issues/238

## 变更了什么

Baldric 的内置 provider 目录现在是数据驱动的。provider 与模型元数据住在：

```text
src/baldric_coding/data/catalog.toml
```

运行时，Baldric 还可以叠加一份用户目录：

```text
~/.baldric/catalog.toml
```

叠加是可选的。它可以添加新 provider 或部分覆盖内置 provider。

provider 运行时偏好保持独立于：

```text
~/.baldric/providers.json
```

该文件现在存引用/偏好，如默认 provider、每 provider 默认模型、headers、超时/重试设置与 scoped model。
不再需要重复 provider 定义。

## 为什么存在

此变更前，加 provider 或更新模型清单需要改 Python 源码。即使变更只是元数据，provider 支持也是 PR 驱动的。把目录移到 TOML 让源码聚焦校验与运行时行为，同时让 provider 添加变小而可评审。

## 架构边界

实现留在 `baldric_coding`，因为目录加载使用 Baldric home
路径与应用专属的 provider 偏好。可复用的 `baldric_agent`
harness 仍只收到就绪的模型 provider 与模型名。`baldric_ai`
层保持聚焦 provider 中立的运行时适配器。

公开兼容面仍是
`baldric_coding.providers.catalog` 的 `ProviderCatalogEntry`。TOML 解析、校验与叠加行为
住在 `baldric_coding.providers.loader`。

## 目录形状

```toml
schema_version = 1

[[providers]]
name = "local-gateway"
display_name = "Local Gateway"
kind = "openai-compatible"
base_url = "http://localhost:11434/v1"
api_key_env = "LOCAL_GATEWAY_API_KEY"
credential_name = "local-gateway"
models = ["qwen-coder"]
default_model = "qwen-coder"
docs_url = "https://example.test/local-gateway"

[providers.context_windows]
qwen-coder = 64000
```

支持的 `kind` 值为 `openai-compatible`、`anthropic` 与
`openai-codex`。对用户自定义 provider，`openai-compatible` 是预期的首选路径。

## 叠加行为

当 `~/.baldric/catalog.toml` 定义与内置 provider 同 `name` 的 provider：

- 标量字段替换内置值
- `models` 先并用户模型再合并
- `context_windows` 合并
- `thinking_levels` 出现时 thinking 字段作为一组替换

Baldric 本阶段有意只支持用户级目录叠加。不读项目级目录文件，克隆仓库不可能悄悄重定向内置 provider 的 `base_url`。

## 运行时偏好

`~/.baldric/providers.json` 有意存运行时偏好，不存 provider
元数据：

```json
{
  "default_provider": "local-gateway",
  "provider_preferences": {
    "local-gateway": {
      "default_model": "qwen-coder",
      "headers": {},
      "timeout_seconds": 60,
      "max_retries": 2,
      "max_retry_delay_seconds": 1
    }
  },
  "scoped_models": []
}
```

带完整 `providers` 条目的旧 `providers.json` 仍被接受。
Baldric 再次保存设置时，自定义 provider 定义写入
`~/.baldric/catalog.toml`，`providers.json` 被改写为仅偏好形状。

## 校验

目录文件以 `CatalogError` 尽早失败。Baldric 拒绝未知键、空必填字符串、空模型名、不支持的 provider kind、不在 `models` 清单里的默认模型、指向未知模型的
`thinking_models` 或 `context_windows` 条目，以及非正数或非整数的 context window 值。

## 怎么测试

```bash
uv run pytest tests/test_provider_catalog.py
uv run pytest tests/test_provider_config.py
uv run ruff check .
uv run mypy
```

目录测试覆盖内置加载、打包资源访问、用户自定义
provider、内置叠加、非法目录，以及 `providers.json` 已存在时与
`ProviderSettings` 的集成。
