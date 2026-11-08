# TUI 视觉系统 Implementation Plan（第二批：L3 交互层 + L4 一致性层）

> **执行纪律（沿用第一批，用户指定，优先级高于本文档）**
>
> 1. 本文档不是铁律。动手前必须去代码核实每个文件/签名/行号；冲突以代码为准，先改文档再写代码。
> 2. 每任务开始前写清：影响面清单（git grep 实查）、≥3 个具体 bug 场景、验证方法。缺一不动手。
> 3. 新逻辑进 `rendering/` 纯函数；`app.py` 与 `widgets/core.py` 受棘轮锁定，净增长必须补偿或记录。
> 4. 参数/常量来源优先抄 opencode / pi，注明来源文件。
> 5. 修烂代码必须单独 commit，说明原行为与新行为。
> 6. 硬约束不变：`TuiTheme` 35 字段、`theme_css_variables` 32 键不减不改名；`rendering/` 不引 Textual；每 commit 一件事。

**Spec:** `docs/superpowers/specs/2026-11-08-tui-visual-system-design.md` §6（L3）、§7（L4）
**前置:** 第一批已完成（commit `4380cba..acba095`），验收记录 `dev-notes/architecture/tui-visual-batch1-acceptance.md`

---

## 已核实的代码现状（2026-11-09 实测，执行时仍需复核）

| 事实 | 位置 | 说明 |
|---|---|---|
| spinner 现值 8 帧 `⣾⣽⣻⢿⡿⣟⣯⣷`、0.15s | `rendering/activity.py` | 第一批已抽出到独立模块 |
| opencode/pi spinner **完全一致** | `opencode-dev/.../component/spinner-frames.ts`、`pi-main/.../components/loader.ts` | 10 帧 `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`，80ms |
| pending 工具行已有 elapsed 计时（≥1s 显示） | `widgets/core.py:1644-1647`，`TOOL_TIMER_MIN_SECONDS=1.0` | `format_elapsed` |
| **完成后时长被丢弃** | `tui/state.py:663/:671` `record_tool_result` 把 `started_at` 置 None | 需先捕获再清除 |
| 工具成败靠 `startswith("✓")` | `widgets/core.py:1595-1598`、`_tool_accent_style:1607-1611` | 第一批标记的烂代码 |
| `ThemeTokens.role_tool_{pending,success,error}_bg` 已存在但无人消费 | `rendering/theme_schema.py` | 三态底色的数据源 |
| 流式组件已分 `-streaming/-finalized` 两态 | `widgets/core.py:468-497`（`TranscriptMarkdownStream`，flush 间隔复用） | 栅栏收敛行为需实测 Textual MarkdownStream 对未闭合 fence 的渲染 |
| 思考折叠摘要为纯文本行 | `format_hidden_thinking_summary`（`rendering/thinking.py`） | 不可点击 |
| `ChatItem` 是 state 内部数据类 | `tui/state.py` | 加字段 = additive，非公开契约 |

---

## Task 1: spinner 换 10 帧 + 80ms（小，热身）

**Files:** `rendering/activity.py`；测试 `tests/coding/rendering/` 或 tui 现有 activity 测试。

- [ ] 核实：`ACTIVITY_SPINNER_FRAMES`/`ACTIVITY_TICK_SECONDS` 全部消费点（app.py re-export、`set_interval`）；opencode/pi 帧序列与 interval（已核实一致）。
- [ ] bug 场景：① `set_interval` 的回调节拍与新帧数不匹配（取模安全）；② 测试断言帧序列硬编码（有意变更 → 改断言）；③ re-export 别名遗漏导致 AttributeError。
- [ ] 改 `ACTIVITY_SPINNER_FRAMES`（10 帧）与 `ACTIVITY_TICK_SECONDS = 0.08`；跑 activity 相关测试；commit `feat(tui): ten-frame braille spinner at 80ms`。

## Task 2: 工具结果数据层——显式记录成败与时长（烂代码修复，独立 commit）

**Files:** `tui/state.py`（`record_tool_result` + `ChatItem`）、`tests/`。

- [ ] 核实：`ChatItem` 全字段与构造点；`started_at` 的写入点（谁在 pending 时盖章）；`tool_result` 字段消费者。
- [ ] bug 场景：① orphan 结果路径（`:675-684`）漏记时长；② 批量/分组调用（`_grouped_calls_by_call_id`）时长记在成员还是组上；③ `time.monotonic()` 跨天/进程恢复的会话重放无意义（持久化字段为 None 时渲染侧回退）。
- [ ] `ChatItem` 增 `tool_is_error: bool | None = None`、`tool_duration_seconds: float | None = None`；`record_tool_result` 在清除 `started_at` 前捕获时长、写入 is_error。原行为：渲染侧靠 `startswith("✓")` 猜；新行为：显式状态。
- [ ] commit `fix(tui-state): record tool outcome and duration explicitly`。

## Task 3: 工具行三态底色渐变 + 完成后 `· 4.2s`（ThemeTokens 接线）

**Files:** `widgets/core.py`（`_chat_item_role_style`、工具行渲染）、`rendering/`（新纯函数：状态→底色渐变帧）、`state.py` 无。

- [ ] 核实：`role_tool_*_bg` 三值在 5 套主题里的取值；`_blend_hex_colors` 复用；工具行重绘时机（record 后是否有动画帧循环，参照 `_sync_activity_indicator` 的 timer 模式）；`+N −M` diffstat 的数据可得性（patch 在 `tool_result.details`，`parse_unified_patch` 可数）。
- [ ] bug 场景：① 渐变帧 timer 泄漏（行被移除后未停）；② 分组行（batch）成员各自完成时的底色归属；③ `parse_unified_patch` 对非 diff 内容返回空（diffstat 缺省为不显示）；④ 三态色在 light 主题对比度不足。
- [ ] 渲染：pending=无底色（border 表达）、success/error=对应 `role_tool_*_bg` + 2 帧从工具文本色渐入；完成后行尾 `· 4.2s`（有 patch 时先 `+3 −1 · `）。第一版可不做 diffstat（拆到后续），本任务保底完成时长。
- [ ] commit `feat(tui): tool row state backgrounds with completion timing`。

## Task 4: 流式收敛实测与打磨

**Files:** `widgets/core.py`（Streaming/`TranscriptMarkdownStream`）、必要时 `rendering/`。

- [ ] 先写探针测试：向 `StreamingTranscriptMessageWidget` 流式喂一个跨多次 write 的未闭合 fence，观察 MarkdownStream 的中间渲染（纯文本？部分高亮？），闭合后再观察。**没有实测不设计。**
- [ ] bug 场景：① 中间态闪烁（flush 间隔内重复 parse）；② 未闭合 fence 吞掉后续普通段落；③ finalize 与 stream.stop 的竞态（on_unmount 已处理一半）。
- [ ] 依实测结果决定：仅需调 flush/CSS（小改）或需要自定义中间渲染（大改，可能降级为"记录现状+最小修复"）。
- [ ] commit 视结果定，保证一件事一 commit。

## Task 5: 思考块点击展开

**Files:** `widgets/core.py`（折叠摘要行→可点击）、`tui/state.py`（按块展开状态）、`rendering/thinking.py` 不动。

- [ ] 核实：折叠摘要行的 widget 类型与挂载点；`state.show_thinking`/`update_thinking_visibility` 全局开关与按块展开的正交性；重绘（`update_from_state`）会不会重置点击态 → 展开状态必须存 state（`ChatItem.thinking_expanded: bool`）而非 widget。
- [ ] bug 场景：① 流式中 thinking 块被点击（应不可点——只折叠摘要行可点）；② 展开后 `show_thinking` 全局切换的交互（全局关时逐块展开态怎么办——定义：全局开关优先）；③ 点击命中区域是整行还是图标。
- [ ] commit `feat(tui): click a collapsed thinking row to expand it`。

## Task 6: hover/focus/selected 一致性

**Files:** 各 picker/completion 的 CSS 与样式函数（以 grep 实测为准）。

- [ ] 核实：opencode `action.$hovered/$focused/$selected` 语义；现状每处高亮用的字段（`completion_selected`、ListView `-highlight` 等）；列一张不一致清单再动手。
- [ ] bug 场景：① 键盘 focus 与鼠标 hover 双高亮叠加；② `-highlight` 类被多组件复用导致误伤；③ light 主题对比度。
- [ ] commit 一处一概念，可能拆多个小 commit。

## Task 7: 侧栏 `extensions` 分区重复澄清（烂代码，先核查）

**Files:** `tui/widgets/sidebar.py:211/:355`（行号以实查为准）。

- [ ] 先核查：两处是否真的都渲染（读代码+跑起来看），还是有条件分支。**如属实**：单独 commit 修复 + 说明原/新行为；**如不属实**：在本文档记录结论，关闭该项。
- [ ] bug 场景：① 两处渲染的是不同数据源（删错一个丢功能）；② `widgets/__init__.py` re-export 依赖。

## Task 8: PickerShell / DialogShell 基类 + 首批迁移（分阶段）

**Files:** 新 `tui/screens/shells.py`（或 `rendering/`？——screens 层，非 rendering）；首批迁移 4 个搜索型 picker：session/model/skill/tree。

- [ ] 核实：12 个 screen 文件里 ModalScreen 的公共结构（标题/搜索/列表/边框）与差异；`spec §7` 的 150α 遮罩（`$baldric-scrim` 不存在——需新 CSS 变量？**不许加**：32 键约束——用现有字段组合或记录新键提案）。
- [ ] 范围控制：本批只建基类 + 迁移 4 个搜索型；其余 20+ 对话框/确认屏留第三批，在本文档记录。
- [ ] bug 场景：① 基类吸纳后某 screen 的独有快捷键丢失；② escape/取消语义不一致；③ 搜索输入与列表 focus 环。
- [ ] commit：基类一个、每迁移一批一个。

## Task 9: 截图验收 + 全量闸门（收口）

- [ ] 扩充 batch-1 截图脚本：三态工具行、点击展开的思考块、新 picker 外观。
- [ ] 全量闸门同第一批：fast + TUI + ruff + format + import graph + structure + suppressions + mypy（14 已知噪音）。
- [ ] 验收记录追加到 `dev-notes/architecture/tui-visual-batch1-acceptance.md` 或新开 batch2 文档；commit `docs: batch-2 visual acceptance record`。

## 执行顺序

T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 → T9（风险递增；T4 探针先行，若 MarkdownStream 已满足则缩水为小改）。

## 明确不做（本批）

- `thinking_levels` 主题级覆盖接线（schema→tokens 消费路径，随第三批 schema 校验器一起做）。
- L4 其余 20+ 对话框/确认屏迁移（第三批）。
- diff 的 `+N −M` 若 T3 工期吃紧则随第三批。
