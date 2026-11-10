# provider/模型安全与 HTTP 错误详情

Issue #226 与 PR #249 修复的 provider/model 错配相重叠：`/tree`
导航现在保留活动 runtime 模型，而不是只回放所选分支的历史模型。本笔记记录其后追加的加固。

## 变更了什么

- 在 print mode、TUI 启动、模型切换、provider 刷新或运行时 provider 构建进行之前，provider/model 选择现在先校验所选模型确实由所选 provider 声明。
- 持久化的旧 `model_change` entry 与活动 provider 不再匹配的 session，回退到当前 provider 配置的默认，而不是构建错配的运行时 provider。
- TUI resume 启发式只在 provider 当前可用时才从已存模型推断 provider，因此同名模型的不可用 provider 不能侥幸胜出。
- OpenAI 兼容、OpenAI Codex 与 Anthropic 的 HTTP 错误现在共享一个 helper：从 JSON 响应体提取有用的 provider 错误详情，把 HTTP 状态与所选模型放进用户可见的 provider 错误消息。

## 为什么存在

Baldric 的 provider 目录刻意 provider 特定：`openai` API key provider 与 `openai-codex` 订阅 provider 是不同的 transport，可能不支持相同模型。对照活动 provider 校验模型，把非法组合变成立即的、可执行的配置错误。

共享的 HTTP 错误格式化器让生产失败在 provider 因账户、模型可用性、请求形状或其他校验原因拒绝请求时仍可调试。coding-session 诊断日志已经为不可恢复的 provider
错误记录 provider 名、模型、状态与安全响应体。

## 怎么测试

```bash
uv run pytest tests/test_provider_config.py tests/test_provider_runtime.py \
  tests/test_baldric_ai.py tests/test_coding_session.py tests/test_tui_app.py
```

合并前跑全量：

```bash
uv run ruff check
uv run pytest
```
