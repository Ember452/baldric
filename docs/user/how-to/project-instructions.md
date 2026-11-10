---
title: 项目指令（AGENTS.md）
description: 用 AGENTS.md 文件给 agent 关于你项目的长期指令。
---

**`AGENTS.md`** 文件是你给 agent 持久的项目级 context 的方式：要遵循的约定、要跑的命令、要避开的东西。Baldric 自动发现这些文件，并把它们包进每一轮的 system prompt，外层套 `<project_context>` 标签。

## 放什么进去

任何你否则每个 session 都要重复给 agent 的东西：

- 怎么跑测试、lint、构建、格式化
- 项目约定（风格、commit message 格式、分支命名）
- 架构注释与坑
- "总是 X / 永不 Y" 规则

保持聚焦——它是每一轮 prompt 预算的一部分。

## Baldric 在哪里找

Baldric 按此顺序发现指令文件。用户文件总是合格；项目文件只在活动 cwd 的[项目信任决定](/how-to/project-trust/)之后纳入：

```text
~/.baldric/AGENTS.md
~/.agents/AGENTS.md
<project root>/AGENTS.md
<project root>/.../<cwd>/AGENTS.md   # 根与 cwd 之间的祖先目录
<cwd>/.baldric/AGENTS.md
<cwd>/.agents/AGENTS.md
```

**项目根**是最近的含有 `.git`、`pyproject.toml`、`uv.lock`、`setup.py` 或 `package.json` 之类标记的祖先目录。

这种分层让你把个人全局指令放在 `~/.baldric/` 或 `~/.agents/`、项目级规则放在仓库 `AGENTS.md`、更细的规则放在离工作位置更近的子目录。

## 编辑后重载

TUI 打开时改了 `AGENTS.md`，运行 **`/reload`** 刷新后续轮次的项目 context。向空项目添加第一个受保护文件会触发信任解析，而不是静默继承旧的空快照。

> [!NOTE]
> Baldric 自己在仓库根用了一个 `AGENTS.md`——一个实践中的真实样例。
