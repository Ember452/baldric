---
title: 键盘快捷键
description: Baldric TUI 的默认按键，以及如何重新映射。
---

以下是交互式 [TUI](/how-to/tui/) 的默认按键。在会话内运行 `/hotkeys` 可以查看它们，并在 `~/.baldric/tui.json` 里重新映射（见[配置](/reference/configuration/#tui-设置)）。

## 输入

| 键 | 动作 |
| --- | --- |
| `Enter` | 接受高亮的非文件补全；否则按输入原样提交 prompt（包括 `@` 文件引用文本） |
| `Shift+Enter` | 插入换行 |
| `Esc` | 取消当前运行 |
| `Enter`（运行中） | 把文本排队为当前运行的 steering |
| `Alt+Enter` | 排队一个 follow-up，等到运行本会结束之后执行 |
| `Up`（空 prompt 且运行中） | 把最近排队的 follow-up 拉回输入框编辑 |

## 导航与 picker

| 键 | 动作 |
| --- | --- |
| `Ctrl+K` | 打开命令面板 |
| `Ctrl+R` | 打开 session 选择器 |
| `Tab` | 接受高亮补全，包括 `@` 文件引用 |
| `Down` / `Up` | 在补全间移动 |
| `Ctrl+E`（在 `/prompts` 中） | 编辑选中的 prompt template |
| `Ctrl+S`（编辑 prompt template 时） | 保存并重新加载资源 |

## 模型与 thinking

| 键 | 动作 |
| --- | --- |
| `Ctrl+P` | 向前轮换 scoped（收藏）模型 |
| `Shift+Ctrl+P` | 向后轮换 scoped（收藏）模型 |
| `Shift+Tab` | 轮换 thinking mode |
| `Ctrl+T` | 切换 thinking/reasoning 内容的显示 |

## 输出与 session

| 键 | 动作 |
| --- | --- |
| `Ctrl+O` | 切换确切工具命令与完整输出（对比紧凑预览） |
| `Ctrl+C` | 清空 prompt 输入 |
| `Ctrl+D` | 退出 |

> [!NOTE] 重新映射
> 按键使用 Textual 的语法（`ctrl+k`、`shift+tab`、`down`、`f2`……）。Baldric 拒绝未知名称、空键位与重复赋值，错误尽早暴露。未设置的键保持默认。如果你的终端无法把 `Shift+Enter` 与 `Enter` 区分开，选一个它能单独上报的键：
>
> ```json
> {
>   "keybindings": {
>     "insert_newline": "f2"
>   }
> }
> ```
