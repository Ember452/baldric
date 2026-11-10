# `/resume` 后台加载

## 变更了什么

TUI 现在先挂载一个空的 `/resume` 壳，然后在后台线程读取当前与其他项目索引。已打开的 picker 显示分阶段加载消息并保持可用；先是当前项目的 session，然后完整项目列表出现，都不替换弹窗。

两个 picker 栏使用 Textual 的虚拟化 `OptionList`。此前每个 session 与项目都成为挂载的 `ListItem`，尽管弹窗最多显示 16 行。大历史因此把远多于解析索引的时间花在构建组件上。`OptionList` 保留每个可搜索选项但只渲染可见行。

普通 `/resume` 命令补全不再在命令名本身还在输入时读取 session 索引。`/resume ` 之后跟参数文本时 session-id 补全仍可用。

## 为什么

同步聚合每个 `~/.baldric/sessions/*/index.jsonl` 文件会在弹窗出现前阻塞 Textual 事件循环。急切挂载数百个行组件又叠加更大延迟。把跨项目文件系统与 Pydantic 工作移出事件循环、并虚拟化两栏，让常见的当前项目路径立即可用，同时保留跨项目发现与搜索。

## 安全与行为

- 全局后台失败让已加载的当前项目 session 保持可用并显示警告。
- picker 已被关闭或替换时忽略结果。
- 刷新在记录仍存在时保留所选项目、搜索词与所选 session。
- session 管理器与可移植 agent harness 保持对 Textual 独立。

## 验证

一个 Textual pilot 测试阻塞全局索引读取，验证弹窗与本地 session 已可交互，然后放行读取并验证其他项目出现。既有的 picker 导航、搜索与 resume 测试覆盖刷新后的列表。
