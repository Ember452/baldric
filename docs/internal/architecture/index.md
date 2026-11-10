---
title: "架构笔记"
---

本节按构建顺序逐阶段解释 Baldric 的架构。

Baldric 刻意以小分层开发。每层应回答三个问题：

1. 加了什么？
2. 为什么存在？
3. 后续阶段如何使用它？

## 当前架构分层

```text
baldric_ai       provider/model streaming layer
baldric_agent    portable agent harness, loop, tools, events, sessions
baldric_coding   CLI app, resources, skills, extensions, commands, UI integration
```

最重要的边界是 `baldric_agent` 保持可移植。它可以定义可复用的 agent 大脑，但不该知道 VS Code、Textual、Rich 渲染、本地配置目录、slash 命令或项目专属 prompt。

实用 frontend 契约见 [Building a Custom TUI](../custom-tui.md)。

项目增长时新代码应去哪里，见
[Target project layout](./target-project-layout.md)。那份笔记是蓝图，不是
当前树的描述；与它不符的代码并不因此就是错的。

## 阶段笔记

- [Phase 1: Core Types and Events](./phase-1-core-types-and-events.md)
- [Phase 2: AI Provider Layer](./phase-2-ai-provider-layer.md)
- [Phase 3: Pure Agent Loop](./phase-3-agent-loop.md)
- [Phase 4: AgentHarness](./phase-4-agent-harness.md)
- [Phase 5: Built-in Coding Tools](./phase-5-coding-tools.md)
- [read 工具的多模态结果](./multimodal-read-results.md)
- [有界 read 图片处理](./read-image-processing.md)
- [Phase 6: 非交互 print-mode CLI](./phase-6-print-mode-cli.md)
- [Phase 7: session 树与 JSONL 持久化](./phase-7-session-tree.md)
- [Phase 8: Coding Session 包装](./phase-8-coding-session.md)
- [Phase 9: skill 与 prompt template](./phase-9-skills-prompts.md)
- [Phase 10: system prompt 组装](./phase-10-system-prompt.md)
- [Phase 11: print 与事件渲染模式](./phase-11-print-event-rendering.md)
- [Phase 12: Textual TUI](./phase-12-textual-tui.md)
- [Phase 13: Baldric home、路径与 `.agents` 资源](./phase-13-paths-agents-resources.md)
- [Phase 14: session 管理器与恢复](./phase-14-session-manager-resume.md)
- [Phase 15: slash 命令注册表](./phase-15-slash-command-registry.md)
- [Phase 16: 健壮的资源发现](./phase-16-resource-discovery.md)
- [Phase 17: TUI slash 命令补全](./phase-17-tui-autocomplete.md)
- [Phase 17.5: TUI transcript 换行](./phase-17-5-transcript-wrapping.md)
- [Phase 18: provider 配置基础](./phase-18-provider-config-foundation.md)
- [配置驱动的 provider 目录](./config-driven-provider-catalog.md)
- [Codex 运行时模型限制](./codex-runtime-model-limits.md)
- [provider 重试事件](./provider-retries.md)
- [provider/模型安全与 HTTP 错误详情](./provider-model-safety.md)
- [Phase 19: 项目 context 发现与重载](./phase-19-context-discovery.md)
- [Phase 20: 安装与配置文档](./phase-20-installation-docs.md)
- [Phase 20.1: context 计量刷新](./phase-20-1-context-accounting.md)
- [Phase 20.2: thinking mode 控制](./phase-20-2-thinking-controls.md)
- [Phase 20.3: skill 调用可靠性](./phase-20-3-skill-invocation.md)
- [Phase 20.4: session 导出与可视化](./phase-20-4-session-export.md)
- [排队的 steering 与 follow-up](./queued-steering-follow-ups.md)
- [extension 化之前的加固摘要](./pre-extension-hardening.md)
- [Phase 21: extensions](./phase-21-extensions.md)
- [受信任的隐藏内置 extension](./trusted-built-in-extensions.md)
- [Phase 6: 本地推理加固与第二 backend 验证](./phase-6-local-inference-hardening.md)
- [extension 安装器](./extension-installer.md)
- [Phase 22: compaction 回放基础](./phase-22-compaction-foundation.md)
- [Phase 23: 高级 TUI 与产品打磨](./phase-23-tui-polish.md)
- [有界的 TUI transcript 渲染](./tui-long-transcript-performance.md)
- [Phase 24: session 树分支](./phase-24-session-tree-branching.md)
- [wire 契约基线](./wire-contract-baselines.md)
- [被截断的响应绝不执行 tool call](./truncated-tool-calls.md)
- [能打断停滞流的取消](./cancellation.md)
- [session 持久性：撕裂行与原子写入](./session-durability.md)
- [provider 重试策略](./provider-retry-policy.md)
- [契约债务：没有生产者或消费者的字段](./contract-debt.md)
- [流式 tool-call 参数](./tool-call-deltas.md)
- [context 与成本：现状](./context-and-cost-status.md)
- [推迟的可靠性决策](./deferred-decisions.md)
- [大文件拆解：拆了什么，没拆什么](./large-file-decomposition.md)
- [审计跟进 2026-11：改了什么，还有什么开放](./audit-followups-2026-11.md)

Phase 21 extension 已实现；见阶段笔记与用户指南
`docs/user/how-to/extensions.md`。
