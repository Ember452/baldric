# Baldric 内部文档

这些是 Baldric 的内部构建日志、设计、决策与计划。
它们**不**发布在文档站点上。面向用户的文档在
`docs/user/`。

## 内容

- `adr/` - 架构决策记录，统一编号。
- `architecture/` - 逐阶段实施笔记与子系统日志。每篇回答：加了什么、
  为什么存在、后续阶段如何使用。
- `design/` - 实现前写下的设计，保留理由。
- `notes/` - 不属于某个 phase 的功能构建日志与调查。
- `plans/` - 可执行的工作计划。完成的计划要么沉淀为 `adr/` 里的
  决策，要么作为历史留在这里。
- `specs/` - 计划所实现的详细规格。

路线图记录在 [GitHub issue #2](https://github.com/Ember452/baldric/issues/2)。
文档规则见 [../AGENTS.md](../AGENTS.md)。
