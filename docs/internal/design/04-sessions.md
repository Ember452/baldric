---
title: "04 — Sessions"
---

session 跨运行保存对话与 agent 状态。

## 设计

Baldric 使用 append-only 的 session 树。不改写旧状态，而是追加 entry 并通过回放重建状态。

底层实现位于：

```text
src/baldric_agent/session/
```

## entry 类型

- `message`
- `model_change`
- `thinking_level_change`
- `compaction`
- `branch_summary`
- `label`
- `leaf`（仅为 legacy 读取兼容；从不写入）
- `session_info`
- `custom`

## 当前能力

Baldric 现在可以：

- 把 session entry 序列化/反序列化为 JSONL
- 向本地 session 文件追加 entry
- 按序读取 session 文件
- 重建线性 session 状态
- 重建从根到叶的分支路径
- 载入恢复消息并持久化新运行的 `baldric_coding.CodingSession`

## 持久消息边界

`CodingSession` 把 `MessageEndEvent` 视为持久消息边界。持久化是推送式的：coding session 向 harness 订阅一个监听器，每条 `message_end` 通知在该事件到达消费 frontend 之前就把该消息追加进存储。持久化不在事件消费者里运行，所以停止消费的 frontend（TUI 在 Esc 时取消其 worker）不可能丢写——包括 harness 在取消清理期间追加并推给订阅者的合成"Tool call interrupted by user"结果。

这与 Pi 的 session 模型一致，对交互式 UI 很要紧：

- assistant 还在回复时，第一条用户 prompt 已可分支
- 排队的 steering 与 follow-up 消息在注入时变为持久
- 取消或进程失败保住已完成的消息
- TUI 能读到与活动运行一致的树状态

`message_end` 从未触发的消息刻意不持久化：在第一条完成消息前放弃运行不留持久痕迹，被中止的首条 prompt 不会索引出新 session。

活动尖是文件顺序中最后一条非 `leaf` entry。每条新 entry 指向当前内存中的尖，因此一次追加既记录操作又使其分支成为活动分支。历史 `leaf` entry 仍可反序列化，但不参与尖选择。

空 session 仍然延迟创建：加载新 session 在内存里准备初始元数据，但 Baldric 直到第一条持久 session entry 追加才创建 transcript 文件。第一次追加在写入消息之前，先物化待处理的 `session_info`、model 与 thinking-level entry。

## system prompt 持久化

Baldric 目前不把已解析的 system prompt 持久化进 session JSONL 文件。

恢复的 session 从 append-only session 文件还原已保存的对话分支、模型变更、thinking 级别变更、compaction、分支摘要、标签与自定义 entry。system prompt 在加载时从当前 coding-agent 配置与资源重建，包括当前 cwd、tools、已加载 skill、`AGENTS.md` 之类 context 文件，以及任何自定义或追加的 system prompt 设置。

这意味着 `/resume` 应理解为：

```text
saved conversation branch
+
current resolved system prompt
```

而不是：

```text
saved conversation branch
+
original system prompt snapshot from session creation
```

session 创建之后 system prompt 输入发生变化，被恢复 session 的后续轮次可能以与早前轮次不同的 system prompt 运行。当 session 应该跟上改进的 Baldric 指令、更新的项目 context、变化的 skill 或变化的工具指引时，这是有用的。代价是 JSONL 文件不是"每个历史轮确切发送了什么 prompt 文本"的完整审计快照。

这与 Pi 的当前行为一致。Pi 的 JSONL session schema 存对话树与 session 状态 entry，但不存专门的已解析 system prompt entry。Pi 在创建或恢复 agent session 时从活动资源加载器重建其基底 system prompt。Pi 在某些 UI/导出路径可以显示/导出当前运行时 system prompt，但那个 prompt 来自活动的 agent 状态，不是持久化的 JSONL 快照。

Baldric 未来可以增加显式的元数据 entry，存放已解析 system prompt 快照或 system prompt 修订。若加入，它很可能应保持为 session 元数据而非普通可分支的 transcript 消息，因为 harness 把 system prompt 与用户、assistant、工具消息分开对待。

## 边界

底层 session 原语属于 `baldric_agent`。文件位置、slash 命令与编码 agent 工作流属于 `baldric_coding`。

`CodingSession` 是底层原语之上的第一个 `baldric_coding` 层。它把存储、`AgentHarness`、cwd 与编码工具接在一起，把更丰富的命令与资源加载留给后续阶段。
