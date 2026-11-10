---
title: "01 — 架构"
---

Baldric 把可复用的 agent 内核与编码 agent 应用、以及任何 UI 分开。

## 层

### `baldric_ai`

拥有 provider 特定的模型流式。它把 provider 响应翻译为 Baldric 的 provider 中立事件。

### `baldric_agent`

拥有可移植的 agent 大脑：消息、工具、事件、agent loop、harness 与 session 原语。
这个包不得导入 CLI、Rich、Textual 或应用资源加载代码。

### `baldric_coding`

拥有编码 agent 应用：CLI 命令、内置编码工具、项目指令、skill、
prompt template、磁盘上的 session 与 UI 适配器。

## 依赖方向

```text
baldric_coding -> baldric_agent -> baldric_ai
```

UI 包消费已发出的事件。内核不直接渲染 UI。

## 指导性切分

```text
AgentHarness = reusable brain
AgentSession = coding-agent environment
TUI = one possible frontend
```
