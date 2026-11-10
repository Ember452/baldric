---
title: "00 — 路线图"
---

Baldric 作为 Pi 极简编码 agent harness 架构的 Python 实现来构建。
目标不是逐行移植；目标是沿用同样的边界，同时使用 Python 原生工具。

## 包分层

```text
baldric_ai       provider/model streaming layer
baldric_agent    portable agent harness, loop, tools, events, sessions
baldric_coding   CLI app, resources, skills, extensions, commands, UI integration
```

## 当前状态

Phase 0 到 20.4、22、23 已实现并记录。Phase 21
extension 曾被推迟到内核 harness、coding session 与 TUI 稳定之后；现在已实现（见 architecture/phase-21-extensions.md）。

最近一次 pre-extension 加固增加了 context 用量刷新、
thinking-mode 控制、可选 thinking token 显示、provider 重试、
凭据优先级、skill 调用可靠性、session 导出、transcript
选择/复制、活动状态，以及 Pi 式排队 steering/follow-up prompt。
当前行为与验证覆盖见 [Pre-extension Hardening Summary](./architecture/pre-extension-hardening.md)。

context compaction 现在使用 Pi 式的模型生成摘要，自动压缩时保留近期
context，并能以一次 compact-and-retry 从 context 溢出的 provider 错误中恢复。见
[Context Compaction](./context-compaction.md)。

项目信任的强制执行尚未实现。其文档优先的设计、
Pi 兼容性研究、资源矩阵、分阶段实施与测试计划记录在 [Project trust](./project-trust.md)（对应 issue #535）。

## 阶段计划

0. 项目地基与设计文档。
1. 核心消息、工具与事件类型。
2. 带 fake 与真实 provider 的 provider 接口。
3. 纯 agent loop。
4. 可复用的 `AgentHarness`。
5. 内置编码工具。
6. 非交互 print-mode CLI。
7. append-only session 树持久化。
8. 带命令的 coding session 包装。
9. skill 与 prompt template。
10. system prompt 组装。
11. print 与事件渲染模式。
12. 适配器边界之后的 Textual TUI。
13. Baldric home、路径与自动 `.agents` 资源。
14. session 管理器与恢复。
15. slash 命令注册表。
16. 健壮的 skill 与 prompt 发现。
17. TUI slash 命令补全。
18. provider 配置与 setup。
19. 项目 context 发现与重载。
20. 打包与安装打磨。
20.1. 精确的 context 计量与侧栏刷新。
20.2. thinking mode 控制。
20.3. skill 调用可靠性。
20.4. session 可视化与导出。
21. extension。已实现。
22. compaction 与 context 管理。
23. 高级 TUI 与产品打磨。

## Phase 0 交付物

Phase 0 创建文档、包脚手架、开发检查与一个基本的 `baldric --version` 命令。
