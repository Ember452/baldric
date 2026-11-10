# TUI 视觉系统第一批验收记录（batch 1）

日期：2026-11-08 · 分支：`design/tui-visual-system` · 截图：`dev-notes/architecture/assets/tui-batch1/*.svg`

## 截图

| 文件 | 内容 |
|---|---|
| `batch1-transcript.svg` | baldric-dark，user 卡片 + 思考折叠 + edit diff（整行底色、词级加粗）+ bash 输出 + 一行状态栏 + thinking 等级色 prompt 边框 |
| `batch1-session-picker.svg` | 会话选择器（全新安装、空记录态） |
| `batch1-model-picker.svg` | 模型选择器（fake 目录，含 scoped 分组） |
| `batch1-light.svg` | baldric-light 同一对话 |

生成方式：headless `app.run_test()` + `app.export_screenshot()`（Textual 输出 SVG）。
脚本在仓库外（`_tmp_okhsl/tui_batch1_shots.py`），不随仓库提交。

## 已知坑（写进流程）

- 截图前必须 `os.environ.pop("NO_COLOR")`，否则全灰（本机环境带 `NO_COLOR=1`）。
- `export_screenshot()` 返回 SVG 字符串，不是字节。
- 验证 SVG 内容时必须显式按 UTF-8 读，pwsh 默认 GBK 会把 CJK 读成乱码（display-only）。

## 验收对照（计划 §9）

| 项 | 结论 | 证据（SVG 内实测颜色/文本探针） |
|---|---|---|
| user 消息卡片可见 | ✅ | `#1e2430`（ raised 亮度层，非 prompt 色）出现在 transcript SVG |
| diff 整行底色 | ✅ | added `#20303b`、removed `#37222c`，词级加粗叠加；文本 `#4fd6be`/`#c53b53`（opencode base.diff） |
| thinking 折叠 | ✅ | 隐藏块折叠为一行 token 计数摘要（`format_hidden_thinking_summary`） |
| 一行状态栏 | ✅ | `cwd · model (medium) · 12k/200k (6%) · $1.24 · 40 tps · TTFT 1.2s`（FakeSession 与 spec §5.4 示例同构） |
| prompt 边框随 thinking 等级 | ✅ | `#3e5e9f`（pi ramp medium）取代静态 `#2d3748` |
| 侧栏默认收起 | ✅ | `size=(120,46)` 仍以 `-hide-sidebar` 启动；Ctrl+B 显示/隐藏；页脚出现 `Sidebar ctrl+b` 提示 |
| 5 套主题可用 | ✅ | `BUILTIN_TUI_THEME_NAMES` 五项；`/theme` 选择器列表五项（含 opencode-dark、pi-dark） |

## 已知限制（有意留到第二批）

- diff 底色用 `rendering/diffs.py` 的 `DiffPalette` 默认值（opencode `base.diff`），**所有主题共用**；
  主题自带 diff 段要等 `ThemeTokens` 接线（`render_patch(tokens=...)` 参数已留好）。
- 工具行右侧 `+N −M · 4.2s` 计时渲染属 L3（spec §6），本批只有状态栏里的 tps/TTFT。
- 侧栏内部样式与 `extensions` 分区重复（`widgets/sidebar.py` 两处渲染）未动 —— 按计划单独核查后再改。
- `thinking_levels` 色带目前是全局默认（pi dark ramp）；主题级 `text.thinking_levels` 覆盖待 schema 消费接线。

## 全量闸门（本记录提交前实测）

- `uv run pytest -q --ignore=tests/coding/tui`：2201 passed, 52 skipped（Windows 已知 POSIX skip）
- `uv run pytest -q tests/coding/tui`：741 passed, 74 skipped
- `uv run ruff check .` / `uv run ruff format --check .`：All checks passed / formatted
- `scripts/check_import_graph.py`：OK（rendering/ 未引入 Textual）
- `scripts/check_structure.py`：OK（例外已记录：themes/__init__.py、sidebar.py、app.py 净缩小、全局 fan-out 53→54）
- `scripts/check_suppressions.py`：OK
- `uv run mypy`：仅剩 14 个已知 Windows fcntl 噪音（Linux CI 为 0）
