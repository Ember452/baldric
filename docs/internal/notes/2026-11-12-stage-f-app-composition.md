# 阶段 F 执行记录：app 组合根 + ExtensionRuntime 注入（结构重构 v2）

- 日期：2026-11-12
- 对应计划：[../plans/2026-11-12-structural-rearchitecture.md](../plans/2026-11-12-structural-rearchitecture.md) §5 阶段 F
- 分支：`refactor/structural-v2`
- 前置：A0–E 已提交。

## 做了什么

| 产出 | 说明 |
|---|---|
| 新建 `runtime/app.py`（组合根） | 提供 3 个工厂 + 1 个 dataclass，**所有 `ExtensionRuntime(...)` 构造收敛到这一个模块**：<br>• `build_runtime()` — `CodingSession.__init__` 的裸 runtime fallback；<br>• `prepare_runtime_for_load(config, previous_runtime) -> PreparedRuntime` — 原 `CodingSession.load` 内的构造 + 首次 `load`（resource-dir 阶段）；<br>• `stage_runtime_for_reload(...)` — 原 `lifecycle.py` 重载/重绑的替换 runtime 构造 + 加载；<br>• `eligible_built_in_extensions(config)` — 从 `session.py` 移出的 built-in 过滤。 |
| `session/session.py` | 删除内联构造块与 `_eligible_built_in_extensions`；`load()` 改调 `prepare_runtime_for_load`；`__init__` fallback 改 `build_runtime()`；`ExtensionRuntime` 仅剩 `TYPE_CHECKING` 引用（运行时不再 import 具体类）。 |
| `session/lifecycle.py` | 重载 staging 改调 `stage_runtime_for_reload(...)`；`ExtensionRuntime` 引用移除（TYPE_CHECKING 也不再需要）。 |
| `session/resource_helpers.py` | 仅类型注解用 `ExtensionRuntime` → 改 `TYPE_CHECKING`。 |
| 基线 | `structure`（app.py 新增；session −37 行、lifecycle −3、resource_helpers +3 越 400 自由线→按 ratchet 规则记录）与 `suppression`（总数仍 138）重算并审计。 |

## 关键决策（为何不是计划的「75 成员 Port」）

计划 §4.1 字面要求「`CodingSession` 只持有 port 类型、不 import platform」。实测 `ExtensionRuntime` 公开面 **~75 成员**、且 `load()` 中 runtime 构造 + **两阶段 `.load()` 与 project-trust 解析交织**（先 resource-dir 加载 → trust 决策 → 再 project-dir 加载）。

- 若造 75 方法 `Platform` Protocol：只是把 concrete 类改名成 god interface，**不是解耦而是更差的抽象**（计划此处是理论瑕疵）。
- 因此选**高层反转**：把「构造 + 首阶段 load」收进组合根 `runtime/app.py`（core 不再构造/导入 platform 具体类，运行时依赖方向变为 `session → app → platform`），两阶段中与 trust 交织的第二阶段 `load` 仍留在 `session.load()`（生命周期归属正确）。

## 影响面（逐字核对）

- 构造点：`session.py`（原 587 `__init__` fallback、687 `load`）、`lifecycle.py:314` 三处 → 全部改为调用 `app.py` 工厂；grep 确认 src 内 `ExtensionRuntime(` 只出现在 `app.py`。
- 静态 import：`session/{session,lifecycle,resource_helpers}.py` 不再运行时 import `platform.runtime`（session/resource_helpers 仅 `TYPE_CHECKING`；lifecycle 完全移除）。
- `PreparedRuntime` 返回 `runtime_paths`/`credential_store`/`unfiltered_resource_paths`，保证 `load()` 后续 codex catalog / provider 准备逻辑不变。
- 变量名避让：工厂结果命名 `runtime_prep`，避免与 `load()` 内既有 `prepared = await _prepare_provider_selection(...)` 冲突（首次提交前 mypy 抓到 32 个误推断错误，改名后消失）。

## 验收（证据）

- 全量 fast suite（除 TUI）：**2284 passed / 52 skipped / 0 failed**。
- TUI 套件：**767 passed / 74 skipped / 0 failed**。
- session 域专项：**355 passed / 11 skipped**。
- `ruff check .` / `ruff format --check .` / `check_import_graph` / `check_agent_guidance` / `check_suppressions` / `check_structure`：全绿。
- `uv run mypy`：14 个已知 Windows-only 基线错误，无新增。
- `tests/guards`：70 passed。
- 行为不变：resume/branch/reload/replacement 相关测试全绿（这些正是 runtime 装配路径的回归保护）。

## 留给后续阶段

- 阶段 G：`tui → frontends/tui`、`modes/rpc → frontends/rpc`、cli print → `frontends/print`。
- 阶段 H：`session` 消肿（2097→<500，现 2060）。
- 后续可选：`platform/__init__` 导出面按消费方收窄、`baldric.api` 稳定面治理；`session_view` 相关 port 化可随 H 一并做。
