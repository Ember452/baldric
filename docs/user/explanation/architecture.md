---
title: 架构总览
description: Baldric 如何拆成四个包——以及为什么这条边界就是全部重点。
---

Baldric 刻意保持小而分层。最重要的设计思想是**边界**：可复用的 agent"大脑"对终端、文件路径、渲染一无所知。一切应用特定的东西都包裹在它外面。

## 四个包

```text
baldric.runtime  →  { baldric.agent, baldric.ai }  →  baldric.protocol
```

### `baldric.protocol` — 共享的 wire 契约

拥有其他所有层都要说的 provider 中立形状：消息与内容模型、tool 契约、provider 流事件，以及持久化的 session wire（entry 形状、树遍历、JSONL 格式）。它唯一的依赖是 pydantic——无 I/O、无平台代码、上面没有任何东西。第三方（provider 适配器、frontend、session 工具）可以只针对这个包构建。

### `baldric.ai` — 与模型对话

拥有 provider 特定的模型流式。它把每个 provider 的 API（OpenAI、Anthropic……）翻译成 Baldric 的 **provider 中立事件流**，这样它上面的任何东西都不必关心用的是哪家模型。

### `baldric.agent` — 可移植的大脑

拥有可复用的 agent 内核：[agent loop](/explanation/agent-loop/)、harness、事件发射与 tool 调用编排，全部构建在 `baldric.protocol` 契约之上。这个包**不得**导入 CLI、Rich、Textual 或资源加载代码——正是这一点让它可移植。

### `baldric.runtime` — 编码应用

拥有让 Baldric 成为一个*你能运行的编码 agent*的一切：CLI、内置[工具](/reference/tools/)、[项目指令](/how-to/project-instructions/)、[skill 与 prompt](/how-to/skills-and-prompts/)、[磁盘上的 session](/how-to/sessions/)、provider 配置，以及 Textual TUI。

### 本地后端边界

本地推理属于 `baldric.runtime`，不属于可移植的 agent 内核。一个分阶段的 extension runtime 在 provider registry 旁边拥有一个感知来源与世代的 local-backend registry。backend 返回类型化的配置、状态、进度、诊断与能力值；Textual 适配器渲染它们并拥有取消、确认与空闲检查。把每个 backend 与它确切来源的 provider 层配对，可以防止一个遮蔽性的 extension 使用或重置另一个来源的集成。见[本地后端指南](/how-to/local-inference/)。

Phase 6 用一个常驻的第二 fake backend 和一个仅测试用的 Ollama 适配器验证这条边界。provider 发现与 backend 状态可以使用不同端点，已安装/运行状态套进通用模型状态，`NoAuth` 不需要特判的 backend API。刷新取消是有界且世代安全的；迟到的任务无法在退役后发布。路由变更仍是后续阶段。

TUI 与 print 启动共享同一条信任感知的准备边界：加载受信任的 built-in 与合格的 extension、恢复安全的动态快照、解析显式的 provider/model，然后构建候选 runtime。因此一个已保存的 llama.cpp 快照可以在服务器宕机时支撑显式启动，而不把本地后端变成隐式回退。

## 依赖方向

依赖只指向一个方向：`baldric.runtime → {baldric.agent, baldric.ai} → baldric.protocol`，而 `baldric.protocol` 除 pydantic 外不依赖任何东西。UI 代码*消费*事件；内核永不向上伸手渲染任何东西。一行话说：

```text
AgentHarness = 可复用的大脑
CodingSession = 编码 agent 环境
TUI = 一种可能的 frontend
```

## 边界为什么重要

因为内核不含 UI，同一个 agent 可以驱动 print mode、Textual TUI，或你自己构建的 frontend——全都消费同一条事件流。这也是 Baldric 可读的原因：每一层回答一个问题，你可以不拆开其他层就研究它。

→ 下一站：[agent loop 与事件](/explanation/agent-loop/) ·
[设计原则](/explanation/design-principles/) ·
[构建你自己的 frontend](/explanation/custom-frontend/)

> [!NOTE] 想深入
> 逐阶段的构建日志、设计文档与 ADR 在仓库的 `docs/internal/` 里（不在本站上）。见[贡献](/contributing/)。
