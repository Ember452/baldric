---
title: Skill 与 prompt template
description: 用 skill 教 Baldric 可复用的知识，用 prompt template 免去重复输入指令。
---

Baldric 从磁盘加载两种可复用 Markdown：**skill**（怎么做一件事）和 **prompt template**（按名称触发的已保存 prompt）。两者都可以放在用户级（处处可用）或项目内。

## 文件放在哪

skill 从这些位置加载，优先级递增（名字冲突时后者覆盖前者）：

```text
~/.baldric/skills/
~/.agents/skills/
<cwd>/.baldric/skills/
<cwd>/.agents/skills/
```

prompt template 从这些位置加载：

```text
~/.baldric/prompts/
~/.agents/prompts/
<cwd>/.baldric/prompts/
<cwd>/.agents/prompts/
```

TUI 打开时添加或编辑了文件，运行 **`/reload`** 重新发现它们。重复/被覆盖的资源报告为诊断，不是致命错误。TUI 启动时，不同位置的 skill 或 prompt template 同名时 Baldric 还会在 transcript 里显示红色警告。警告列出两个路径，方便你重命名或移除非预期的重复；Baldric 仍使用优先级更高的资源。

## Skill

skill 是包含 `SKILL.md` 文件的目录，遵循
[Agent Skills spec](https://agentskills.io/specification#directory-structure)。
目录名就是 skill 名。可选的 frontmatter 提供描述：

```text
~/.baldric/skills/security-review/SKILL.md
```

```md
---
description: Review a diff for security issues.
---

Steps to review the current diff for security problems...
```

支撑文件（参考、片段）可以与 `SKILL.md` 一起放在同一目录里。

> [!TIP]
> skills 目录根下的裸 `.md` 文件（例如
> `~/.baldric/skills/review.md`）**不会**作为 skill 加载。Baldric 会给出
> 诊断，提示你把它们移进自己的目录：
>
> ```bash
> cd ~/.baldric/skills
> mkdir review && mv review.md review/SKILL.md
> ```
>
> 这符合 Agent Skills spec，并在 `.baldric/` 与
> `.agents/` 位置统一适用。

Baldric 自己的 extension 与 provider 工作流是打包文档，不是内置 skill。它们对 agent 保持可用，但不出现在你的 skill 列表里、不与你的 skill 名冲突、也不被
`--no-skills` 禁用。

Baldric 在 system prompt 里列出已加载的用户与项目 skill，模型因此知道它们存在，并能在相关时（经 `read` 工具）读取完整文件。运行 **`/skills`** 搜索名字与
描述，选中一个把其调用插入 prompt，再补充指令。
在 picker 里，**F1** 打开完整的头部描述，**Ctrl+Enter** 在 transcript 里显示完整
`SKILL.md` 供检视而不加入模型 context。或显式调用：

```text
/skill:security-review check the changes on this branch
```

较长的指令把 request 放在后续行：

```text
/skill:security-review

Check the changes on this branch.
Pay special attention to authentication boundaries.
```

`/skill:<name>` 是 *prompt 展开*路径——Baldric 把 skill 与任何
行内或多行 request 展开进你的 prompt，然后作为普通一轮运行。

### 对模型隐藏 skill

在 frontmatter 设 `disable-model-invocation: true`，让 skill 不进
system prompt。模型看不到它、也不会自行调用，但你
仍可用 `/skill:<name>` 显式运行（它也仍出现在
`/skills` picker 与补全里）：

```md
---
description: Generate the weekly status report.
disable-model-invocation: true
---

Steps to build the report...
```

适合由用户触发的流程——否则它们只会给 skill 列表添乱，或诱使模型在不合适的时候触发。

## Prompt template

prompt template 是按文件名触发的已保存 prompt。例如
`~/.agents/prompts/wt.md` 用 `/wt` 调用。在 TUI 运行 `/prompts`
搜索所有已加载模板。按 **Enter** 只插入调用不提交，或 **Ctrl+E** 直接编辑其 Markdown。用 **Ctrl+S** 保存；
Baldric 自动重载资源。文件名与内置 slash 命令或别名相同的模板——例如 `new.md`、`quit.md` 或 `exit.md` ——是保留的：Baldric 加载时忽略它，并给出指名文件与冲突命令的资源诊断，让 `/new`、`/quit` 之类的内置命令保持可达。文件名主干匹配不区分大小写。template 使用与 Pi 相同的参数变量：

- `$1`、`$2`…… 位置参数
- `$@` 或 `$ARGUMENTS` 以空格连接的全部参数
- `${1:-default}` 与 `${@:-default}` 默认值
- `${@:N}` 或 `${@:N:L}` 简单的参数切片

```md
---
description: Implement a feature in an isolated git worktree.
---

Implement this feature safely in a new worktree:
Feature: $1
Additional instructions: ${@:2}
```

用 `/wt add caching` 调用。带引号的参数保留为一个位置参数，例如 `/wt add "shared caching"`。旧式的
`{{ arguments }}` 与 `{{ args }}` 占位符继续支持。

template 没有参数占位符时，你的参数追加在空行之后。

每个内置命令名与别名都保留，不只是 `prompts.md`、`skills.md` 这类 picker 名。如果你以前靠 template 遮蔽命令——比如 `new.md` 展开自定义 prompt 而不是开新
session——把文件改名为不冲突的 `new-feature.md`，用 `/new-feature` 调用。

## skill 还是 prompt template？

- 反复输入**同样的指令**、只想要个快捷方式（可带填空变量），用 **prompt template**。
- 想给模型*参考知识*、任务需要时再取用、用 `/skill:<name>` 调用，用 **skill**。

> [!TIP]
> 个人的、跨项目的 helper 放 `~/.agents/`。项目专属的放仓库的 `.baldric/` 或 `.agents/`，与协作者共享。
