---
title: 什么是 Baldric？
description: Baldric 是一个运行在终端里的小而可读的编码 agent——也是一个展示编码 agent 如何构建的活例子。
type: doc
---

**Baldric 是一个运行在你终端里的编码 agent。** 你用平实的语言说出想做的事——"解释这个仓库"、"给解析器加测试"、"修复这个堆栈回溯"——Baldric 会读文件、跑命令、改代码来把它完成，并实时流式呈现它的工作。

它同时是两样东西：

- **一个你能用的工具。** 一个真正的终端编码 agent，有交互式界面、多个模型 provider、可以恢复和分支的持久 session，以及承载你自己的 skill 与 prompt 的资源系统。
- **一个你能读懂的项目。** Baldric 生来就是为了*被阅读*。它的源码被组织成小而诚实的层，让你看清编码 agent 的每个部分——从模型流式、到 agent loop、再到工具与 session。

## 它能做什么？

- 在你的项目里**读、写、编辑文件**并**运行 shell 命令**，同时与你对话。
- 以**交互式 TUI** 或**单条命令**（适合脚本与管道）两种方式工作。
- 对接 **OpenAI、Anthropic、OpenAI Codex、OpenRouter、Hugging Face** 或任何 OpenAI 兼容端点（包括本地模型）。
- **记住**每个 session，让你之后**恢复**它，并从任意更早的点**分支**去探索不同路径。
- 通过自动 **compaction** 在长 session 中保持可用，并在支持的模型上提供 **thinking mode**。
- 用你自己的 **skill**、**prompt template** 和项目级**指令**（`AGENTS.md`）扩展它自己。

## 它面向谁？

- **你想要一个能运行、能改造的编码 agent**——装上它、指定一个模型、开工。从[快速上手](/tutorials/quickstart/)开始。
- **你想弄懂编码 agent 是怎么造出来的**——读[核心概念](/explanation/concepts/)，然后是 [Baldric 如何工作](/explanation/architecture/)分区。

## 接下来去哪

- **[快速上手](/tutorials/quickstart/)**——安装 Baldric，几分钟内跑起第一个 session。
- **[核心概念](/explanation/concepts/)**——那几个一切都建立在其上的想法（agent loop、provider、tool、session、skill）。
- **[任务配方](/how-to/tui/)**——TUI、session、provider 等主题的实操指南。
- **[参考](/reference/cli/)**——确切的 CLI 命令、slash 命令与快捷键。
