---
title: "Phase 12：Textual TUI"
---

Phase 12 用 Textual 加了 Baldric 第一个交互式终端 UI。

实现位于：

```text
src/baldric_coding/tui/
```

## 加了什么

Baldric 现在有一个最小交互 TUI：

- 用 `CodingSession` 而非裸 `AgentHarness`
- 经 Textual 输入组件接受用户 prompt
- 把 `AgentEvent` 流式转入 TUI 显示状态
- 显示 assistant 消息、工具事件、状态消息与错误
- 显示深色 session 侧栏：model、cwd、tools、skills 与 prompt template
- 把之前的 session 消息还原进可见 transcript
- 支持既有的 `/help` 与 `/exit` 命令处理
- 支持 Escape 请求取消
- 把早期默认 TUI session 存于 `.baldric/sessions/default.jsonl`

CLI 默认打开 TUI：

```bash
baldric
```

全局选项可在启动 TUI 前传入：

```bash
baldric --model gpt-4.1-mini --cwd /path/to/project
```

## 为什么存在

Pi 把可复用 agent 层与终端 UI 事务分开：

```text
agent/session emits events
terminal frontend consumes events
TUI components render display state
```

Baldric 现在用 Python 原生的 Textual 遵循同一边界：

```text
CodingSession.prompt()
  emits AgentEvent
      ↓
TuiEventAdapter
  updates TuiState
      ↓
BaldricTuiApp
  renders Textual widgets
```

`baldric_agent` 仍不依赖 Textual、Rich、Typer 或终端 UI 行为。

## TUI 状态适配器

适配器层刻意与 Textual 分离：

```text
src/baldric_coding/tui/state.py
src/baldric_coding/tui/adapter.py
```

`TuiState` 存储仅显示的状态：

- transcript 项
- 当前 assistant 流式缓冲
- 运行标志
- 最近错误

`TuiEventAdapter` 把可移植 `AgentEvent` 应用到该状态。

这让事件到显示的行为无需启动终端应用即可测试。

## Textual 应用

Textual 应用刻意保持最小：

```text
src/baldric_coding/tui/app.py
src/baldric_coding/tui/widgets.py
```

它使用：

- `Header`
- `Footer`
- `Static` 做状态与侧栏内容
- `Horizontal` 与 `Vertical` 容器做侧栏/主布局
- 可滚动的 transcript，由可选中消息组件构成
- `Input` 做 prompt 提交

prompt 执行运行在 Textual worker 里，事件流式期间 UI 可以继续更新。

## session 存储

Phase 12 加了一个临时的默认本地 session 路径 helper：

```python
def default_session_path(cwd: Path) -> Path:
    return cwd / ".baldric" / "sessions" / "default.jsonl"
```

刻意简单。后续阶段可以用更丰富的 Pi 式 session 管理器与 picker 替换它。

## 当前限制

TUI 是地基，还不是完整的 Pi 级界面。它不含：

- session picker
- 模型 picker
- 命令面板
- 树导航
- diff 查看器
- markdown 渲染
- 主题自定义
- 键位配置
- extension UI hook
- compaction UI

## 测试

本阶段覆盖于：

```text
tests/test_tui_adapter.py
tests/test_cli.py
```

测试聚焦纯适配器与 CLI 接线。完整终端交互测试推迟到 TUI 表面稳定。

## 下一阶段

下一阶段可以从以下方向增量扩展 TUI：

- session 选择与恢复支持
- 更丰富的 transcript 渲染
- 命令面板与 slash 命令注册表
- extension hook
- compaction/context 管理 UI
