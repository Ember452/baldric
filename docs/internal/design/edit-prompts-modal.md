# 从 `/prompts` 编辑 prompt template

## 变更了什么

`/prompts` picker 现在对高亮模板提供 **Ctrl+E**。Baldric 在 Textual `TextArea` 里打开完整 Markdown 源；**Ctrl+S** 写回该模板的既有路径并重载 session 资源。**Escape** 不保存直接返回。

## 为什么

此前 picker 只能把 `/name` 插入输入框。更新 template 需要离开 Baldric、找到它生效的用户级或项目级文件、在外部编辑、再运行 `/reload`。弹窗内编辑把这条维护流程留在活动 session 内，新内容立即可用。

## 架构

该功能留在 `baldric_coding.tui`——Textual 的适配器层。`PromptTemplate` 继续表示发现的资源，`CodingSession.reload()` 仍是文件变更后重新发布资源状态的唯一路径。没有 Textual 依赖进入 `baldric_agent`。

编辑器加载并保存完整 Markdown 源，而不是只有解析后的 prompt 内容，保留 `description` 这类可编辑 frontmatter。读取、写入与重载失败以 TUI 通知显示。

## 验证

自动化试点覆盖：打开 `/prompts`、调用 **Ctrl+E**、编辑并保存一个临时 template，并校验文件内容与资源重载。手动验证：

1. 创建 `~/.agents/prompts/example.md`。
2. 启动 Baldric 运行 `/prompts`。
3. 高亮 `/example`，按 **Ctrl+E**，修改 Markdown，按 **Ctrl+S**。
4. 确认 picker 返回，且 `/example` 使用更新后的 template，无需手动 `/reload`。
