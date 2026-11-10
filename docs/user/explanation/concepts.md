---
title: 核心概念
description: Baldric 背后的几个核心想法——agent、provider、tool、session、skill、context 与 thinking。
type: doc
---

Baldric 由一小组概念构成。理解了它们，其余文档（以及 agent 本身）都会变得好懂。

## agent loop

当你发送一个 prompt，Baldric 会运行一个 **agent loop**：它请模型给出回复并流式接收；当模型请求使用 **tool** 时，Baldric 执行工具、把结果喂回去、请模型继续——如此往复，直到模型不再请求任何东西。这个循环是每个编码 agent 的心脏。
→ [Baldric 如何工作：agent loop](/explanation/agent-loop/)

## provider 与 model

**provider** 是托管 AI 模型的服务（OpenAI、Anthropic、OpenAI Codex、OpenRouter、Hugging Face，或任何 OpenAI 兼容端点）。**model** 是你对话的那个具体大脑（如 `gpt-5.5`、`claude-sonnet-4-6`）。你选择 provider + model，并且可以在会话中途切换。
→ [Providers & models](/how-to/providers-and-models/)

## 工具（tool）

**工具**是 agent 能在你的项目里采取的动作。Baldric 内置四个：`read`、`write`、`edit` 和 `bash`。由模型决定何时调用；Baldric 在你的工作目录里执行它们并流式返回结果。
→ [工具参考](/reference/tools/)

## session

**session** 是一段持续对话加上 agent 在其中所做的一切。session 以 append-only 文件保存到磁盘，所以之后可以**恢复**它们。因为历史是一棵树，你还可以从任意更早的点**分支**，尝试不同方向，并把 session **导出**为 HTML 或 JSONL。
→ [Sessions](/how-to/sessions/)

## 项目指令（`AGENTS.md`）

一个 **`AGENTS.md`** 文件给 agent 关于*你的*项目的长期指令——约定、坑、怎么跑测试。Baldric 自动发现这些文件，并把它们折叠进 system prompt。
→ [项目指令](/how-to/project-instructions/)

## skill 与 prompt template

**skill** 是描述如何完成某个具体任务的 Markdown 文件；你用 `/skill:<name>` 调用它。**prompt template** 是可复用的 prompt，按名称触发（可带变量），不必重新打字。两者都可以放在用户级（所有项目）或项目级。
→ [Skills & prompt templates](/how-to/skills-and-prompts/)

## context 与 compaction

模型一次只能"看到"有限的文本——它的 **context window**。长 session 会把它填满。Baldric 估算用量并自动 **compact**：把较早的消息总结掉，让对话得以继续。你也可以用 `/compact` 手动压缩。
→ [管理 context](/how-to/context/)

## thinking mode

一些模型可以在回答前花额外精力"思考"。Baldric 暴露一个 **thinking mode**（off → minimal → low → medium → high → xhigh → max），可以在活动模型支持时切换，并可选择显示流式推理过程。
→ [管理 context](/how-to/context/#thinking-mode)

## 两种界面

Baldric 以**交互式 TUI**（默认）或 **print mode**（`-p`，单条非交互 prompt）运行。两者共享同一个 session 环境。
→ [交互式会话](/how-to/tui/) · [Print mode](/how-to/print-mode/)
