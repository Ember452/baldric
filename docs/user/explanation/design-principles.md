---
title: 设计原则
description: 让 Baldric 保持小、可移植、可读的那几条规则。
---

Baldric 始终遵循几条原则。它们是代码库在增长时仍然平易近人的原因。

## 小分层胜过魔法

每个包只做一件事：`baldric.ai` 流式对接模型，`baldric.agent` 跑循环，`baldric.runtime` 是应用。你可以单独阅读和测试任何一层，不需要理解其他层。→ [架构](/explanation/architecture/)

## 事件即契约

agent 通过一串 provider 中立的事件流传达进展。frontend 从这些事件渲染，绝不从 provider 特定的分块或内部控制流渲染。这就是 print mode、TUI 与自定义 frontend 能共享同一内核的原因。→ [agent loop 与事件](/explanation/agent-loop/)

## 内核保持可移植

`baldric.agent` 不得依赖 Textual、Rich、CLI、配置目录、slash 命令或应用特定的资源。它们属于 `baldric.runtime`，从外部包裹内核。可复用的大脑永不向上伸手到一个 UI。

## 工具就是普通的类型化函数

一个 tool 就是一个名字、一段描述、一个 JSON 输入 schema 和一个返回结构化结果的异步执行器。没有框架魔法——这让工具易于阅读、测试和添加。→ [内置工具](/reference/tools/)

## session 持久且可检视

每段对话都是磁盘上一个 append-only 的 JSONL 转录。历史是一棵可以恢复和分支的树；compaction 只改变*活动* context，不重写记录。格式朴素到可以手工阅读。
→ [Sessions](/how-to/sessions/)

## 小的产品分歧是显式的

Baldric 大体遵循 [Pi](https://pi.dev) 的"agent 大脑 / coding session / frontend"极简分离。少数面向用户的便利点有意偏离这个基线。一个例子是自动 session 命名：Baldric 在第一条用户消息落盘后，请活动的 provider/model 起一个短标题，并存为 session 元数据。它留在 `baldric.runtime` 而不是可移植的 `baldric.agent` harness 里，因为它是应用工作流，不是 agent-loop 行为。

## 文档跟随实现

Baldric 以小而文档化的阶段构建，读者可以追溯系统如何长成。那些阶段笔记放在仓库的 `docs/internal/` 里（见[贡献](/contributing/)）；这些页面蒸馏结果。
