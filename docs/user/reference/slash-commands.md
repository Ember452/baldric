---
title: slash 命令
description: Baldric TUI 中的全部会话内 slash 命令。
---

在交互式 [TUI](/how-to/tui/) 里输入这些命令。用 **Ctrl+K** 打开可搜索的命令面板。

| 命令 | 说明 |
| --- | --- |
| `/quit` | 退出会话 |
| `/new` | 开始新 session |
| `/session` | 显示 session 信息与统计（model、cwd、tools、skills、context） |
| `/context` | 显示本 session 已加载的项目 context 文件 |
| `/diagnostics` | 检视资源加载的警告与错误，包括其来源路径 |
| `/system` | 按来源分组显示活动 system prompt，不加入 context 或 session 历史 |
| `/compact [instructions]` | 总结并压缩活动 context |
| `/export [--format html\|jsonl] [dest]` | 导出当前 session |
| `/resume [session-id]` | 恢复之前的 session，或打开选择器 |
| `/tree` | 从 session 树上更早的点分支 |
| `/name <new name>` | 重命名当前 session；在支持的终端里同步更新终端标签页标题 |
| `/model` | 刷新 provider 目录并打开模型选择器 |
| `/tools` | 浏览活动工具并查看完整描述 |
| `/scoped-models` | 刷新 provider 目录并为 Ctrl+P / Shift+Ctrl+P 快速轮换选择收藏模型 |
| `/theme [name]` | 显示或设置 TUI 主题 |
| `/login [provider]` | 通过 OAuth 或 API key 连接内置 provider；Anthropic 使用 `anthropic-subscription` 或 `anthropic-api` |
| `/local` | 选择并管理已注册的本地 backend；仅限交互模式。兼容的 llama.cpp router 提供显式加载/卸载、Hugging Face GGUF 搜索与服务端下载动作，均带确认与对账 |
| `/sidebar` | 为本 session 切换侧栏可见性，不修改 `tui.json` |
| `/logout [provider]` | 移除某 provider 的已存凭据 |
| `/extensions` | 打开已加载 extension 与 extension 诊断的可搜索清单 |
| `/mcp [on\|off\|restart] [name]` | 列出已配置的 MCP 服务器，或启用/禁用/重启其中一个；`on`/`off` 会记住在 `mcp.json` 里 |
| `/reload` | 重新加载本地 skill、prompt、extension 与项目 context |
| `/prompts` | 搜索已加载的 prompt template；按 Enter 插入调用，Ctrl+E 编辑文件 |
| `/help` | 列出可用的 slash 命令 |
| `/hotkeys` | 显示键盘快捷键 |
| `/skills` | 打开已加载 skill 的可搜索 picker，并把选中项插入 prompt |
| `/skill:<name> [request]` | 把已加载的 skill 展开进你的 prompt |

`/system` 给连续的 prompt 区块标注来源，包括 Baldric 的内置 prompt、`SYSTEM.md` 与 `APPEND_SYSTEM.md` 文件、项目指令文件、skill、extension 区块以及运行时日期/cwd 值。在 TUI 中，每个区块用与其来源名颜色匹配的独立浅色背景。如果活动 prompt 与 Baldric 确定性的组合结果不再一致，Baldric 会保守地显示一个运行时组合来源，而不是猜测。

> [!NOTE] 实时 HTML 导出包含 system prompt
> `/export` 在生成 HTML 时会把当前 system prompt 放进一个折叠区块。分享前先检查，因为它可能暴露项目指令或其他本地 context。JSONL 导出不包含 prompt。离线的 `baldric export` 从已存 JSONL 无法恢复它，会省略该区块。HTML 导出的 **Usage** 视图以图表展示 token 与缓存活动。其 prompt 输入图表会相对下一次模型请求标注 compaction、模型与 thinking 级别变更以及分支摘要，让缓存变化有会话上下文。

> [!NOTE] `/skill:` 是特殊的
> `/skill:<name>` 是*prompt 展开*路径，不是普通命令——Baldric 把指定的 skill 展开进你的 prompt 并作为一轮运行。它的可选 request 可以与命令同一行，也可以在后续行。见 [Skills & prompt templates](/how-to/skills-and-prompts/)。

只有已注册的命令会被本地消费。其他以斜杠开头的输入，包括 `/tmp`、`/Users/me/file.png` 这类绝对路径，都作为普通 prompt 发给模型。

相关内容：

- **Thinking mode** 由键盘驱动，不是 slash 命令——见[键盘快捷键](/reference/keybindings/)与[管理 context](/how-to/context/#thinking-mode)。
- **Prompt template** 使用 slash 调用（例如 `/wt …`）。用 `/prompts` 搜索已加载模板、只插入调用不提交，或用 **Ctrl+E** 编辑选中的模板。
