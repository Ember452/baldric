# 阶段 B 执行记录：subagents 试点搬迁（结构重构 v2）

- 日期：2026-11-12
- 对应计划：[../plans/2026-11-12-structural-rearchitecture.md](../plans/2026-11-12-structural-rearchitecture.md) §5 阶段 B
- 分支：`refactor/structural-v2`
- 前置：A0、A 已提交。

## 做了什么

| 产出 | 说明 |
|---|---|
| 物理搬迁 | `git mv src/baldric/runtime/extensions/builtins/subagents → src/baldric/runtime/features/subagents`（20 文件：16 模块 + `ui/` 4 文件）。包内相对 import 不变。 |
| 新建 features 包 | `runtime/features/__init__.py`（声明 features 命名空间 + UI 例外说明）。 |
| 注册表字符串化解耦 | `builtin_registry._subagents_setup` 改为 `importlib.import_module("baldric.runtime.features.subagents.extension")`，消除对 feature 的**静态 import**（S1a）。`BUILT_IN_EXTENSIONS` 仍声明 `name="subagents"`，行为不变。 |
| 测试搬迁 | 14 个 `test_subagents_*.py` → `tests/features/subagents/`；新建 `tests/features/__init__.py`、`tests/features/subagents/__init__.py`。测试 helper `tests/helpers/subagents_shared.py` 的 `EXTENSION_DIR` 与 `subagents_ui_helpers.py` 的导入改新路径。 |
| S1a 闸门 | `scripts/check_import_graph.py` 增 `scan_feature_isolation_violations`：`runtime.core/platform/frontends/extensions` 不得静态 import `runtime.features.*`（AST 走文件体，捕获函数体内 import；`importlib` 字符串加载放行）。`tests/guards/test_import_boundaries.py` 增 4 个测试（真实树 0 违规 + 合成样例能报/放行）。 |
| 基线重算 | `structure-baseline.json`、`suppressions-baseline.json` 因路径变更重算；经核对为**纯路径重命名**（suppression 总数不变，仍 138），无新增抑制。 |

## 与本轮计划的分歧（已按现实修正并回写计划）

1. **§5 B 步骤 3「ExtensionRuntime 由 app 注入」推迟到阶段 F**：注入点组合根 `runtime/app.py` 是阶段 F 产物；A0 只定义了 `HookDispatcher`/`FeatureSetup` 两个 port，断开 core→platform 所需的 `ProviderCatalog`/`SessionLifecycle` 当时按维护者确认推迟。故 B 不硬做注入（否则半迁移，违反铁律），把"真正断开 core→platform 依赖"留到 F 一并完成。B 只完成「物理搬迁 + 注册表字符串化解耦 + S1a 验收」。
2. **未建 `runtime/platform/`**：计划 §5 B step 2 要 `platform/features.py` 静态 FEATURES，但 `runtime/platform/` 是阶段 E 才建。为避免提前半迁移，B 用 `builtin_registry` 内的字符串路径实现解耦；`FEATURES`/`platform` 归位留到 E。
3. **`features/subagents/ui → frontends/tui` 记为文档化例外**（维护者确认 (a) 方案）：`ui/strip.py`、`ui/viewer.py` 是**真 Textual 控件**，必须依赖 tui。§4.3 矩阵的 `features ✗→ frontends` 对本用例例外；**host 接线**仍走 `ComponentBridge`（`ui/controller.py` 干净，tui 类型仅 TYPE_CHECKING）。已在 `features/__init__.py` 与计划 §4.3 注明。

## 影响面（逐处核对）

- 全仓 `extensions.builtins.subagents` 绝对引用：`builtin_registry.py` + 14 测试 + 2 helper，全部改写为 `features.subagents`；包内相对 import 不动。零残留（grep 校验）。
- `builtin_registry` 的 subagents 加载路径改为 importlib；`llama_cpp`/`mcp` 仍在 `builtins/`（阶段 C 才搬），行为不变。
- 两个基线 JSON 的 diff 为纯路径重命名（已核对 removed/added 成对、suppression 总数 138 不变）。

## 验收（证据）

- 全量 fast suite（除 TUI）：**2282 passed / 52 skipped / 0 failed**。
- TUI 套件：**765 passed**（首跑 2 个 `test_tui_app` 用例因 Windows asyncio 抖动失败，单跑即过——AGENTS.md 已知抖动，非本次改动）。
- 搬迁后 subagents 测试：**232 passed / 3 skipped**。
- `ruff check .` / `ruff format --check .` / `check_import_graph` / `check_agent_guidance` / `check_suppressions` / `check_structure`：全绿。
- `uv run mypy`：14 个已知 Windows-only 基线错误，无新增。
- `tests/guards/`：**30 passed**（含 S1a 真实树 0 违规 + 合成样例有牙）。
- **S1a**：`runtime/core/platform/frontends/extensions` 静态 import `runtime.features.*` = **0**（AST 扫描，实读核对）。

## 留给后续阶段

- 阶段 C：`mcp_tools` / `llama_cpp` 同法搬迁（llama_cpp 只依赖 `providers/backends` 契约）。
- 阶段 E：建 `runtime/platform/` 时把 `builtin_registry` 的静态 `FEATURES` 声明归位、`runtime/extensions → platform` 收口；届时删除 features 内对 `runtime.extensions` 的现存依赖路径（如有）。
- 阶段 F：引入 `runtime/app.py` 组合根，把 `ExtensionRuntime` 从 `session.py:587/687`、`lifecycle.py:314` 抽出注入，完成 core→platform 依赖反转（B 已为其备好 port 与字符串化注册表）。
