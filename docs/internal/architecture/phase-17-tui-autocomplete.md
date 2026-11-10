---
title: "Phase 17：TUI slash 命令补全"
---

Phase 17 给 Baldric 的 Textual TUI 加 prompt 补全，同时把逻辑留在
`baldric_coding`。

实现位于：

```text
src/baldric_coding/tui/autocomplete.py
src/baldric_coding/tui/app.py
src/baldric_coding/tui/widgets.py
```

## 加了什么

Baldric 现在从 coding-session 元数据为 prompt 输入构建补全建议：

- 活动注册表 `CommandRegistry` 里的已注册 slash 命令
- 已加载 skill（供 `/skill:<name>`）

纯补全模型是：

```python
CompletionItem
CompletionState
build_completion_state(...)
```

这让补全匹配与替换行为不依赖 Textual 即可测试。Textual 应用只拥有渲染、按键处理与把所选补全应用到 prompt 输入。

## TUI 行为

prompt 以 `/` 开头时，Baldric 显示匹配的 slash 命令。

示例：

```text
/st       -> /status
/ski      -> /skill:
```

命令补全从活动 `CommandRegistry` 读取规范命令名、可执行别名与
非执行的搜索词。搜索词只是过滤器：接受一个会插入规范命令。例如 `/res`
可以直接匹配 `/resume`，也可以经 `/new` 命令的 `reset`
搜索词匹配 `/new`，所以补全把直接命令/别名匹配排第一，其下保留回退搜索词匹配。

prompt 以 `/skill:` 开头时，Baldric 显示匹配的已加载 skill。
接受 skill 补全保留请求的其余部分：

```text
/skill:r fix tests -> /skill:review fix tests
```

prompt 输入处理：

- `Tab` 接受任何选中的补全
- `Enter` 接受选中的 slash 命令、skill、prompt template、参数与
  shell 路径补全；`@` 文件引用则相反，Enter 直接提交原始
  prompt 文本而不应用建议
- `Down` 选择下一个补全
- `Up` 选择上一个补全

建议渲染在 prompt 下方的小条里，不混入 transcript。

## prompt template

prompt template 已加载且在 `CodingSession` 上可用，但 Baldric 还没有面向用户的 `/prompt:<name>` 或等价的模板调用命令。因此 Phase 17 暂不暴露 prompt-template 参数补全；等模板调用命令存在时再加。

## 边界

自动补全不进 `baldric_agent`。

可复用 agent harness 不依赖 Textual、命令注册表、
skill、prompt template 或 Baldric 资源路径。它们仍是
`baldric_coding` 拥有的应用事务。

## 测试

本阶段覆盖于：

```text
tests/test_tui_autocomplete.py
tests/test_tui_app.py
```

测试验证：

- 已注册命令建议
- `/skill:` 建议
- skill 补全后保留请求文本
- 补全选择的循环
- 依赖 context 的 Enter 接受 vs 原样 `@` 文件引用提交
- 每种补全的 Tab 接受
