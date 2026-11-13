# 外审修正执行记录：守卫对齐真实树 + 契约诚实化（结构重构 v2）

- 日期：2026-11-13
- 背景：维护者对分支 `f2d564a..HEAD`（A0–G，12 提交）做了逐文件外审，判定
  「搬家干净、记账不干净」，并给出修复清单；本记录对应清单 1–6 的落地。
  修正全部为守卫/文档/计划对账级，**不动生产行为**；对应计划新增 §0.2。
- 分支：`refactor/structural-v2`

## 逐项落地

| 外审项 | 落地 | 关键证据 |
|---|---|---|
| 1. plan §7 S8/S9 虚标 ✅ | S8 改述为现实（teardown 由 `session_shutdown` 事件 + `retire()` 承担，三 feature 现状即如此；disposer 契约删除）；S9 补真实测试 | 亲验三 setup 全 `-> None`（mcp_tools:296 / subagents:1005 / llama_cpp:41）；新增 `test_staged_runtimes_do_not_share_feature_state` |
| 2. `FeatureSetup` 二选一 | **删除** `FeatureSetup` + `HookDispatcher`（两者自建立起零消费：全仓仅定义/facade 导出/文档）；`ports.py` 仅保留有真实消费方的 `ProviderCatalog`/`EffectiveProviderView`；ADR-0007 加修订注 | grep 全仓（src/tests/examples/docs）：零代码消费；`ports.py` 115→68 行 |
| 3. 守卫指向未建成的树 | S1a **反转**为「`runtime.*` 下除 `features` 外全部禁止静态 import features」——新增子包自动覆盖；合成实验证实原三前缀列表的 session 盲区闭合；`LAYER_MATRIX` 死数据删除 | 合成实验：`runtime.session.leaky` 旧列表 0 违规 → 新规则必报 |
| 3b. 矩阵接线 | 落两条真实边：`config ✗→ trust`（`TrustDefault` 移至 `config/shell_config.py` 定义、trust 层以 `X as X` re-export，修掉 `shell_config.py:11` 的矩阵外 import）与 `features ✗→ frontends`（AllowRule 禁令） | scanner 全绿 + 合成实验：config→trust、features→frontends.{rpc,tui.app} 必报 |
| 4. subagents→frontends.tui 边三选一 | 选「建模例外」：`AllowRule(subagents.ui → frontends.tui, allow=(config,state,widgets))` + 空白禁令；allow-rule 匹配改**最具体优先**（longest source→target），窄例外不被宽禁令吞掉；`features.py`「TUI toolkit」措辞改为「baldric 自有 frontends.tui 三模块」 | 合成实验：例外内 3 import 放行、`tui.app`/`frontends.rpc` 必报；真实树全绿 |
| 5. G 笔记数字 | 1031→1139（splitlines 脚本口径）两处更正 + 勘误注（1031 是 `Measure-Object -Line` 非空行口径，口径混用造成 −508 错觉，实际 −400）；§3 的 cli "<600" 目标标注现值 1,139 | `git show d6c1a41` 与 HEAD 均为 raw 1139 / 非空 1031 |
| 6. 四处冻结文档 | `app.py` docstring 改为准确陈述反转范围（session 仍有 6 处平台契约 import：session.py:56、lifecycle.py:36-37、model_selection.py:21、provider_helpers.py:21-22、runtime.py:52）；`ports.py` docstring 重写（删 "built in a later stage"）；scanner 冻结注释重写（包已存在 + 最具体优先语义）；`features.py` 措辞修正 | 逐处亲读改写 |

另按外审清单顺手项：plan §3.1（rendering 留 `runtime/rendering`，core 合并未发生）、
§4.2（实际 importlib 加载点为 `builtin_registry._load_feature_setup`）加现实修正注。

## 外审结论的核实口径（承认两处更正）

本执行者对外审报告的核实结论：总判词认同；两处数字更正——
① P1-4 并非"数字错 108 行"，而是两种行数口径混用（1139 raw vs 1031 非空）；
② `baldric_coding` 为 835 次/129 文件（非 59 处），且全部为 main 时代遗留、分支新增 0。

## 验收（证据）

- 全量 fast suite（除 TUI）：**2289 passed / 52 skipped / 0 failed**（+3 守卫 +1 S9）。
- TUI：**766 passed**（1 个 `test_local_modals_receive_app_level_arrow_navigation` Windows asyncio 抖动，单跑即过——阶段 D 同款已知抖动）。
- guards：**74 passed**（36 import-boundaries + 结构/抑制/agent-guidance 等 ratchet）。
- `ruff check .` / `ruff format --check .` / `check_import_graph` / `check_agent_guidance` / `check_suppressions`：全绿；`uv run mypy` 14 个已知 Windows-only 基线错误、无新增。
- `check_structure`：`trust/policy.py` 686→688（re-export +2）按 ratchet 规则登记；其余漂移逐一审计为本轮编辑（api −7、ports −47、app +1、shell_config +6、features +3）。
- scanner 规则数 28→31（28 RULES + 3 AllowRule），`measure_structure.py` 实测回写计划 §1。

## 遗留（明确不做）

- `baldric_coding` 旧包名清理（835 处/129 文件，main 时代遗留）——独立小任务。
- `runtime/__init__.py` 139 导出瘦身、`platform/__init__.py` 116 导出收窄——独立重构（§6.1）。
- 阶段 H：session 消肿（2,060 行 / 183 方法）。
- cli.py 进一步瘦身至 <600（F/G3 未达成的目标，见 §3 标注）。
