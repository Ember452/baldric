---
title: "Phase 24：session 树分支"
---

本阶段把 Baldric 既有的 append-only session 树暴露在 Textual TUI 里。
它遵循 Pi 的核心行为：在树上移动是结构性的 session
变更，不是 transcript 编辑。

## 变更了什么

`/tree` 为活动 session 打开弹窗树 picker。picker 把每个
分支的 entry 保持在一起，以历史最长的 child 为主分支。更短的替代分支紧跟其父节点、
在分支点缩进显示，然后未缩进的主历史继续。它
标记活动叶并支持两个动作：

- `Enter` 把活动叶移到所选 entry。
- `S` 经一条新的 `branch_summary` entry 移动活动叶。
- `Ctrl+T` 切换 tool-call entry 的显示，方便在工具密集的历史里导航。

两个动作都保留全部既有 JSONL entry。纯导航只在内存中。用户立即退出时，重开按文件顺序选择最后一条非 legacy 叶
entry，而不是还原那次未提交的选择。下一条消息或状态变更以所选目标为父追加，
因此让新分支持久化。摘要导航立即追加其
`branch_summary`，该摘要随即成为持久尖。picker 有意隐藏元数据 entry（模型变更、
thinking 级别变更、历史叶指针、session 信息）；只显示用户消息、assistant 消息、tool call、compaction 摘要与
分支摘要。

## 分支摘要

Baldric 本来就有 `BranchSummaryEntry` 类型。本阶段让它回放感知：
活动根到叶路径包含分支摘要时，`SessionState`
把它转换为用户 context 摘要消息。

分支摘要现在用活动 provider 与 model 总结所选 entry 之后的
活动路径消息。`CodingSession` 在主 `AgentHarness` transcript 之外发送一次性总结
请求，使用 Pi 风格的结构化摘要 prompt，含目标、约束、进展、决策与
后续步骤区块。TUI 同时支持默认 prompt 与每分支的自定义
焦点指令。Baldric 把结果文本存进既有
`BranchSummaryEntry` 形状。provider 返回不可用文本、报错或抛异常时，Baldric 回退到自动 compaction 使用的同一确定性摘要 helper。

## 边界

`baldric_agent.session` 拥有 `branch_summary` entry 的通用回放语义。
`baldric_coding.CodingSession` 拥有分支导航、模型摘要创建、
回退摘要创建、存储变更与 harness 消息替换。
Textual TUI 只显示选项并调用用户选定的 session 方法。

## 验证

有用的检查：

```bash
uv run pytest tests/test_session.py tests/test_coding_session.py tests/test_commands.py tests/test_tui_app.py -q
uv run ruff check src/baldric_agent/session/memory.py src/baldric_coding/session.py src/baldric_coding/commands.py src/baldric_coding/tui/app.py tests/test_session.py tests/test_coding_session.py tests/test_commands.py tests/test_tui_app.py
```
