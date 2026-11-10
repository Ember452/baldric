---
title: 主题
description: 用 JSON 主题文件重塑 Baldric TUI——从单个颜色到完整自定义调色板。
---

Baldric 的 TUI 主题是 JSON 文件。内置主题（`baldric-dark`、`baldric-light`、
`high-contrast`）以 JSON 形式随包发布，经与自定义主题相同的
解析器加载，因此可以直接当参考样例：
[`src/baldric/runtime/tui/themes/`](https://github.com/Ember452/baldric/tree/main/src/baldric/runtime/tui/themes)。

## 添加自定义主题

把 `.json` 文件放进某个主题目录：

- `~/.baldric/themes/` — 所有项目可用
- `<project>/.baldric/themes/` — 项目级，名字冲突时胜过用户目录

主题在启动时发现；添加或编辑文件后重启 Baldric。非法主题文件被跳过并给启动提示——它们绝不阻止 Baldric 启动。用 `/theme <name>`、`/theme` picker 或
Textual 命令面板选择主题。选择持久化在 `~/.baldric/tui.json`——
见 [Configuration](/reference/configuration/#tui-设置)。

## 主题格式

```json
{
  "name": "my-theme",
  "dark": true,
  "syntax_theme": "ansi_dark",
  "vars": {
    "base": "#1e1e2e",
    "text": "#cdd6f4",
    "teal": "#94e2d5"
  },
  "colors": {
    "screen_background": "base",
    "screen_text": "text",
    "completion_selected": "bold base on teal",
    "…": "all color fields are required"
  },
  "roles": {
    "user": { "border": "teal", "body": "text on base" },
    "…": "all roles are required"
  }
}
```

- `name`（必填）—— 唯一；不得包含 `/`，也不能与内置主题名重名。
- `dark`（可选）—— 主题是否为深色。默认取 `screen_background` 的亮度。控制深浅色渲染细节，例如工具结果颜色。
- `syntax_theme`（可选）—— 围栏代码块的 Pygments 样式，或
  `ansi_dark` / `ansi_light`。默认跟随 `dark`。
- `vars`（可选）—— 具名颜色。`colors` 或 `roles` 值里任何匹配 var 名的空白分隔 token 都会被其值替换，因此 `"bold base on teal"` 这样的复合 Rich 样式可用。与 Rich 样式关键字（`on`、`bold`、`dim`……）冲突的 var 名被拒绝，var 值必须是单个颜色 token。
- `colors`（必填）—— 主题调色板的每个字段，包括
  `success` / `error` 状态 token 与工具调用文本的 `tool_success_text` /
  `tool_error_text` 颜色。完整列表见 `src/baldric/runtime/tui/themes/__init__.py` 的 `THEME_COLOR_FIELDS`；内置主题 JSON 文件在上下文里展示了全部字段。
  大多数颜色同时由 Rich 与 Textual 渲染，所以坚持两者都接受的格式——`#94e2d5` 这类六位 hex 总是安全。库专属语法，例如 Rich 的 `bright_red` / `grey50` 或 Textual 的 `ansi_red` /
  `#ff000080` 会被拒绝，仅 Rich 的 `tool_success_text` /
  `tool_error_text` 字段与 `completion_*` 样式字符串例外。
- `roles`（必填）—— 每个 transcript 角色的 `border` 与 `body` 样式：
  `user`、`assistant`、`tool`、`error`、`status`、`thinking`、`skill`、
  `custom`（extension 消息）、`branch_summary`、`compaction_summary`。
  `body` 是 Rich 样式字符串，
  可以带背景（`"#cdd6f4 on #1e1e2e"`）；其颜色也会影响周围的 Textual 组件，所以与调色板颜色一样必须使用两个库都接受的格式。`border` 是每块 transcript 旁的彩色竖条；完成的 tool call 会用 `success` 或 `error` 覆盖 `tool` 边框。

校验一次报告文件里的所有问题，新主题可以一轮修完。
