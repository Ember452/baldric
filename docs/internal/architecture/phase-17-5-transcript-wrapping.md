---
title: "Phase 17.5：TUI transcript 换行"
---

Phase 17.5 加固 Textual transcript 表面，让它更像一个极简聊天栈。

实现位于：

```text
src/baldric_coding/tui/app.py
src/baldric_coding/tui/widgets.py
```

## 加了什么

transcript 项现在渲染为独立的色块，而不是 `you:`、`assistant:` 之类的前缀行。

显示状态保持简单：

```python
ChatItem(role="user", text="...")
```

只有 Textual 渲染器决定如何显示该项。核心边界得以保留：

```text
CodingSession emits events
TuiEventAdapter builds display state
TranscriptView renders blocks
```

## 换行行为

`TranscriptView` 现在是装着独立
`TranscriptMessageWidget` children 的 `VerticalScroll` 容器。容器保持：

```python
min_width = 1
```

每个消息组件拥有自己的 Rich renderable 与选中文本提取。这让普通用户与 assistant 消息按可用
终端宽度重排，同时避免一整张 transcript 级的大选择面。聊区块正文用带折叠溢出的 Rich `Text`，长串不断行文本在块内换行而不是强迫水平滚动。

工具输出与类代码文本保留换行。超长不断行的块被有意折叠而非裁剪。

后续 Phase 23 打磨保持同一显示状态形状，但在块内用 Rich renderable 渲染围栏代码块、edit patch 与 assistant Markdown。畸形或行内栅栏回退纯文本，transcript 内容不丢失。

## 视觉模型

每个角色有独立的深色块样式：

- user
- assistant
- tool
- status
- error

角色用颜色表达，不用行内标签。TUI 因此保持极简，transcript 结构仍可扫读。

## 测试

本阶段覆盖于：

```text
tests/test_tui_app.py
```

测试验证：

- 聊天项渲染不带 `you:`、`assistant:`、`tool:` 前缀
- 长不断行消息文本在窄控制台宽度内折叠
- 挂载的 transcript 使用窄 `min_width`
- 选中文本提取限定在单个消息组件或相邻消息组件内
