# 可搜索的 skill picker

Issue #451 增加 `/skills` 作为仅 TUI 的发现流程。普通命令注册表返回一个 UI 意图，把 Textual 挡在可复用的 command/session 层之外。Textual 适配器按名字排序呈现已加载 skill，并不区分大小写地过滤名字与描述。

选中一行把 `/skill:<name>` 放入 prompt 而不提交。F1 在弹窗中预览完整的 skill 头部描述，同时把 Space 留给多词搜索。Ctrl+Enter 把完整 `SKILL.md` 追加进仅供显示的 TUI 状态，于是它出现在 transcript 里而不进入持久 session 历史或模型 context。取消会还原已提交的 `/skills` 文本。空集合与空搜索显示明确状态；既有资源诊断仍在其既有界面呈现。

验证：

```bash
uv run pytest tests/test_commands.py tests/test_tui_app.py
```
