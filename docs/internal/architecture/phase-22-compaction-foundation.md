---
title: "Phase 22：compaction 回放基础"
---

本阶段启动 Baldric 的 compaction 与 context 管理工作。现已包含
模型驱动的 Pi 式摘要、自动 compaction 的近期 context 保留，以及溢出触发的重试行为。

实现位于：

```text
src/baldric_agent/session/entries.py
src/baldric_agent/session/memory.py
src/baldric_coding/context_window.py
src/baldric_coding/session.py
src/baldric_coding/commands.py
```

## 加了什么

`CompactionEntry` 现在在 session 回放中有意义。

`SessionState.from_entries()` 遇到现代 compaction entry 时：

1. 插入一条 provider 中立的摘要消息
2. 在完整的活动根到叶 entry 路径上找到 `first_kept_entry_id`
3. 按路径顺序保留该边界及其后的产生 context 的 entry
4. 原始 append-only entry 保持完好

这匹配 Pi 的含首保留语义。边界缺失或找不到时，回放不保留
compaction 前的消息，但仍包含后续后继者。此编码之前写入的 Baldric session 用 `replaces_entry_ids`；非空 legacy
清单优先，保留原本的任意集合回放行为。

摘要消息目前使用这个稳定形式：

```text
Previous conversation summary:
<summary>
```

## 为什么存在

Baldric 需要 compaction 来缩减活动的 provider context，同时保留
完整 session 文件。这保持 Pi 的 append-only session 性质：

```text
session file = durable history
SessionState.messages = reconstructed active context
```

手动 `/compact` 可以追加 `CompactionEntry` 而不编辑或
删除旧 entry。新记录持久化一条 first-kept 边界，而不是所有被总结 entry id 的清单。

## context 大小估算

Baldric 现在在 `baldric_coding` 有确定性的近似 context 大小 helper：

```python
estimate_text_tokens(...)
estimate_message_tokens(...)
estimate_tool_tokens(...)
estimate_context_tokens(...)
```

这些 helper 有意用粗略的按字符估算而不是 provider 专属分词器。`/status` 以如下形式呈现当前估算：

```text
Estimated context tokens: <count>
```

这给自动 compaction 阈值一个稳定的应用层原语，而不把分词器政策加进 `baldric_agent`。

Baldric 默认启用 Pi 式自动 compaction，用：

```text
model context window - 16384 reserve tokens
```

内置模型带配置的 context window 元数据，未知/自定义
模型回退到 `128000` token 窗口。可以为一次运行覆盖阈值：

```bash
baldric --auto-compact-threshold 100000
```

新 prompt 之前或模型响应之后，活动 context 估算超过生效阈值时，Baldric 请活动 provider 做结构化摘要、
追加 `CompactionEntry` 并重建内存 transcript。看起来像
context 溢出的 provider 错误之后，Baldric 还会尝试一轮 compact-and-retry。

## 手动 compaction

Baldric 现在在 TUI 支持模型生成的手动 compaction：

```text
/compact [instructions]
```

命令使用 Baldric 内置的 Pi 风格 compaction prompt。可选
指令作为额外焦点追加到该 prompt。生成的摘要存进
`CompactionEntry`，它成为活动的文件顺序尖。Baldric 随后
回放 session 并为后续轮次替换内存 harness transcript。

当前 prompt、触发条件与已知限制见 [Context Compaction](../context-compaction.md)。

## 边界

这块基础在 `baldric_agent`，因为回放 session entry 是可移植
harness 的事务。它不知道 slash 命令、Textual、Rich、
Baldric home 路径、token 阈值或哪个模型创建摘要。

token 估算、摘要生成、溢出分类与命令 UX
住在 `baldric_coding`。

## 测试

本阶段覆盖于：

```text
tests/test_session.py
tests/test_context_window.py
tests/test_commands.py
tests/test_coding_session.py
tests/test_tui_app.py
```

测试验证：

- compaction entry 经 JSONL 往返而不写空的 legacy id 清单
- 线性回放含首保留第一个边界 entry 并处理每种边界深度
- 分支回放只在活动分支路径应用 compaction
- 基于 fixture 的 legacy 回放保留替换清单优先级
- context 大小估算确定性
- `/status` 含估算的 context token 数
- `/compact [instructions]` 请求模型生成的 compaction
- 手动 compaction 持久化 entry 并重建后续轮次 context
- 选择加入的自动 compaction 在超阈值时于 prompt 前与响应后运行
- 溢出触发的 compaction 在可能时重试一次 provider 调用
