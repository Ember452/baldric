---
title: "Phase 20.4：session 导出与可视化"
---

Phase 20.4 增加在 TUI 之外检视 Baldric session 的持久方式。

## 加了什么

Baldric 可以把任何已索引 session id 或 JSONL session 文件导出为独立
HTML 文档：

```bash
baldric export <session-id>
baldric export <session-id> session.html
baldric export <session-id> --format jsonl
baldric export ~/.baldric/sessions/<project>/<session-id>.jsonl
```

未提供目标时，`baldric export` 写到当前工作
目录而不是 Baldric 内部 session 存储目录。交互式 session 经以下命令暴露同一导出流程：

```text
/export [--format html|jsonl] [destination]
```

导出包含两个协同视图：

- 保留父子关系、分支、叶
  指针与活动分支路径的 session 树
- 按存储顺序的消息/详情视图：消息、tool call、工具结果、compaction、标签、模型变更、thinking 变更与自定义
  entry

生成的文件自包含 HTML、CSS 与 JavaScript，不需要运行 Baldric 或 Textual 应用即可打开。transcript entry 渲染为紧凑折叠的手风琴行（图标、标题、单行预览、时间戳），
thinking 块、tool call 参数与结果细节嵌套为内层手风琴。工具行标题为 `Tool: <name>`，session 树为可读性只用工具名标注工具 entry。芯片式头部
过滤器带 entry 计数，可在两个视图隐藏 tool call/结果，或为聚焦用户/assistant 的 transcript 去掉非消息 session 事件；一个按钮同时展开或折叠所有手风琴。下载按钮从内嵌（base64 编码）页面的 entry 数据复现 JSONL 导出，单独的 HTML 文件即可往返完整 session。过滤器只改导出视图；完整 session 仍内嵌在文档里。

## 为什么存在

Baldric session 是 append-only 树，不是单一扁平聊天记录。这对未来 fork 与分支工作流很重要——多个候选分支可以共享同一根。纯 transcript 会掩盖那个形状，让回放、compaction 或分支选择难以调试。

导出器把可视化留在 `baldric_coding`，因为它是持久 session 数据之上的应用工作流。可复用的 `baldric_agent`
session 模型保持 provider 中立与 frontend 中立。

## 与 Pi 的对应

Pi 有一个 HTML session 导出流程用于在交互界面之外检视对话状态。Baldric 镜像核心产品行为且实现更小：导出器从既有
`SessionEntry` JSONL 记录渲染静态 HTML，而不加一个单独的客户端应用。

## 怎么测试

跑聚焦测试：

```bash
uv run pytest tests/test_session_export.py tests/test_cli.py -k export
```

发布前跑全量门：

```bash
uv run pytest
uv run ruff check src tests
uv run mypy
uv run --group docs mkdocs build --strict
```
