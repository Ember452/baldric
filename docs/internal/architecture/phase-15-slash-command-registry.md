---
title: "Phase 15：slash 命令注册表"
---

Phase 15 把 Baldric 硬编码的 slash 命令处理替换为 `baldric_coding`
里的一个小注册表。

实现位于：

```text
src/baldric_coding/commands.py
```

## 加了什么

Baldric 现在有一个 `CommandRegistry`，可以：

- 以名字、别名、描述与用法文本注册 slash 命令
- 列出已注册命令供生成的帮助输出
- 解析 slash 命令输入
- 把命令分发给 handler
- 向 UI 层返回结构化的命令结果

核心命令类型：

```python
SlashCommand
CommandContext
CommandResult
CommandRegistry
```

`CodingSession.handle_command()` 现在委托给注册表，而不是硬编码命令行为。

## 内置命令

默认注册表包括：

- `/quit` — 退出当前 session
- `/new` — 开始新 session
- `/compact` — 用手动摘要替换活动 context
- `/export` — 导出当前 session
- `/session` — 显示 session 信息与统计
- `/hotkeys` — 显示常用 TUI 快捷键
- `/resume` — 打开既往 session 选择或恢复指定 session id
- `/model` — 选择或切换当前模型
- `/login` — 添加或刷新内置 provider 登录
- `/reload` — 重载本地资源与项目 context
- `/name` — 重命名当前 session
- `/theme` — 显示或设置 TUI 主题

补全还使用非执行的搜索词。例如输入
`/clear` 会建议 `/new`，但搜索词不是已注册命令。

## 为什么属于 `baldric_coding`

slash 命令是编码 agent 应用行为。它们依赖资源、
session、skill、provider/model UX 与 UI 期望。

可复用的 `baldric_agent` 包保持对 slash 命令、Textual、
Typer、本地配置目录与 Baldric 专属产品行为独立。

## Pi 命令对齐

Pi 的内置命令清单包括：

```text
settings, model, scoped-models, export, import, share, copy, name, session,
changelog, hotkeys, fork, clone, tree, login, logout, new, compact, resume,
reload, quit
```

Baldric 镜像能干净映射到既有 Baldric 能力的命令：

- `/session` 映射 Baldric 既有的 session 状态/详情输出。
- `/hotkeys` 报告 Baldric 当前常用 TUI 快捷键。
- `/quit` 是唯一注册的退出命令；旧 Baldric 专属的 `/exit` 与
  `/q` 别名有意不保留。
- `/model`、`/login`、`/new`、`/compact`、`/resume`、`/reload`、`/name`、
  `/theme` 与 `/export` 存在于 Baldric 命令注册表。

Baldric 有意把更早的 Baldric 专属诊断命令移出注册表，包括 `/help`、`/status`、`/skills`、`/resources`、`/context`
与 `/thinking`。等价信息仍可通过
Pi 对齐命令、持久 UI 面、键位或模型 system prompt 看到。

其余 Pi 命令推迟——它们需要超出本次注册表清理的更大工作流：

- `/settings`
- `/scoped-models`
- `/import`
- `/share`
- `/copy`
- `/changelog`
- `/fork`
- `/clone`
- `/tree`
- `/logout`

## TUI 集成

TUI 仍调用：

```python
session.handle_command(text)
```

但返回的 `CommandResult` 现在可以请求退出之外的更多行为。

例如 `/new` 返回 `new_session_requested=True`。TUI 响应方式是创建并加载一个全新的已索引 session，而不删除更早的持久 JSONL
session 历史。

## prompt 展开命令行为

`/skill:<name> [request]` 仍是 prompt 展开路径，不是普通 slash
命令。

prompt template 也表现为动态的 prompt 展开命令。例如
`.agents/prompts/example.md` 以 `/example [arguments]` 调用，由
`CodingSession.prompt()` 在模型看到 prompt 之前展开。

注册表对 skill 与 prompt template 展开指令有意返回 `handled=False`，让
`CodingSession.prompt()` 在把 prompt 发给模型之前替换它们。

与 Pi 一样，Baldric 对每条未注册的斜杠前缀输入也返回 `handled=False`。只有被识别的命令在本地消费；未知命令样式文本与 `/tmp`、`/Users/me/file.png` 之类的绝对路径继续作为普通 prompt。

Pi 对齐的注册表里没有纯 `/skill` slash 命令。

## 未来用途

这个注册表是后续阶段的基础：

- TUI slash 命令补全可以从注册表读命令元数据。
- extension 终究可以贡献命令。
- 未来的命令面板可以显示同一份命令元数据。

## 测试

本阶段覆盖于：

```text
tests/test_commands.py
tests/test_coding_session.py
tests/test_tui_app.py
```

测试验证：

- 命令解析与分发
- 生成的帮助输出
- 退出与新 session 控制旗标
- status 与 skills 输出
- `/skill:<name>` 直通行为
- 已索引 session 列表
- 结构化的 `/resume <session-id>` 请求
- TUI 对 `/new` 的处理
