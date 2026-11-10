# ADR-0002：为什么本轮不拆 `CodingSession` / `BaldricTuiApp` 两个 god-class

- 状态：Accepted（本轮内核重构的收尾决策）
- 日期：2026-11-08
- 背景：`kernel-refactor-plan.md` 阶段 5 原计划"把 session.py 1796 行 / tui/app.py 4180 行降到 ≤1200"。实际动手前的全量分析表明：**文件级瘦身对这两个文件是伪重构**。本 ADR 记录证据与替代路径。

## 1. 实测耦合数据（脚本 AST 扫描，非估算）

| 类 | 所在文件 | 方法数 | 类行数 | 不同 `self` 属性 | 结论 |
|---|---|---|---|---|---|
| `CodingSession` | `session/session.py`(1796) | **179** | **1491** | 大量共享 | 状态强耦合的单块编排器 |
| `BaldricTuiApp` | `tui/app.py`(4180) | **149** | **3366** | **177** | 状态强耦合的终端应用类 |

`CodingSession` 的 provider/model 子簇（68 个方法）触碰 20 个 `self._attr`，其中 **17 个同时被大量非簇方法使用**。这意味着任何"拆成 mixin/多类"的动作都会把这些属性散落到多个类上，**耦合不降反升**，只是行数下降。

## 2. 为什么"移出纯逻辑"也不达标

- `session.py` 里可移的纯逻辑只有 3 个小类（`TerminalCommandResult`/`ManualCompactionResult`/`CodingSessionConfig`，合计约 110 行）。其中 `CodingSessionConfig` 依赖 **20+ 个跨子系统类型**（provider/trust/commands/extensions/context/providers/session），移动它只是把"类型 import 中心"换个文件，不降低耦合；另两个类共 ~18 行，移出是零收益。且 `models.py` 若 import `baldric_coding.session` 包会与 `session.py` 循环，需绕道 submodule，增加脆弱性。
- `tui/app.py` 有 30 个模块级纯函数（约 220 行，均可安全移出），但 `BaldricTuiApp`（3366 行）本身不动，等于"瘦文件不瘦类"——真正的维护负担（god-class）原样保留。移动的又是文件内私有 helper，外部可维护性没有实质提升。

判断标准：**拆分的收益必须来自"降低耦合 / 稳定契约 / 降低回归半径"，而不是"文件更短"。** 上述两项都不满足。

## 3. 本轮实际做了什么（有真实收益的部分）

`subagents/extension.py`（1666 行）里的 **13 个纯格式化函数**（无 `self`、显式入参、只读 `AgentRun` 属性）已抽出到 `notification_format.py`（203 行小函数，max 8 stmts）。这是**真内聚**：把字符串渲染从 712 行 `SubagentManager` + 625 行 `setup` 中分离，且不引入循环（`AgentRun` 走 `TYPE_CHECKING`），字节级 codepoint 一致保证渲染不变。extension.py 1791→1622 行。

## 4. 后续独立任务的正确拆法（不在本轮）

god-class 拆分需要的是**降耦合设计**，不是文件搬家。可行方向（择一，需单独立项 + 独立 ADR）：

- **`CodingSession` → "状态对象 + 委托组件"**：先抽出不变的状态载体（`CodingSessionState` dataclass，纯数据），再把 provider 选择 / compaction / persistence / 命令处理 变成接收状态的可测组件（`ProviderController`、`CompactionController`、`PersistenceController`…）。每步有清晰的状态边界与行为契约测试。这是数周级的重构，不是本轮可达。
- **`BaldricTuiApp` → "Screen/Widget 组合 + 纯状态机"**：把 149 个方法按"事件处理 / 渲染辅助 / 会话桥接"分层，状态进一个 `TuiAppState`，interaction 逻辑进可单测的纯函数。同样需要完整 TUI 行为契约测试护栏先行（当前 TUI 测试在 Windows 偶发 flaky，需先稳定）。

## 5. 风险与门槛

- 两个 god-class 都是仓库热点（36 个 importer 依赖 `CodingSession`；20 个依赖 `BaldricTuiApp` 符号），拆分必须保持全部导出符号 + 行为契约。
- 拆分前必须：① 有覆盖其内部关键路径的行为测试（当前偏集成）；② 独立分支 + 分阶段可回滚；③ 专门的评审。

## 6. 结论

**本轮内核重构（protocol 抽取 / 内核零 I/O / 边界守卫 / 契约冻结 / subagents 纯函数抽取）到此收尾。** 两个 god-class 的文件级拆分不做——它不是架构改进，会制造低价值 churn 与回归风险。god-class 的**真**拆分作为独立项目按 §4 方向推进。
