---
title: "Phase 19：项目 context 发现与重载"
---

本阶段加 Baldric 的项目指令发现与 reload 命令。它留在
`baldric_coding`，与资源、命令、session 启动为伴。

实现位于：

```text
src/baldric_coding/context.py
src/baldric_coding/session.py
src/baldric_coding/cli.py
src/baldric_coding/commands.py
```

## 加了什么

Baldric 现在自动发现 markdown 指令文件，并把它们插入既有
`ProjectContextFile` system prompt 区块。

当前发现顺序：

```text
~/.baldric/AGENTS.md
~/.agents/AGENTS.md
<project root>/AGENTS.md
<project root>/.../<cwd>/AGENTS.md
<cwd>/.baldric/AGENTS.md
<cwd>/.agents/AGENTS.md
```

项目根是最近的含有 `.git`、`pyproject.toml`、`uv.lock`、`setup.py` 或 `package.json` 等常见项目标记的祖先。没有标记时，Baldric 把 session cwd 当项目根。

## system prompt 集成

正常 `CodingSession` 启动与非交互 print mode 都把发现的 context 文件传入：

```python
BuildSystemPromptOptions(context_files=...)
```

这保留了 Phase 10 的 prompt 边界：

```text
baldric_coding discovers local files
baldric_coding.system_prompt formats them
baldric_agent receives only a ready system string
```

`baldric_agent` 仍不依赖本地资源发现、Baldric home、
项目路径、slash 命令、Rich 或 Textual。

## slash 命令

Baldric 现在有：

```text
/context
/reload
```

`/context` 列出运行中 session 的活动项目 context 文件。

`/reload` 为后续轮次刷新 Baldric 自有资源：

- skill
- prompt template
- 项目 context 文件
- 资源诊断

session 使用 Baldric 生成的 system prompt 时，只有当供给该 prompt 的资源变化时 reload 才重建 harness system 字符串。
transcript 与 session 树不动。

`/reload` 不刷新 provider 配置。provider/model 设置由使用它们的 provider 专属流程刷新，例如保存凭据后的 `/login`、校验选择或打开模型 picker 前的 `/model`。

`/status` 与 `/resources` 也包含当前 context 文件计数。

## 边界

reload 是 `baldric_coding` 操作。它更新 harness 周围的 coding-session 环境，需要时把重建的 system 字符串交给 harness 供后续轮次使用。`baldric_agent` 不知道 skill、prompt 或 context 文件从哪来。

## 测试

本阶段覆盖于：

```text
tests/test_context.py
tests/test_coding_session.py
tests/test_cli.py
tests/test_commands.py
```

测试验证：

- 用户、项目、嵌套、`.baldric` 与 `.agents` context 发现
- 发现的 context 进入 session system prompt
- 发现的 context 进入 print-mode system prompt
- `/context`、`/status`、`/resources` 命令输出
- `/reload` 命令输出
- 仅当 prompt 输入变化时，reload 才更新资源与下一轮 system prompt
