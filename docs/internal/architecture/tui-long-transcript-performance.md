---
title: "有界的 TUI transcript 渲染"
---

Baldric 的 Textual transcript 现在保持一个有界窗口的挂载消息组件，而不是让 Textual DOM 随 session 里每条消息无限增长。

## 为什么存在

持久对话与 TUI 显示状态早已分离，但最初的
`TranscriptView` 为每个 `ChatItem` 挂载一棵 Textual 组件树。长 session 因此让无关交互变得昂贵：布局与刷新时 Textual 要遍历数千个消息泵，即使用户只是在 prompt 里打字。

完整 transcript 刷新更贵——它移除并重建每个消息组件。工具完成、结构化 thinking 响应、结果可见性切换与终端 resize 都可能走到那条路径。

## 架构

完整显示投影仍在 `TuiState.items`。`TranscriptView` 现在只挂载一段连续的
frontend 窗口：

```text
CodingSession / durable messages
              ↓
TuiState.items (complete display history)
              ↓
TranscriptView window (bounded Textual DOM)
```

初始挂载最近 80 项。更早或更晚的项在窗口之外时显示小的边界行。到达边界把窗口按更小的页移动，同时保留一条既有消息作为滚动锚。状态从不截断，session 持久化不变。

这刻意是 Textual 适配器优化。没有窗口化、渲染或组件策略加进
`baldric_agent` 或 `CodingSession`。

## 增量热路径

常见事件路径不再重建 transcript 历史：

- 工具完成更新既有工具行；
- 终端命令追加并完成一行；
- 最终有序 thinking/文本块只替换临时 assistant 尾部；
- thinking 与工具结果可见性只更新受影响的挂载行；
- 终端 resize 依赖 Textual 原生重排；
- transcript 项与 tool-call 查找用 frontend 索引而非反复扫描。

prompt 活动动画保持流畅，但固定尺寸动画帧跳过布局，工具耗时行每秒最多更新一次。

流式保持窗口小还有第二个原因：每次流式 Markdown 追加都触发一次遍历全部挂载组件的布局。性能剖析显示缩小窗口让长恢复 session 的流式帧率大致翻倍后，窗口从 200 降到 80 项。`TranscriptMarkdownStream` 还把追加限制为每
`STREAM_FLUSH_INTERVAL_SECONDS`（100 毫秒）一次，合并其间到达的增量，消息结束时立即冲刷待处理文本。

## 取舍

挂载窗口内，原生 Textual Markdown、选择、流式与每消息渲染保持完好。跨窗口移动会清除视口外组件，因此鼠标选择不能跨越翻页边界。继续滚动即可看到完整 transcript，导出/session 回放仍用完整持久历史。

## 验证

自动化测试覆盖：

- 有界挂载组件数且完整状态保留；
- 两个方向的 transcript 翻页；
- 滚动锚定与流式行为；
- 增量的工具、结构化 assistant、结果切换与 resize 更新；
- 限流的活动/计时器布局工作。

项目检查运行：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```
