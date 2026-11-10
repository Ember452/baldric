# `/resume` picker 搜索栏

## 变更了什么

`/resume` 弹窗（`src/baldric_coding/tui/app.py` 的 `SessionPickerScreen`）现在有搜索框，与模型 picker
（`ModelPickerScreen`）及登录 provider picker
（`LoginProviderPickerScreen`）既有的搜索 UX 一致。

- 打开 `/resume`（或按 `Ctrl+R`）时，焦点落在 session 列表上方新的
  `#session-picker-search` 输入框。
- 输入按 session 名或模型实时过滤可见 session（大小写不敏感
  子串匹配）。工作目录不影响搜索结果。
- 方向键、Enter、Escape 的行为不变，无论焦点在搜索框还是列表——搜索输入把这些键转发给 picker screen，而不是编辑自己的文本。
- 在搜索框提交（Enter）选中当前高亮的
  session，与列表聚焦时按 Enter 相同。
- 没有 session 匹配时，帮助行切换为 "No matching sessions -
  Escape closes"。

## 为什么存在

session 列表随时间增长，在未过滤的列表里滚动找特定历史 session 很痛苦。这让 `/resume` 与已提供该模式的模型/登录 picker 对齐。

## 与既有 picker 的对应

新的 `SessionPickerSearchInput` 与 `SessionPickerScreen` 的刷新/过滤逻辑镜像
`ModelPickerSearchInput` /
`_filter_model_choices` 与 `LoginProviderSearchInput` /
`_filter_login_providers`：

- 专用的 `Input` 子类把导航键（`up`、`down`、`escape`）
  留在 picker 本地，不让 `Input` 组件消费它们。
- 模块级 helper `_filter_session_records` 从完整记录列表与当前搜索文本计算可见记录。
- 搜索文本或记录集变化时，`_refresh_session_list` 重建
  `ListView` children 与帮助文本。

`baldric_agent` 与 `baldric_ai` 无需变更——这纯粹是
`baldric_coding` 的 TUI/frontend 变更，与"可复用 agent harness 不含 Textual 专属代码"一致。

## 测试

- `test_tui_app_session_picker_search_filters_sessions` —— 输入查询缩小列表，Enter 仍恢复高亮的（过滤后）session。
- `test_tui_app_session_picker_search_does_not_match_workspace_path` —— session 名与模型匹配，工作目录匹配被忽略。
- `test_tui_app_session_picker_search_with_no_matches_shows_help_text` —— 无匹配查询清空列表并更新帮助文本。
- 既有的 `/resume` picker 测试（方向键导航、Enter 恢复、人类可读元数据）不变通过。

## 手动验证

1. 创建几个不同标题/模型的 session（或恢复真实历史），让 `/resume` 有多行。
2. 运行 `baldric`，按 `Ctrl+R`（或输入 `/resume` 回车）。
3. 确认搜索框已聚焦，输入部分 session 名或模型名——列表实时收窄。工作目录路径片段不应产生匹配。
4. 按 Enter 恢复高亮 session。
5. 试一个无匹配的查询，确认帮助文本变为 "No matching sessions - Escape closes"。
6. 任意时刻按 Escape，确认 picker 仍关闭而不恢复。
