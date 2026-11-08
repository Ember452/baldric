# TUI 视觉系统重构设计（方案四：opencode 全量 schema + 双层投影）

**Status:** Design draft — awaiting review. **Not yet implemented.**

**Baseline:** `main` @ `3050518`（PR #63 merged）
**参数来源:** `opencode-dev/packages/tui/src/theme/assets/v2/opencode.json`（+ `opencode2.json`）
              `pi-main/packages/coding-agent/src/modes/interactive/theme/{dark,light}.json`
**相关已有资产:** `src/baldric_coding/rendering/{diffs,widths,grouping,thinking,approval_card}.py`（PR #63）

---

## 0. 这份设计要解决什么（一句话）

现在 `TuiTheme` 是 31 个扁平颜色 + 10 个 role，**没有"表面层级"**——所以卡片做不出来，每个组件只能硬编码色值，改来改去还是"简陋"。本设计把**数据层**升到 opencode 的完整 schema（色阶 + 语义 token 嵌套），**代码层**保持 `TuiTheme` 不变（它是扩展契约），中间加一个投影层。

## 1. 十个已确认的决定

| # | 决定 | 出处 |
|---|---|---|
| D1 | 卡片风格 = **混合**：opencode 的三级灰阶做卡片底，Pi 的色相区分角色，保留 `#a7f3f0` 作 accent | 用户 |
| D2 | 工具行 = **分级预算**：bash 5 行 / read 6 行 / edit·write 完整 patch；右上角 `+3 −1` + 耗时 | 用户 |
| D3 | 计时行 **默认显示在摘要右侧** | 用户 |
| D4 | picker 统一 = **opencode 无框面板**：150α 遮罩 + 无框 + 搜索行 + 整行高亮 + `●` 当前项 | 用户 |
| D5 | token 落地 = **扩展现有 JSON**（本设计细化成方案四：JSON 上 opencode 全量 schema，代码上双层） | 用户 + 复核后升级 |
| D6 | 侧栏 **默认收起，Ctrl+B 展开** | 用户 |
| D7 | 参数 **综合取两家**：色值优先 opencode hex，语义命名优先 pi | 用户 |
| D8 | 主题 **5 套**：baldric-dark / baldric-light / high-contrast / opencode-dark / pi-dark | 用户 |
| D9 | 布局常量 **照抄两家**，不自己发明；两家冲突时在本文档标注来源并选一个 | 用户 |
| D10 | 范围 **两批**：第一批 L1+L2，第二批 L3+L4+侧栏+剩余主题 | 用户 |

## 2. 为什么是"双层"，不是"直接换掉 TuiTheme"

**测量（已跑）：**

```
theme.* 引用       208 处 / 16 文件
  widgets/core.py 32, widgets/sidebar.py 38, themes/__init__.py 53, tui/app.py 25
  session/export/html.py 14          ← HTML 导出也依赖 TuiTheme
  extensions/api.py:                ← 扩展契约
    SlotWidgetFactory    = Callable[["TuiTheme"], "Widget"]
    SidebarWidgetFactory = Callable[["TuiTheme"], "Widget"]
    MainViewFactory      = Callable[["MainViewHandle", "TuiTheme"], "Widget"]
  extensions/builtins/subagents/ui/{strip,viewer}.py 18 处 theme.*
```

结论：**`TuiTheme` 已经是发给第三方扩展的公开契约**。直接改成嵌套结构会 break 所有已发布扩展。因此：

- **数据层**升级（`theme.json` 用 opencode schema）；
- **投影**出 `TuiTheme`（旧扁平视图，一行调用点都不改）和 `ThemeTokens`（新分层视图）；
- **新组件只用 `ThemeTokens`**；`TuiTheme` 标记 deprecated 但长期保留。

## 3. 架构

```
~/.baldric/themes/*.json  ──┐
builtin 5 套（opencode schema）─┤
                              ▼
                    tokens.py :: load_schema(json) -> ThemeSchema
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
   project_to_tui_theme(schema)        build_tokens(schema)
              │                               │
              ▼                               ▼
   TuiTheme（不变，208 处引用）         ThemeTokens（新，L2 组件用）
              │                               │
   theme_css_variables() / textual_theme   组件直接读
              │
   Textual CSS  $baldric-*
```

**关键不变量：**
1. `TuiTheme` 的字段名、含义、`TuiRoleStyle` 形状**完全不变**——扩展 API 零破坏。
2. `theme_css_variables()` 的变量名**完全不变**——所有 CSS 不用改。
3. 5 套主题走**同一份 schema 校验**——自定义主题与内置主题同格式（`set_custom_tui_themes` 顺势支持）。

## 4. L1：Token Schema（数据层）

### 4.1 Schema 结构（照抄 opencode，仅保留终端用得到的部分）

```jsonc
{
  "$schema": "...",
  "name": "opencode-dark",
  "appearance": "dark",
  "hue": {                                    // 色阶：opencode 全量，直接抄 hex
    "gray":   { "100": "#ffffff", "...": "...", "900": "#141414" },
    "red":    { ... }, "green": { ... }, "cyan": { ... },
    "blue":   { ... }, "purple": { ... }, "orange": { ... }
  },
  "text": {
    "base":           "$hue.gray.200",
    "muted":          "$hue.gray.400",
    "faint":          "$hue.gray.500",
    "thinking":       "$hue.gray.400",
    "feedback": { "error": {...}, "warning": {...}, "success": {...}, "info": {...} }
  },
  "background": {
    "base":   "$hue.gray.900",
    "raised": { "base": "$hue.gray.800", "high": "$hue.gray.700", "max": "$hue.gray.600" }
  },
  "border":    { "base": "$hue.gray.700", "accent": "$hue.purple.200", "muted": "$hue.gray.800" },
  "diff": {
    "text":       { "added": "#4fd6be", "removed": "#c53b53", "context": "#828bb8", "hunkHeader": "#828bb8" },
    "background": { "added": "#20303b", "removed": "#37222c", "context": "$hue.gray.800" },
    "highlight":  { "added": "#b8db87", "removed": "#e26a75" },
    "lineNumber": { "text": "#8f8f8f", "background": { "added": "#1b2b34", "removed": "#2d1f26" } }
  },
  "syntax":   { "comment": ..., "keyword": ..., "function": ..., "variable": ...,
                "string": ..., "number": ..., "type": ..., "operator": ..., "punctuation": ... },
  "markdown": { "text": ..., "heading": ..., "link": ..., "linkText": ..., "code": ...,
                "blockQuote": ..., "emphasis": ..., "strong": ..., "horizontalRule": ...,
                "listItem": ..., "listEnumeration": ... },
  "roles": {                                  // pi 的语义命名，值来自上面的 token
    "user":               { "border": "$hue.blue.200",   "body": "on $background.raised.base" },
    "assistant":          { "border": "$hue.cyan.200",   "body": "" },
    "tool":               { "border": "$hue.orange.200", "body": "on $background.raised.base" },
    "tool_success":       { "background": "$hue.green.700" },
    "tool_error":         { "background": "$hue.red.800" },
    "thinking":           { "border": "$hue.gray.600",   "body": "$hue.gray.400" },
    "error":              { "border": "$hue.red.200",    "body": "$hue.red.100" },
    "status":             { "border": "$hue.gray.600",   "body": "$hue.gray.300" },
    "skill":              { "border": "$hue.purple.200", "body": "$hue.purple.100" },
    "custom":             { "border": "$hue.cyan.200",   "body": "$background.raised.base" },
    "branch_summary":     { "border": "$hue.purple.200", "body": "$hue.purple.100" },
    "compaction_summary": { "border": "$hue.purple.200", "body": "$hue.purple.100" }
  },
  "syntax_theme": "ansi_dark"
}
```

**取值规则（D7）：**
- `hue.*` 一律抄 opencode 对应 mode 的 hex，**不改**。
- `diff.*` 一律抄 opencode `base.diff`，**不改**。
- `roles.*` 的**名字**用 pi 的（`user/tool/thinking/...`，和现有 `TRANSCRIPT_ROLES` 对齐），**值**由 hue 组合。
- `thinking` 7 级（`pi` 的 `thinkingOff→Max`）进入 `text.thinking_levels.*`，供 D2/边框色使用。

### 4.2 5 套主题的来源

| 主题名 | 数据来源 | 说明 |
|---|---|---|
| `baldric-dark` | **现有值为主**，缺的（`raised`/`diff`/`state`）从 opencode dark 抄 | 保留现有识别度（`#a7f3f0` accent），补齐层级 |
| `baldric-light` | 同上，补值从 opencode light 抄 | 现有 light 只有 flat，补亮色系层级 |
| `high-contrast` | 现有值 | 只补 schema 必备字段，视觉不变 |
| `opencode-dark` | **opencode.json 全量照搬** | 致敬皮肤，一个 hex 不改 |
| `pi-dark` | **pi dark.json 全量照搬**（okhsl → hex 转换） | 致敬皮肤；转换函数要单测 |

> **opench2.json 暂不做成主题**：它与 opencode.json 只差 `bg.base`（`neutral.900` vs `.800`），并入 `opencode-dark` 的一个变体不值得多维护一套文件。若后续需要，加文件即可（同 schema）。

### 4.3 兼容与校验

- `parse_tui_theme_json()`：**保留**，改为接受两种输入：
  - 旧格式（`colors`/`roles` flat）→ 内部映射成新 schema 再走统一路径（**兼容用户已有的自定义主题**）；
  - 新格式（`hue`/`text`/`background`/...）→ 直接校验。
- 校验规则沿用现有三条：`_TOP_LEVEL_FIELDS`（扩到新键）、`_RICH_STYLE_FIELDS`、`_RICH_ONLY_COLOR_FIELDS`。
- `$hue.*` / `$background.*` 引用解析在任何颜色校验**之前**完成（现有 `_substitute_vars` 的同款机制，扩成 `$a.b.c` 多级）。

## 5. L2：组件层（第一批产出，含验收截图）

### 5.1 消息卡片（D1 混合风）

改造点：`TranscriptMessageWidget._body_background` + `render_chat_item()` 的 `Table.grid` 左色条。

| 角色 | 底色 | 边框/左轨 | 依据 |
|---|---|---|---|
| user | `background.raised.base` | 左 1 列 `roles.user.border` | Pi `userMessageBg` 思路 + opencode `raised.base` 层级 |
| assistant | 无底 | 无 | 两家一致 |
| tool（pending） | `background.raised.base` | `roles.tool.border` | Pi `toolPendingBg` |
| tool（success） | `roles.tool_success.background` | 同上 | Pi `toolSuccessBg` = `green.700` |
| tool（error） | `roles.tool_error.background` | 同上 | Pi `toolErrorBg` = `red.800` |
| error | 无底 | `roles.error.border` | 现有 |
| thinking | 无底，`text.thinking` | `roles.thinking.border` | 现有 |

**布局常量（D9，照抄）：**
- 消息块外边距：`margin: 1 1 1 0`（**现有值，= pi `new Spacer(1)`，不改**）
- 块内左右 padding：`padding: 0 1 0 1`（**现有值，= pi `paddingX=1`，不改**）
- user 额外上下 padding：`(1, 0)`（**现有值，= pi `paddingY=1`，不改**）
- 结论：**现有布局常量已经是 Pi 的值**，这次只换色，不动间距。

### 5.2 工具行（D2 分级预算 + D3 计时）

改动点：`tui/state.py` 的 4 个预览常量 + `widgets/core.py` 的 `_render_tool_chat_body`。

```
新常量（替换现有的 8 / 32 / 120）：
  TOOL_BASH_PREVIEW_LINES      = 5      ← 抄 pi 的 BASH_PREVIEW_LINES
  TOOL_READ_PREVIEW_LINES      = 10     ← 抄 pi 与 opencode 一致值（10），不自创
  TOOL_PATCH_PREVIEW_LINES     = 全部    ← edit/write 的 patch 不截断（D2 要求）
  TERMINAL_OUTPUT_PREVIEW_LINES = 120   ← 现有值保留（终端命令输出另属一类）
```

**摘要行右侧**（D3）：`<tool> <path>` + `+3 −1`（来自 diff `summarize_preview_changes`，已有）+ `4.2s`（来自 `item.started_at`）。三段之间用 `·` 分隔，全部 `text.muted`。

**折叠尾巴**：`… (N earlier lines · Ctrl+O)`——文案取 pi 的 `(N earlier lines, ctrl+o to expand)` 精简（本项目按键名不同）。

### 5.3 diff 高亮（"回复高亮"）

改动点：`rendering/diffs.py` 的 `_line_text()` 加整行底色。

- 增行：整行 `diff.background.added`，行号列 `diff.lineNumber.background.added`，文本 `diff.text.added`
- 删行：同构，用 `removed`
- 上下文：`diff.background.context`
- hunk 头：`diff.text.hunkHeader`
- 词级高亮：`diff.highlight.added/removed`（现有 `bold` 改成 `bold <color>`）

**这是纯增量**：现有 `DiffLine` 结构不变，只加渲染时的背景段。

### 5.4 输入区 + 状态行

- prompt：保留现有上下两条 `border-top/bottom`，**边框色改成 `thinking` 等级色**（D2 的副产品，Pi 同款：`thinkingOff→Max` 7 色）。
- 状态行：现有 `#compact-session-info` 从"N 行"合并成**一行**：`cwd · model · 12k/200k (6%) · $1.24 · 40 tps · TTFT 1.2s`。数据全部来自现有 `session.session_stats`，零新查询。

### 5.5 侧栏（D6）

- 默认 `-hide-sidebar` 类（现有机制已有 `_update_responsive_layout` / `_sidebar_visibility_override`）。
- 绑定 `Ctrl+B`（现有 `TOGGLE_SIDEBAR` 已走通，只需补默认关闭 + keybind）。
- **第一批只做"默认收起"，不改侧栏内部样式**；样式重构放第二批。

## 6. L3：交互层（第二批）

| 项 | 做法 | 依据 |
|---|---|---|
| **spinner** | `ACTIVITY_SPINNER_FRAMES` 换成 `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`，80ms | opencode `SPINNER_FRAMES` + pi `loader.ts` 完全一致 |
| **思考点击展开** | 隐藏态摘要行改为可点击 widget（`on_click` → 就地展开该块）；流式进行中**不可点**（只显示摘要），结束后可点 | 用户要求；边界原因见 §10 |
| **hover/focus/selected** | `state.hovered/focused/selected` token 接到 list item / completion / picker 行 | opencode `action.$hovered` |
| **工具状态切换** | pending → success/error 时整行底色渐变（Textual 无 alpha，用 2–3 帧色阶过渡） | Pi 三态底色 |
| **流式收敛** | 代码栅栏闭合瞬间从纯文本切 rich 渲染（现有 `StreamingTranscriptMessageWidget` 已有基础） | 用户要求"回复高亮" |

**明确不做**（opencode 独有、Textual 画不出）：`title-shimmer` 扫光、单格 alpha glow、逐字符 RGBA 渐变。

## 7. L4：一致性层（第二批）

- 30 个 `ModalScreen` 统一到 `PickerShell` 基类：`align: center middle` → 150α 遮罩（`background: $baldric-scrim`）→ 无边框面板（`background: surface.raised.high`）→ 标题 + 搜索 + 列表三段。
- 30 个里**只有一部分有搜索**（session/model/skill/tree），其余是 confirm/input 型——按类型分两个基类：`PickerShell`（列表+搜索）和 `DialogShell`（标题+内容+按钮）。
- 删除现有的 `border: tall $baldric-border` 逐处定义。

## 8. 影响面清单（改之前必须看过的）

| 文件 | 为什么 | 第一批/第二批 |
|---|---|---|
| `rendering/themes/__init__.py` | schema 解析 + 投影 + CSS 变量 | 一 |
| `rendering/themes/*.json`（3→5 个） | 数据 | 一（dark/light/hc）+ 二（两套致敬皮肤） |
| `rendering/diffs.py` | 整行底色 | 一 |
| `tui/state.py` | 预览常量 | 一 |
| `tui/widgets/core.py` | 卡片底色 + 工具行 + 状态行 | 一 |
| `tui/app.py` | prompt 边框色 + 侧栏默认 + **208 处 theme.* 中 25 处** | 一（部分）+ 二 |
| `session/export/html.py` | **14 处 theme.***，HTML 导出也要跟着变 | 一（只保证不破，不重设计） |
| `extensions/builtins/subagents/ui/{strip,viewer}.py` | **18 处 theme.***，扩展 UI 会跟着变色 | 一（自动受益，不改代码） |
| `extensions/api.py` | 3 个工厂签名**不能变** | 一（只加不改） |
| 30 个 `screens/*.py` + `backends.py` + `trust.py` | L4 统一壳 | 二 |
| `tui/widgets/sidebar.py` | 38 处 theme.* + 分区样式 | 二 |
| `tests/coding/tui/test_tui_themes.py`（294 行） | 主题断言会大面积变 | 一（重写断言到新 token） |
| `tests/coding/tui/test_tui_config.py`（28 处） | 同上 | 一 |
| `tests/coding/session/test_session_export.py` | HTML 导出颜色断言 | 一（若断言了具体色值） |

## 9. 验收标准

**第一批（L1+L2）——硬指标：**
1. `uv run pytest -q tests/coding/tui tests/coding/rendering tests/coding/session` 全绿；新 `test_theme_schema.py` 覆盖 5 套主题解析 + 旧格式兼容 + 坏数据诊断。
2. `uv run ruff check . && ruff format --check . && mypy` 不新增错误（Windows fcntl 噪音除外）。
3. 三个棘轮（structure / suppressions / import-graph）不破。
4. **视觉验收（人眼）**：用 headless 截图（`export_screenshot` + 现有 PNG 管线）出 4 张图——对话页（含 edit diff、bash 输出、thinking 折叠）/ 会话选择器 / 模型选择器 / 浅色主题，与 opencode+pi 参照并排对比。
5. **回归**：`TuiTheme` 字段一个没少（写个测试断言 `fields(TuiTheme)` 集合与 main 完全相同）；`theme_css_variables()` 的键集合完全相同。

**第二批（L3+L4）——硬指标：**
1. 30 个 screen 全部迁到 `PickerShell`/`DialogShell`，`grep -r "border: tall \$baldric-border" src/` 为空。
2. 思考块点击展开有单元测试（流式中不可点、结束后可点）。
3. spinner 帧与间隔有测试断言。
4. 5 套主题全部通过 schema 校验，`/theme` 切换后即时生效。

## 10. 风险与已知边界

| 风险 | 对策 |
|---|---|
| 改 schema 可能悄悄改变现有 3 套主题的观感 | 用"旧值投影"对照测试：新 schema 解析后投影出的 `TuiTheme` 必须与 main 的 3 个 JSON 逐字段相等（除新增字段） |
| `pi-dark` 的 okhsl → hex 转换有精度损失 | 转换函数单测覆盖全部 token；误差容忍 ±1/255 |
| 30 处源码里 208 个 `theme.*` 引用可能被漏改 | 分批 grep 清单逐文件勾选；`mypy` 兜底（字段不存在会报错） |
| 思考点击展开在流式中引发重绘闪烁 | 明确"流式中不可点"，见 §6 |
| Textual 无 alpha，opencode 的 150α 遮罩怎么做 | **全部用预混合色**（opencode 遮罩 = `bg.base` × 0.75 叠在 `bg.base` 上，算出固定 hex），不用 `opacity` CSS。原因：Textual 的 `opacity` 会连带影响子组件重绘，且在不同终端渲染不一致。预混合色是确定性的，也便于 golden 测试。`ThemeTokens` 暴露 `scrim` 字段承载该值。 |

## 11. 实施顺序（两批，不并行）

```
第一批
  T1  schema 定义 + 解析 + 投影 + 5 套 JSON 骨架  （含旧格式兼容测试）
  T2  旧值等价对照测试（3 套主题投影 == main）
  T3  diff 整行底色（diffs.py + 测试）
  T4  工具行分级预算 + 计时（state.py + core.py + 测试）
  T5  消息卡片底色（core.py）
  T6  状态行合并 + prompt 边框色
  T7  侧栏默认收起 + Ctrl+B
  T8  截图对比 + 人工验收
第二批
  T9   PickerShell / DialogShell + 30 screen 迁移
  T10  思考点击展开
  T11  spinner / hover 状态 / 工具状态过渡
  T12  侧栏内部样式重构
  T13  两套致敬皮肤（opencode-dark 全量、pi-dark 转换）
```

## 12. 明确不做

- 不做 prompt_toolkit / scrollback 前端（PR #63 已排除）。
- 不做 opencode 的 shimmer / 逐格 alpha 动效。
- 不改 `baldric_agent` / `baldric_ai`（本设计完全在 `baldric_coding` 层）。
- 不改 `TuiTheme` 的公开字段形状（扩展契约）。
- 不给 `rendering/` 加 Textual 依赖（CI 强制）。
