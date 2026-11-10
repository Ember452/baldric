---
title: "extension 化之前的加固摘要"
---

本笔记总结 Phase 21 extension 之前完成的生产加固。Phase 21 仍被有意推迟。

## agent 与 provider 运行时

Baldric 现在有 provider 中立的进展事件：重试、thinking/reasoning
delta、排队 prompt 状态：

- `RetryEvent` 报告 provider 重试尝试，不向 frontend 暴露 provider 特定的
  HTTP 细节。
- `ThinkingDeltaEvent` 携带可选的流式 provider 推理文本，不把它记录为持久的 assistant 消息。
- `QueueUpdateEvent` 为 frontend 状态显示携带待处理的 steering 与 follow-up prompt 文本。

OpenAI 兼容、Anthropic 与 OpenAI Codex 订阅 provider 对瞬时 transport 失败重试，然后才发出最终 provider 错误。重试策略经 provider 设置与环境变量可配置。

凭据解析是显式的：对带 `credential_name` 的 provider，`~/.baldric/credentials.json` 的 Baldric 已存凭据
优先于环境变量回退。

## context、skill 与 session

context 计量现在返回结构化 `ContextUsageEstimate`，含总量、
system、消息与工具 token 估算。TUI 从事件流刷新，侧栏与紧凑 session 的 context 数字因此在用户消息、assistant 响应、工具结果、compaction 及 resume/new-session 流程后更新。

已加载 skill 经两条路径可用：

- system prompt 列出 skill 名、描述与文件位置，模型可用普通 `read` 工具读相关 skill 文件
- `/skill:<name> [request]` 把完整 skill markdown 展开进下一条 prompt

session 导出经 `baldric export` 可用。它为已索引 session id 或 JSONL session 路径写一个自包含 HTML 视图，同时保留
session 树结构与存储顺序 transcript。

## TUI 行为

Textual frontend 留在适配器边界之后：

```text
CodingSession emits AgentEvent values
        ↓
TuiEventAdapter updates TuiState
        ↓
Textual widgets render transcript, status, and controls
```

近期 TUI 加固增加了：

- 响应式侧栏，含 provider/model、thinking mode、tools、skills、
  prompt templates 与 context 文件
- 流式用户、assistant、工具、compaction 与 resume 事件后的 context 大小刷新
- 可见 transcript 输出的 Textual 文本选择
- `Alt-Up` / `Alt-Down` 选择消息
- `Ctrl-C` 复制选中消息
- `Ctrl-O` 内联展开工具结果
- agent 运行活动时的动画活动状态
- `Shift-Tab` 轮换 thinking mode
- `Ctrl-T` 可选 thinking token 显示（默认隐藏）
- 运行中 `Enter` 排队 steering
- 运行中 `Alt-Enter` 排队 follow-up

排队 prompt 首次入队时不持久化。只有当 `AgentHarness` 把它们注入活动运行并发出正常用户消息事件时，才成为持久 session 消息。

## 架构边界

新增行为保持 Baldric 的包切分：

- `baldric_ai` 拥有 provider 特定的重试、token 与流解析。
- `baldric_agent` 拥有可移植消息、事件、循环协调、harness 状态、
  队列语义、工具与 session 原语。
- `baldric_coding` 拥有 provider 配置、凭据、资源、命令、
  持久化流程、文档与 Textual UI 政策。

可复用 agent 包仍不导入 Textual、Rich 渲染、Typer、
本地配置路径、slash 命令注册表或项目资源加载。

## 验证

加固片由跨下列文件的聚焦测试覆盖：

```text
tests/test_agent_harness.py
tests/test_agent_loop.py
tests/test_coding_session.py
tests/test_context_window.py
tests/test_provider_config.py
tests/test_rendering.py
tests/test_session_export.py
tests/test_skills.py
tests/test_baldric_ai.py
tests/test_tui_adapter.py
tests/test_tui_app.py
tests/test_tui_config.py
```

合并最后的 extension 化之前变更前，全量门通过：

```bash
uv run pytest
uv run ruff check .
uv run mypy
```
