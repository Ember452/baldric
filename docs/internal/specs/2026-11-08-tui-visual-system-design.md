# TUI 视觉系统重构设计（方案四：opencode 全量 schema + 双层投影）

**Status:** Design draft — awaiting review. **Not yet implemented.**

**Baseline:** `main` @ `752281c` / **v0.3.0**（PR #63 + #65 agent-kernel-parity + #66 MCP client 均已合并）
**参数来源:** `opencode-dev/packages/tui/src/theme/assets/v2/opencode.json`（+ `opencode2.json`）
              `pi-main/packages/coding-agent/src/modes/interactive/theme/{dark,light}.json`
**相关已有资产:** `src/baldric_coding/rendering/{diffs,widths,grouping,thinking,approval_card}.py`（PR #63）

> **本版按 v0.3.0 重新核对过。** 上一版写于 PR #63 时点（v0.2.3），此后 10 小时内合并了
> PR #65（新增 `baldric_protocol` 包 + agent kernel parity）与 PR #66（新增 `baldric_mcp` 包），
> 文件规模、主题模块结构、包分层都已变化。**§14 记录本次核对的实际数值与修正项**；
> 凡本版与前版数字冲突，以本版为准（均来自实测，不是估算）。

---

## 0. 这份设计要解决什么（一句话）

现在 `TuiTheme` 是 **31 个扁平颜色 + 10 个 role**，**没有"表面层级"**——所以卡片做不出来，每个组件只能硬编码色值，改来改去还是"简陋"。本设计把**数据层**升到 opencode 的完整 schema（色阶 + 语义 token 嵌套），**代码层**保持 `TuiTheme` 不变（它是扩展契约），中间加一个投影层。

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

**测量（v0.3.0 实测，2026-11-08）：**

```
theme.* 引用       208 处 / 16 文件（与 v0.2.3 相同，未增长）
  widgets/core.py 32, widgets/sidebar.py 38, themes/__init__.py 27, tui/app.py 25
  session/export/html.py 14          ← HTML 导出也依赖 TuiTheme
  extensions/api.py:                ← 扩展契约（3 个工厂，签名未变）
    SlotWidgetFactory    = Callable[["TuiTheme"], "Widget"]      (:183)
    SidebarWidgetFactory = Callable[["TuiTheme"], "Widget"]      (:193)
    MainViewFactory      = Callable[["MainViewHandle", "TuiTheme"], "Widget"]  (:196)
  extensions/builtins/subagents/ui/{strip,viewer}.py 9+9=18 处 theme.*
```

结论：**`TuiTheme` 已经是发给第三方扩展的公开契约**。直接改成嵌套结构会 break 所有已发布扩展。因此：

- **数据层**升级（`theme.json` 用 opencode schema）；
- **投影**出 `TuiTheme`（旧扁平视图，一行调用点都不改）和 `ThemeTokens`（新分层视图）；
- **新组件只用 `ThemeTokens`**；`TuiTheme` 标记 deprecated，**v0.3.x 期间兼容，v1.0 删除**（见 §13）。

## 3. 架构

### 3.1 包分层（v0.3.0 现实，CI 由 `scripts/check_import_graph.py` 强制）

```
baldric_protocol   最底层 wire 契约：消息模型 / 工具契约 / 助手流事件 / session entries
   ▲   ▲   ▲   ▲   （只依赖 pydantic；不 import 任何上层包）
   │   │   │   └──────────── baldric_mcp      MCP client（工具适配 + 连接管理）
   │   │   └──────────────── baldric_ai       provider 适配 / 流解析
   │   └──────────────────── baldric_agent    agent loop / 事件 / 工具编排
   └──────────────────────── baldric_coding   CLI / TUI / extensions / commands
```

**对本文档的关键含义（三条，v0.3.0 新增）：**

1. **`baldric_protocol` 拥有消息模型与助手流事件**（`messages.py` / `tools.py` / `provider_events.py`），但 **高层 `AgentEvent` 仍在 `baldric_agent/events.py`**（`grep AgentEvent` 在 protocol 内零命中）。所以 **TUI 消费的事件边界仍是 `baldric_agent.events.AgentEvent`**，其字段引用 protocol 的消息/工具类型。
2. **`baldric_mcp` 不直接 import 进 coding 内部**：MCP 工具经内置扩展 `baldric_coding/extensions/builtins/mcp/extension.py:153 _api.register_tool(...)` 注册，走 `extensions/runtime.py:1105 bind_live_tools()` 的 live-registration seam。**它不新增任何 `Screen`**（已核，见 §8）。
3. **禁止反向 import**：`baldric_protocol` 不得 import agent/ai/coding/mcp/textual/rich；`baldric_agent`/`baldric_ai` 不得 import `baldric_mcp`（"harness and providers must not learn MCP exists"）。本设计的所有改动都在 `baldric_coding` 内，不触碰这些边界。

### 3.2 主题数据流（本设计新增）

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
   （v0.3.0 实测：`TuiTheme` 共 **35** 个字段，其中 **31** 个是 color 字段——比 v0.2.3 多 1 个，见 §14。）
2. `theme_css_variables()` 的变量名**完全不变**——所有 CSS 不用改。
   （v0.3.0 实测：**32** 个变量，含 25 个 `baldric-*` + 7 个 `footer-*`。新增 token **不得**删除或重命名任何现有变量。）
3. 5 套主题走**同一份 schema 校验**——自定义主题与内置主题同格式（`set_custom_tui_themes` 顺势支持）。

### 3.3 数据真相（v0.3.0 澄清，重要）

`plans/adr-0003-transcript-as-truth.md` 是 **Declined（暂不采纳）**，**transcript-as-truth 没有落地**。因此：

- 渲染状态来源仍是 **`TuiEventAdapter.apply(event)` → `TuiState` → widget**（事件投影），**不是**从持久化 transcript 回放。
- 数据链实现点（给实现时定位用）：
  - `tui/adapter.py:74 apply()` → `tui/app.py:2510/2549 adapter.apply(event)`
  - `tui/app.py:3590 transcript.update_from_state(state, theme)` → `widgets/core.py:750` → `_redraw()` 逐条 `TranscriptMessageWidget(item, ...)`
- **含义**：L2 的卡片/工具行/思考块只需读 `TuiState` 里的 `ChatItem` 字段（字段清单见 §5），**不需要引入新的数据层**。若日后 ADR-0003 重开并落地 wire 变更，§5 的数据来源需要重审（ADR 里已写明重开触发条件）。

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

**v0.3.0 实测：校验逻辑全部仍在 `src/baldric_coding/rendering/themes/__init__.py`（446 行），没有搬去别的模块。** 文件从 v0.2.3 的 1850 行缩到 446 行，是被拆过，但**校验相关的符号一个不少**，全部还在原处：

```
_tools/_TOP_LEVEL_FIELDS  (:105)
_RICH_STYLE_FIELDS        (:109)
_RICH_ONLY_COLOR_FIELDS   (:121)
_RICH_STYLE_KEYWORDS      (:127)
parse_tui_theme_json()    (:159)  ← 统一入口
_parse_name/_parse_vars/_substitute_vars/_parse_colors/_parse_roles
_color_problem/_textual_color_problem/_textual_style_colors_problem/_style_problem
_parse_dark/_is_dark_background/_parse_syntax_theme
_load_builtin_theme()     (:373)  BALDRIC_DARK_THEME/BALDRIC_LIGHT_THEME/HIGH_CONTRAST_THEME
theme_css_variables()     (:428)  textual_theme_for_tui_theme() (:408)
```

实现要求：

- `parse_tui_theme_json()`：**保留**，改为接受两种输入：
  - 旧格式（`colors`/`roles` flat）→ 内部映射成新 schema 再走统一路径（**兼容用户已有的自定义主题**）；
  - 新格式（`hue`/`text`/`background`/...）→ 直接校验。
- 校验规则沿用现有三条：`_TOP_LEVEL_FIELDS`（扩到新键）、`_RICH_STYLE_FIELDS`、`_RICH_ONLY_COLOR_FIELDS`。
- `$hue.*` / `$background.*` 引用解析在任何颜色校验**之前**完成（现有 `_substitute_vars` 的同款机制，扩成 `$a.b.c` 多级）。

> **注意**：`themes/__init__.py` 的 446 行是**拆分后的现状**。动手前必须重新读一遍它，
> 确认 `parse_tui_theme_json` 内部逻辑没有在拆分中改变语义（尤其 `_parse_colors` 的
> 双库校验：Rich 接受但 Textual 拒绝的颜色要在加载时报诊断，不能拖到应用主题时崩）。

## 5. L2：组件层（第一批产出，含验收截图）

### 5.0 数据来源（v0.3.0 实测，实现时按此取数）

渲染时**不新增数据层**，全部从 `TuiState` 的 `ChatItem` / `GroupedToolCall` 读：

| 需要的数据 | 字段 | 来源 |
|---|---|---|
| 工具名 / 参数 | `ChatItem.tool_name` / `.tool_arguments`，分组用 `GroupedToolCall.tool_name` / `.tool_arguments` | `ToolExecutionStartEvent.tool_name/args` |
| 结果文本 | `ChatItem.tool_result_text`（预览）/ `.tool_result_full_text`（全文）/ `.tool_result` | `state.record_tool_result(...)` (:631) |
| 是否失败 | **没有显式 bool**：`tool_result_text.startswith("✗")` / `"✓"`（`format_tool_result_block` 决定）；`record_tool_result` 收到 `is_error` 后拼进文本 | 同上 |
| 开始时间（算耗时） | `ChatItem.started_at` / `GroupedToolCall.started_at`（`time.monotonic()`），结果落地时置 `None` | `resolve_tool_invocation` (:267) 现算 `monotonic() - started_at` |
| 思考文本 | `ChatItem(role="thinking").text` | `add_thinking_delta` / `add_assistant_message` |
| 思考 token 数 | `format_hidden_thinking_summary(texts)` 内 `estimate_text_tokens`（**估算**，仅隐藏态显示） | `rendering/thinking.py:19` |

> **注意（给 D2 的实现警告）**：现在"是否失败"是靠**文本首字符**判断的，不是结构化字段。
> 如果 D2 要给工具行整行着色，**必须沿用这个约定或先把它结构化**（改 `ChatItem` 加字段属于
> L2 范围内的小改动，要在实现时显式决定，不能默默依赖 `startswith("✗")`）。

### 5.1 消息卡片（D1 混合风）

改造点：`TranscriptMessageWidget` 的 `self.styles.background`（:293）与 `_chat_item_role_style()`。
**注意**：TUI 实际渲染走 `TranscriptMessageWidget`（`widgets/core.py:219`），**不是** `render_chat_item()`
（后者只给非交互/测试路径用，返回 Rich `Padding(Table.grid)`）。两处都要改，否则 print 模式与 TUI 不一致。

| 角色 | 底色 | 边框/左轨 | 依据 |
|---|---|---|---|
| user | `background.raised.base` | 左 1 列 `roles.user.border` | Pi `userMessageBg` 思路 + opencode `raised.base` 层级 |
| assistant | 无底 | 无 | 两家一致（**且 `_BORDERLESS_TRANSCRIPT_ROLES` 已排除 assistant/thinking 设背景**，见 :68） |
| tool（pending） | `background.raised.base` | `roles.tool.border` | Pi `toolPendingBg` |
| tool（success） | `roles.tool_success.background` | 同上 | Pi `toolSuccessBg` = `green.700` |
| tool（error） | `roles.tool_error.background` | 同上 | Pi `toolErrorBg` = `red.800` |
| error | 无底 | `roles.error.border` | 现有 |
| thinking | 无底，`text.thinking` | `roles.thinking.border` | 现有 |

**布局常量（D9，照抄；v0.3.0 实测仍在原处，不改）：**
- 消息块外边距：`margin: 1 1 1 0`（`widgets/core.py:226`，**现有值，= pi `new Spacer(1)`，不改**）
- 块内左右 padding：`padding: 0 1 0 1`（`widgets/core.py:232`，**现有值，= pi `paddingX=1`，不改**）
- user 额外上下 padding：`(1, 0)`（`widgets/core.py:284`，**现有值，= pi `paddingY=1`，不改**）
- 结论：**现有布局常量已经是 Pi 的值**，这次只换色，不动间距。

### 5.2 工具行（D2 分级预算 + D3 计时）

改动点：`tui/state.py` 的预览常量（v0.3.0 实测现值：`TOOL_RESULT_PREVIEW_LINES=8`、
`TOOL_PATCH_PREVIEW_LINES=32`、`TERMINAL_COMMAND_OUTPUT_PREVIEW_LINES=120`，见 :44/:45/:49）
+ `widgets/core.py` 的 `_render_tool_chat_body`。

```
新常量（替换现有的 8 / 32）：
  TOOL_BASH_PREVIEW_LINES      = 5      ← 抄 pi 的 BASH_PREVIEW_LINES
  TOOL_READ_PREVIEW_LINES      = 10     ← 抄 pi 与 opencode 一致值（10），不自创
  TOOL_PATCH_PREVIEW_LINES     = 全部    ← edit/write 的 patch 不截断（D2 要求）
  TERMINAL_COMMAND_OUTPUT_PREVIEW_LINES = 120  ← 现有值保留（终端命令输出另属一类）
```

> **实现警告**：现有 `TOOL_RESULT_PREVIEW_LINES` 是**所有工具共用一个值**（read/bash/其它都走它）。
> D2 要分级，必须**按工具名分派**，不能只改一个常量——这属于 L2 里"改结构不只是改数字"的一项，
> 实现时要把 `_preview_text` 的调用点全部找齐（`:930` `:937` `:962` 附近）。

**摘要行右侧**（D3）：`<tool> <path>` + `+3 −1`（来自 diff `summarize_preview_changes`，已有）+ `4.2s`（来自 `item.started_at`）。三段之间用 `·` 分隔，全部 `text.muted`。

**折叠尾巴**：`… (N earlier lines · Ctrl+O)`——文案取 pi 的 `(N earlier lines, ctrl+o to expand)` 精简（本项目按键名不同）。

### 5.3 diff 高亮（"回复高亮"）

改动点：`rendering/diffs.py` 的 `_line_text()`(:244) / `_render_single_line()`(:233) 加整行底色。

- 增行：整行 `diff.background.added`，行号列 `diff.lineNumber.background.added`，文本 `diff.text.added`
- 删行：同构，用 `removed`
- 上下文：`diff.background.context`
- hunk 头：`diff.text.hunkHeader`
- 词级高亮：`diff.highlight.added/removed`（现有 `bold` 改成 `bold <color>`）

**这是纯增量**：`render_patch()`(:164) 返回 `Group` of `Text`，`DiffLine` 结构不变，只给每行 `Text`
加 `style`/背景即可。行号 gutter 已由 `_gutter()`(:158) 生成，不用重写。

### 5.4 输入区 + 状态行

- prompt：保留现有上下两条 `border-top/bottom`，**边框色改成 `thinking` 等级色**（D2 的副产品，Pi 同款：`thinkingOff→Max` 7 色）。
- 状态行：现有 `#compact-session-info` 从"N 行"合并成**一行**：`cwd · model · 12k/200k (6%) · $1.24 · 40 tps · TTFT 1.2s`。数据全部来自现有 `session.session_stats`，零新查询。

### 5.5 侧栏（D6）

- 默认 `-hide-sidebar` 类（现有机制已有 `_update_responsive_layout` / `_sidebar_visibility_override`）。**v0.3.0 实测现状**：侧栏是**响应式**的——`SIDEBAR_MIN_WIDTH = 96`（`app.py:360`），宽度 ≥96 且高度够就默认显示。D6 要把它改成"默认收起，需 Ctrl+B 显式打开"。
- 绑定 `Ctrl+B`（现有 `TOGGLE_SIDEBAR` 命令与 `_toggle_sidebar_visibility()` 已走通，只需补默认关闭 + keybind）。
- **第一批只做"默认收起"，不改侧栏内部样式**；样式重构放第二批。
- **v0.3.0 实测**：侧栏分区从 8 个变成 **9 个**（多了 `compaction`，见 `widgets/sidebar.py:421`），
  且 `extensions` 分区出现两次（:211 一处早期结构、:355 一处）。第二批做侧栏重构时要先澄清这个重复。

## 6. L3：交互层（第二批）

| 项 | 做法 | 依据 |
|---|---|---|
| **spinner** | `ACTIVITY_SPINNER_FRAMES` 换成 `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`，80ms。**v0.3.0 实测现值是 8 帧 braille `⣾⣽⣻⢿⡿⣟⣯⣷`、`ACTIVITY_TICK_SECONDS=0.15`（150ms）** | opencode `SPINNER_FRAMES` + pi `loader.ts` 完全一致 |
| **思考点击展开** | 隐藏态摘要行改为可点击 widget（`on_click` → 就地展开该块）；流式进行中**不可点**（只显示摘要），结束后可点。**已有可复用件**：`widgets/sidebar.py:23` 已 import `textual.widgets.Collapsible`；`TuiState` 已有 `show_thinking` / `update_thinking_visibility()`（`widgets/core.py:770`） | 用户要求；边界原因见 §10 |
| **hover/focus/selected** | `state.hovered/focused/selected` token 接到 list item / completion / picker 行 | opencode `action.$hovered` |
| **工具状态切换** | pending → success/error 时整行底色渐变（Textual 无 alpha，用 2–3 帧色阶过渡） | Pi 三态底色 |
| **流式收敛** | 代码栅栏闭合瞬间从纯文本切 rich 渲染（现有 `StreamingTranscriptMessageWidget` 已有基础） | 用户要求"回复高亮" |

**明确不做**（opencode 独有、Textual 画不出）：`title-shimmer` 扫光、单格 alpha glow、逐字符 RGBA 渐变。

## 7. L4：一致性层（第二批）

- 30 个 `ModalScreen` 统一到 `PickerShell` 基类：`align: center middle` → 150α 遮罩（`background: $baldric-scrim`）→ 无边框面板（`background: surface.raised.high`）→ 标题 + 搜索 + 列表三段。
- 30 个里**只有一部分有搜索**（session/model/skill/tree），其余是 confirm/input 型——按类型分两个基类：`PickerShell`（列表+搜索）和 `DialogShell`（标题+内容+按钮）。
- 删除现有的 `border: tall $baldric-border` 逐处定义。

## 8. 影响面清单（改之前必须看过的）

> **v0.3.0 实测行数/引用数已更新。** 任何一行都要在动手前重新 `git grep` 确认，不能凭本表。
> 特别提醒：`baldric_protocol` / `baldric_mcp` 是 v0.3.0 新增的两个包，
> 已核实**都不引用 Textual/rich/TuiTheme**，本设计不改它们；`baldric_mcp` 也不新增任何 Screen。

| 文件 | 为什么 | v0.3.0 实测 | 第一批/第二批 |
|---|---|---|---|
| `rendering/themes/__init__.py` | schema 解析 + 投影 + CSS 变量 | **446 行**，`theme.*` 27 处 | 一 |
| `rendering/themes/*.json`（3→5 个） | 数据 | 现有 3 个：`baldric-dark / baldric-light / high-contrast` | 一（dark/light/hc）+ 二（两套致敬皮肤） |
| `rendering/diffs.py` | 整行底色 | `render_patch()` :164 / `_line_text()` :244 | 一 |
| `tui/state.py` | 预览常量 + 工具行数据 | **1034 行**，常量 :44/:45/:49 | 一 |
| `tui/widgets/core.py` | 卡片底色 + 工具行 + 状态行 | **1944 行**，`render_chat_item` :1545 / `TranscriptMessageWidget` :219 | 一 |
| `tui/app.py` | prompt 边框色 + 侧栏默认 + spinner | **4589 行**，`SIDEBAR_MIN_WIDTH` :360 | 一（部分）+ 二 |
| `session/export/html.py` | **14 处 theme.***，HTML 导出也要跟着变 | **1846 行** | 一（只保证不破，不重设计） |
| `extensions/builtins/subagents/ui/{strip,viewer}.py` | **9+9=18 处 theme.*** | 确认 | 一（自动受益，不改代码） |
| `extensions/api.py` | 3 个工厂签名**不能变** | :183 / :193 / :196 | 一（只加不改） |
| `baldric_protocol/`、`baldric_mcp/` | 新增两个包 | **零 Textual/rich/TuiTheme 引用；不改** | — |
| `plans/adr-0003-transcript-as-truth.md` | 数据真相决策 | **Declined**，见 §3.3 | 一（只读，不改设计） |
| 30 个 `screens/*.py` + `backends.py` + `trust.py` | L4 统一壳 | **30 个 Screen 类**（`screens/` 22 + `backends.py` 7 + `trust.py` 1） | 二 |
| `tui/widgets/sidebar.py` | 分区样式 | **9 个分区**（含 `compaction`，且 `extensions` 出现两次，需澄清） | 二 |
| `tests/coding/tui/test_tui_themes.py` | 主题断言会大面积变 | **408 行**（v0.2.3 是 294） | 一（重写断言到新 token） |
| `tests/coding/tui/test_tui_config.py` | 同上 | 28 处 theme 断言 | 一 |
| `tests/coding/tui/`（全目录） | TUI 回归面 | **22 文件 / 18935 行**（v0.2.3 是 14934） | 一 + 二 |
| `tests/coding/session/test_session_export.py` | HTML 导出颜色断言 | 若断言了具体色值则要更新 | 一 |

## 9. 验收标准

**第一批（L1+L2）——硬指标：**
1. `uv run pytest -q tests/coding/tui tests/coding/rendering tests/coding/session` 全绿；新 `test_theme_schema.py` 覆盖 5 套主题解析 + 旧格式兼容 + 坏数据诊断。
2. `uv run ruff check . && ruff format --check . && mypy` 不新增错误（Windows fcntl 噪音除外）。
3. 三个棘轮（structure / suppressions / import-graph）不破。**特别地：`check_import_graph.py` 必须仍然 OK**——本设计不得让 `rendering/` 引入 Textual，也不得让 protocol/mcp 反向依赖。
4. **视觉验收（人眼）**：用 headless 截图（`export_screenshot` + 现有 PNG 管线）出 4 张图——对话页（含 edit diff、bash 输出、thinking 折叠）/ 会话选择器 / 模型选择器 / 浅色主题，与 opencode+pi 参照并排对比。
5. **回归**：`TuiTheme` 字段一个没少（写个测试断言 `fields(TuiTheme)` 集合与当前 main **完全相同**，v0.3.0 是 35 个）；`theme_css_variables()` 的键集合完全相同（v0.3.0 是 32 个）。

**第二批（L3+L4）——硬指标：**
1. 30 个 screen 全部迁到 `PickerShell`/`DialogShell`，`grep -r "border: tall \$baldric-border" src/` 为空。
2. 思考块点击展开有单元测试（流式中不可点、结束后可点）。
3. spinner 帧与间隔有测试断言。
4. 5 套主题全部通过 schema 校验，`/theme` 切换后即时生效。

## 10. 风险与已知边界

| 风险 | 对策 |
|---|---|
| 改 schema 可能悄悄改变现有 3 套主题的观感 | 用"旧值投影"对照测试：新 schema 解析后投影出的 `TuiTheme` 必须与当前 3 个 JSON 逐字段相等（除新增字段） |
| `pi-dark` 的 okhsl → hex 转换有精度损失 | 转换函数单测覆盖全部 token；误差容忍 ±1/255 |
| 源码里 208 个 `theme.*` 引用可能被漏改 | 分批 grep 清单逐文件勾选；`mypy` 兜底（字段不存在会报错） |
| 思考点击展开在流式中引发重绘闪烁 | 明确"流式中不可点"，见 §6 |
| **"工具是否失败"靠 `startswith("✗")` 判断** | D2 要给工具行整行着色时，必须结构化（给 `ChatItem` 加字段）或明确沿用该约定；不能默默依赖字符串前缀 |
| **`themes/__init__.py` 从 1850 行缩到 446 行** | 动手前重读，确认拆分没改变 `parse_tui_theme_json` 的语义（尤其双库颜色校验） |
| Textual 无 alpha，opencode 的 150α 遮罩怎么做 | **全部用预混合色**（opencode 遮罩 = `bg.base` × 0.75 叠在 `bg.base` 上，算出固定 hex），不用 `opacity` CSS。原因：Textual 的 `opacity` 会连带影响子组件重绘，且在不同终端渲染不一致。预混合色是确定性的，也便于 golden 测试。`ThemeTokens` 暴露 `scrim` 字段承载该值。 |

## 11. 实施顺序（两批，不并行）

```
T0  动手前必读（v0.3.0 新增，不可跳过）
    - rendering/themes/__init__.py 全文（446 行，确认拆分未改语义）
    - plans/adr-0003-transcript-as-truth.md（确认 Declined，渲染仍走事件投影）
    - src/baldric_protocol/{__init__,messages,tools,provider_events}.py（渲染读的消息/工具/流事件类型来源）
    - src/baldric_coding/tui/adapter.py + state.py 的 ChatItem / GroupedToolCall 字段
    - scripts/check_import_graph.py（层方向红线）
    产出：一份"当前实际调用点清单"，与 §8 对照；有差异先改 §8 再动手

第一批
  T1  schema 定义 + 解析 + 投影 + 5 套 JSON 骨架  （含旧格式兼容测试）
  T2  旧值等价对照测试（现有 3 套主题投影 == 现状，逐字段）
  T3  diff 整行底色（diffs.py + 测试）
  T4  工具行分级预算 + 计时（state.py 按工具名分派 + core.py + 测试）
  T5  消息卡片底色（core.py 的 TranscriptMessageWidget，不是 render_chat_item）
  T6  状态行合并 + prompt 边框色
  T7  侧栏默认收起 + Ctrl+B
  T8  截图对比 + 人工验收
第二批
  T9   PickerShell / DialogShell + 30 screen 迁移
  T10  思考点击展开
  T11  spinner / hover 状态 / 工具状态过渡
  T12  侧栏内部样式重构（先澄清 extensions 分区重复）
  T13  两套致敬皮肤（opencode-dark 全量、pi-dark 转换）
```

## 12. 明确不做

- 不做 prompt_toolkit / scrollback 前端（PR #63 已排除）。
- 不做 opencode 的 shimmer / 逐格 alpha 动效。
- 不改 `baldric_agent` / `baldric_ai`（本设计完全在 `baldric_coding` 层）。
- **不改 `baldric_protocol` / `baldric_mcp`**（v0.3.0 新增的两个底层包；本设计不触碰，且它们不得引用 Textual/rich）。
- 不给 `rendering/` 加 Textual 依赖（CI 强制）。
- **不采纳 transcript-as-truth**（`plans/adr-0003-transcript-as-truth.md` 是 Declined，见 §3.3）。

---

## 13. `TuiTheme` 的迁移路线：v0.3.x 过渡，v1.0 删除

> **⚠ 本节已作废（2026-11-09）。** 下文 13.1–13.6 描述的"`TuiTheme` → `ThemeTokens` 迁移、v1.0 删 `TuiTheme`"方案依赖一个**从未被消费的 `ThemeTokens` 层**。实施第二批后复查：`build_tokens`/`ThemeTokens` 零生产调用者，`render_patch` 从不传 tokens，工具三态底色用常量——整条分层 token 视图是死代码，已于 commit `d4f31ed` 删除。
>
> **新结论（取代本节）**：`ThemeTokens` 方案经评估放弃，`TuiTheme` 是**唯一且长期**的主题契约，不标 deprecated、无删除计划。原方案里"两套 API 并存"的认知负担问题随之消失。保留本节作为决策历史（为什么曾计划迁移、为什么作废），供后续参考。

### 13.1 为什么需要这一节

方案四让 `TuiTheme` 与 `ThemeTokens` 长期并存。**并存不能是终点**：两套主题 API 会让扩展作者反复问"我该用哪个"，也是永久性的认知负担。所以这里把"什么时候删掉旧的"写成有日期的承诺，而不是"以后再说"。

### 13.2 客观结论（与扩展兼容无关时的判断）

如果把"已发布扩展会 break"这个约束完全去掉，纯架构上 **嵌套 schema 优于扁平 `TuiTheme`**：

| 维度 | 扁平 `TuiTheme` | 嵌套 schema |
|---|---|---|
| 层级表达 | 把"base 层"拆成 `screen/chrome/prompt/transcript_background` 四个名字，四者当前全等于 `#000000` | `background.base / raised.{base,high,max}` 直接表达层级 |
| 加一个视觉状态 | 新增字段 + 每处组件各自判断 | JSON 加一行（`$hovered` 挂在 `action.primary` 下） |
| 控件 × 状态这类二维表 | 只能拍平（现在只有 completion 一个控件就已经有 3 个字段） | 天然二维 |
| 类型安全 | **35** 个 typed 字段（31 color），mypy 兜住拼写 | 全 `dict[str, str]`，拼错只有运行时才知道 |
| 可扩展（大量功能） | 每加能力都要动代码与字段 | 只动 JSON |

**扁平结构在"加东西"上的边际成本是递增的，嵌套是平坦的。** 这就是换的理由。

代价也说清楚：嵌套更自由 = 更容易写错，所以它必须配一个**递归 schema 校验**（opencode 用 Effect Schema 做这件事，200 行）。方案四里的 `parse_tui_theme_json` 升级就是这个校验器；没有它，换嵌套是净亏。

### 13.3 三个版本的状态

| 版本 | `TuiTheme` | `ThemeTokens` | 扩展作者看到什么 |
|---|---|---|---|
| **v0.3.x（方案四落地后）** | 保留，标 `deprecated`（docstring + 文档），**行为不变** | 新增，正式 API | 两个都能用；新代码用 `ThemeTokens`，旧代码不动也能跑 |
| **v1.0（一次 breaking）** | **删除** | 唯一 | 工厂签名从 `Callable[[TuiTheme], Widget]` 改为 `Callable[[ThemeTokens], Widget]` |
| v1.x+ | — | 唯一 | 干净 |

> **版本号更正（v0.3.0 复核）**：上一版写的是 "v2.x / v3.0"，但项目当前实际版本是
> **`0.3.0`**，不是 `2.x`。删除点应当写成 **v1.0**（semver 的第一次 major），
> 中间过渡期是 **v0.3.x / v0.4.x 这条 0.x 线**。原文的 "v2.x/v3.0" 是笔误，此处已更正。

### 13.4 v0.3.x 期间必须做的事（否则 v1.0 删不掉）

1. **`TuiTheme` 全量标 deprecated**：类 docstring 写清楚"v1.0 删除，迁移到 `ThemeTokens`"；`docs/` 里加一页迁移指南，逐个字段给 `TuiTheme.x → ThemeTokens.y` 对照表（这张表由 §5 的投影函数自动生成，不手工维护）。
2. **新组件一律只用 `ThemeTokens`**：CI 加一条守卫——`rendering/` 与 `tui/` 里**新增**的模块不得引用 `TuiTheme`（允许名单只含存量文件）。这条守卫防止 deprecation 期间又长出新债。
3. **`ThemeTokens` 必须一开始就覆盖 `TuiTheme` 的全部信息**：任何 `TuiTheme` 有、`ThemeTokens` 没有的字段，都要在投影层补上（当前是 35 个字段 / 31 个 color 字段），否则 v1.0 删除时会发现"有东西没地方接"。
4. **迁移指南里的每个旧字段都必须有明确去向**：不留"这个字段不知道怎么处理"，否则 v1.0 会拖期。

### 13.5 v1.0 的删除条件（写死，避免无限延期）

同时满足三条才发 v1.0：

1. **§13.4 的对照表 100% 覆盖**——`TuiTheme` 每个字段都有 `ThemeTokens` 对应项，且 CI 有一条测试断言这个覆盖率。
2. **`grep -r "TuiTheme" src/` 只剩投影层、`__init__` 导出、deprecation 声明三处**——任何组件、picker、HTML 导出、扩展 UI 都不再直接引用。
3. **至少一个 minor 版本（v0.4.0 起）已经完整发布**，且该版本的 CHANGELOG 里明确写了"`TuiTheme` 将在 v1.0 删除，请迁移到 `ThemeTokens`"。

> 不满足这三条就不发 v1.0。这不是"看情况"，是**前置条件**。反过来，三条都满足后**必须**发——不能因为"用户还没抱怨"就永久保留两套 API。

### 13.6 对 §9 验收标准的补充

第一批验收增加一条：

- **`ThemeTokens` 覆盖率测试**：`set(TuiTheme 的 color 字段) ` 中每个字段都能在 `project_to_tui_theme` 的反向映射里找到来源 token；缺一个就红。这条测试是 v1.0 能否删除的**唯一机械证据**。

---

## 14. 版本核对记录（2026-11-08，按 v0.3.0 重新实测）

本版之所以要重写，是因为上一版写于 PR #63（v0.2.3）时点，之后合并了 PR #65 与 #66。以下是逐项实测差异，**本 spec 现用的是右列"实际"值**：

| spec 旧值（v0.2.3） | 实际（v0.3.0） | 处理 |
|---|---|---|
| `TuiTheme` 34 字段 | **35 字段 / 31 color** | §2、§9、§13.2 已更新 |
| `rendering/themes/__init__.py` 1850 行 | **446 行**（被拆分，校验符号全在原处） | §4.3 已重写 |
| `widgets/core.py` 1747 行 | **1944 行** | §8 已更新 |
| `tui/app.py` 4070 行 | **4589 行** | §8 已更新 |
| `tui/state.py` 901/927 行 | **1034 行** | §8 已更新 |
| `tests/coding/tui` 14934 行 | **18935 行 / 22 文件** | §8 已更新 |
| `test_tui_themes.py` 294 行 | **408 行** | §8 已更新 |
| 版本 `0.2.3` | **`0.3.0`** | 头部、§13.3~13.5 已更正 |
| 侧栏 8 分区 | **9 分区**（多 `compaction`；`extensions` 重复出现） | §5.5、§8 已标注 |
| spinner 未知 | **8 帧 `⣾⣽⣻⢿⡿⣟⣯⣷` / 150ms** | §6 已补实测值 |
| 未提 `baldric_protocol` / `baldric_mcp` | **两个新包，protocol 是最底层** | §3.1 新增包分层；§8、§12 已补 |
| 假设 transcript-as-truth | **ADR-0003 Declined，未落地** | §3.3 新增；§12 明确不做 |
| `theme.*` 208 处 | **208 处**（未变） | 无需改 |
| 3 个扩展工厂接 `TuiTheme` | **3 个，签名未变** | 无需改 |
| HTML 导出 14 处 / 扩展 UI 18 处 | **14 / 18，未变** | 无需改 |
| 30 个 Screen | **30 个** | 无需改 |
| 布局常量 `1 1 1 0` / `0 1 0 1` / `(1,0)` | **仍在 `core.py:226/232/284`** | 无需改，已补行号 |
| 预览常量 8/32/120 | **8/32/120 未变** | 已补行号与"分级要按工具名分派"的警告 |

**方法**：所有"实际"值来自 `git grep`、`wc -l`、运行时 `dataclasses.fields()` 与 `theme_css_variables()` 实测，不是估算。三个只读考古 agent 分别核了 `baldric_protocol` 分层、`baldric_mcp`/live-registration、TUI 渲染数据链与折叠机制；ADR-0003、主题模块、版本号、布局常量由我本人核对。



