# `/resume` 项目导航

## 变更了什么

PR #669 让每个工作目录的 session 在 `/resume` 可用。本跟进把那份历史呈现为双栏导航器，而不是把外部 session 追加在当前项目的 session 下面：

- **Projects** 列出紧凑文件夹名，当前工作目录在前，其余项目按其最近一次索引的 session 排序。
- **Recent sessions** 只显示所选项目的 session，最新在前；其标题保留所选目录的完整路径。
- Left 把导航移到项目栏；Up/Down 换项目并立即更新其 session 列表；Right 回到 session；Enter 恢复。
- 点击项目打开其 session 列表，不恢复任何东西。
- 搜索保持焦点可输入，并在所选项目内过滤名字/模型。

两栏共享一条外层浏览器边框与一条分隔线，像 Finder 的连续栏视图而不是两个独立面板。活动栏有 accent 标题。当前项目有标记，项目行省略 session 计数，session 列表保留水平留白。

## 架构

它完全留在 `baldric_coding.tui.app.SessionPickerScreen`。session
存储、索引与可移植的 `baldric_agent` harness 不变。picker 从 session 管理器供给的记录推导规范项目路径，保留既有的当前项目优先与按时间排序。

## 验证

自动化 Textual pilot 测试覆盖键盘栏切换、项目点击、
项目内搜索、空项目、重复列表刷新、边界
导航与 session 恢复。

手动检查：

1. 在一个 session 历史在别处的项目里打开 `/resume` 或按 Ctrl+R。
2. 确认初始可见当前项目的最近 session。
3. 按 Left 并用 Up/Down 预览其他项目的 session。
4. 按 Right，选一个 session，按 Enter 恢复。
5. 确认输入只过滤所选项目的 session，Escape 关闭而不恢复。
