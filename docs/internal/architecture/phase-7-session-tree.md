---
title: "Phase 7：session 树与 JSONL 持久化"
---

Phase 7 加了 Baldric 第一个持久 session 层。

session 原语位于：

```text
src/baldric_agent/session/
```

## 加了什么

Baldric 现在有：

- 类型化的 append-only session entry
- JSONL 序列化 helper
- 本地 JSONL session 存储
- 内存 session 回放
- 分支路径遍历 helper

## session 为什么是 append-only 的

Baldric 遵循 Pi 的核心 session 思想：持久状态不就地编辑。Baldric 改为追加不可变 entry 并通过回放重建当前视图。

这让 session 文件：

- 易于检视
- 易于安全追加
- 适合日后分支/fork
- 即使 compaction 或摘要落地后也能保留历史

session 文件一行一个 JSON 对象：

```jsonl
{"type":"message","id":"...","message":{"role":"user","content":"Hello"}}
{"type":"message","id":"...","parent_id":"...","message":{"role":"assistant","content":"Hi"}}
{"type":"label","id":"...","parent_id":"...","target_id":"...","label":"Greeting"}
```

## entry 类型

Phase 7 定义这些 entry：

- `message`
- `model_change`
- `thinking_level_change`
- `compaction`
- `branch_summary`
- `label`
- `leaf`
- `session_info`
- `custom`

部分 entry（如 `compaction` 与 `branch_summary`）是后续阶段的占位。Phase 22 让 `compaction` 回放感知，同时保留 append-only session 文件。

## JSONL 存储

`JsonlSessionStorage` 提供第一个本地存储 backend：

```python
from baldric_agent.session import JsonlSessionStorage, MessageEntry
from baldric_agent import UserMessage

storage = JsonlSessionStorage("session.jsonl")
await storage.append(MessageEntry(message=UserMessage(content="Hello")))
entries = await storage.read_all()
```

缺失文件读作空 session。追加时自动创建父目录。

## 回放

`SessionState.from_entries()` 重建内存状态：

```python
from baldric_agent.session import SessionState

state = SessionState.from_entries(entries)
```

重建的状态包括：

- transcript 消息
- 活动模型
- thinking 级别
- 解析出的每 entry 标签及其最近变更时间戳
- 活动叶 id
- session 信息
- 自定义 entry

## 树路径

每个 entry 有：

```python
id: str
parent_id: str | None
```

这给了 Baldric 足够的分支重建结构：

```python
state = SessionState.from_entries(entries, leaf_id="entry-id")
```

提供 `leaf_id` 时只回放根到叶路径。这防止兄弟分支泄漏进活动 transcript。

## 边界

session 层住在 `baldric_agent`，因为它是可复用 agent 大脑的一部分。它不知道 CLI 参数、Textual 组件、Rich 渲染、slash 命令或本地 Baldric 资源目录。

后续的 `baldric_coding` session 包装将决定何时追加 entry、session 文件存哪里、`/sessions` 或 `/fork` 之类的命令如何表现。

## 测试

本阶段覆盖于：

```text
tests/test_session.py
```

测试验证：

- entry JSONL 往返
- 畸形 JSONL 错误
- 追加/读取存储行为
- 缺失文件行为
- 线性状态回放
- 分支路径重建
- 缺失父节点校验

## 下一阶段

路线图下一阶段是 Baldric coding session 包装。那层可以在这条 append-only 基础之上组合 session 持久化、slash 命令、prompt 展开、资源与 print/交互 frontend。
