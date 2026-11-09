# TUI 视觉系统第二批验收记录（batch 2）

日期：2026-11-09 · 分支：`design/tui-visual-system`
截图：复用 `dev-notes/architecture/assets/tui-batch1/*.svg`（已按第二批特性重新生成——三态工具行底色、完成时长、思考点击展开均已生效）
计划：`docs/superpowers/plans/2026-11-09-tui-visual-batch2.md`

## 交付（6 个 code commit + 3 个 docs/test commit）

| Commit | 任务 | 结果 |
|---|---|---|
| `65145b0` | 计划 | batch-2 计划（含逐任务核实清单） |
| `01da571` | T1 spinner | 10 帧 braille + 80ms（opencode/pi 两源一致） |
| `729b863` | T2 工具成败/时长数据层 | 烂代码修复：`startswith("✓")` 猜测→显式 `tool_is_error`；完成时长不再丢弃 |
| `4a2fbb0` | T3 三态底色 + 完成 `· 4.2s` | `rendering/tool_state.py`；core.py 回基线 |
| `81ed8eb` | T4 流式收敛 | 探针结论：现状已满足，零新代码，留回归守卫 |
| `e32f507` | T5 思考块点击展开 | `HiddenThinkingWidget` + state 存展开集合；两补偿抽取保棘轮 |
| `51f38cf` | T6 hover 一致性 | picker 列表行 hover 复用选中调色板（CSS 级守卫） |
| `548f7bd` | T8 picker shells | 顺延，附 4 个 picker 结构差异表 + 真实数据门槛 |
| `eb9d70b` | T7 侧栏 extensions 澄清 | 非 bug，记录关闭 |

## 验收（spec §6 / §7）

| 项 | 结论 | 证据 |
|---|---|---|
| spinner 10 帧 80ms | ✅ | activity 测试：帧序列 `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`、tick 0.08 |
| 工具行完成计时 | ✅ | 完成行尾 `· 4.2s`（一位小数）；批量/还原路径有测试 |
| 工具行三态底色 | ✅ | success `#144922` / error `#410a13`（opencode 色）；SVG 实测含 `#144922` |
| 流式收敛 | ✅ | 未闭合栅栏即渲染为真 `MarkdownFence`，闭合自动收敛（探针测试锁定） |
| 思考块点击展开 | ✅ | 摘要行可点、展开态跨重绘保持、全局 Ctrl+T 优先（3 测试） |
| hover/focus/selected 一致性 | ✅ | selected 全站同一对变量；hover 与 selected 共用调色板（CSS 守卫 + 侧栏运行时测试） |
| 侧栏 extensions "重复" | ✅ 非 bug | 交互路径 vs 静态渲染器，两条互斥路径 |
| PickerShell 基类 | ⏸ 顺延 | 4 个 picker 结构差异大，硬抽象违反 Simplicity First；门槛：≥6 个同构 picker |

## 本批的取舍与已知限制（如实记录）

1. **T3 渐变降级为静态三态底色**：`_redraw` 每次全量重建 DOM，`styles.animate` 会在每次刷新重放；渐变需 widget 复用架构（第三批）。
2. **T4 零代码**：探针推翻 spec 的"纯文本切 rich"假设——现状已收敛。
3. **T6 hover 无法 headless 行为测试**：`Pilot.hover` 在 pushed modal 上返回 False，合成 MouseMove 又绕过 compositor 的 `:hover` 管线。用 CSS 级守卫 + 侧栏运行时 hover 测试覆盖同一机制。
4. **T7 非 bug、T8 顺延**：两项都按"先核查、结论入文档"处理，不硬造。
5. **模型选择器测试的 Windows flake**：`test_tui_model_picker_shows_cached_choices_before_remote_refresh` 全量跑偶现失败，单独跑必过（仓库已知 asyncio Windows flaky，Linux CI 是确定性闸门）。

## 代码审查修复（2026-11-09，commit `79bffdd`）

审查提出的问题经逐条核实后，属实的已修复：

- **P1 用户可见**：`DiffPalette` 默认是 opencode 暗色调板且无调用者传 tokens，导致 **baldric-light 的 diff 行是暗底**。改为 `DiffPalette.for_theme(theme)` 按 light/dark 出两套（light 值抄 opencode `light.diff`）；light 截图实证暗底 24/18 → 0/0。
- **P2-3 崩溃**：分层 schema 不强制全部 `TRANSCRIPT_ROLES`，最小新格式主题会产出空 `role_styles`，widget 渲染 `role_styles["tool"]` 直接 KeyError。schema 路径现补同扁平路径的 "roles missing" 校验（实测最小主题现在被正确拒绝）。
- **token dark 误判**：`build_tokens` 只读 `appearance`，旧扁平主题（`dark:` 布尔）恒判 dark——baldric-light 变 dark。新增 `_resolve_dark`（appearance → dark 布尔 → 默认 dark），projection 同用。
- **P3 spec §9 验收**：补 `TuiTheme` 35 字段冻结守卫 + `theme_css_variables` 32 键冻结守卫。

**仍顺延（已明确记录，非遗忘）**：

- **token 层是建成未通车（死代码）**：`build_tokens` 零生产调用者；两处 `render_patch` 不传 tokens；`tool_state.py` 三态底色是硬编码常量。由此 pi-dark.json 的 `diff` 段、两套皮肤的 `syntax` 段、`roles.tool_success/tool_error` 目前是死数据。这不是"接线走漏了个别点"，而是整条 `ThemeTokens` 消费链未落地。**决策（2026-11-09）**：不为对齐 pi 的"三态底色随主题变"再加旁路 registry（那会给 baldric 引入全局可变状态只为两个底色）——是否要把 tool 三态当作 baldric 自身的概念，先定方向再动，不在第三批默认做。

- **注意区分**：`DiffPalette.for_theme`（`diffs.py`）走的是 `render_patch` **无 tokens 的真实路径**，light/dark 两套已生效（light 截图实证 24/18→0/0）；它和上面那条死掉的 `build_tokens` diff 默认不是一回事。
- 主题级 `text.thinking_levels` 覆盖（thinking 色带现全局硬编码 pi dark ramp）。
- 词级 diff 高亮色（spec §5.3 承诺 `diff.highlight.*`，现仍纯 `bold`）。
- `TuiTheme` deprecated 标记 / 迁移指南 / "新模块禁用 TuiTheme" CI 守卫（spec §13.4 的 v0.3.x 必做项）——仍在 0.3.x 窗口内，进第三批追踪。


## 全量闸门（本记录提交前实测）

见下一次全量运行结果（fast + TUI + ruff + format + import graph + structure + suppressions + mypy）。
