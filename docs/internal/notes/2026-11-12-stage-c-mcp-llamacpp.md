# 阶段 C 执行记录：mcp_tools / llama_cpp 搬迁（结构重构 v2）

- 日期：2026-11-12
- 对应计划：[../plans/2026-11-12-structural-rearchitecture.md](../plans/2026-11-12-structural-rearchitecture.md) §5 阶段 C
- 分支：`refactor/structural-v2`
- 前置：A0、A、B 已提交。

## 做了什么

| 产出 | 说明 |
|---|---|
| 搬迁 mcp | `git mv extensions/builtins/mcp → features/mcp_tools`（按计划 §3.3 改名，避开顶层 `baldric.mcp`）。`__init__.py` + `extension.py`。 |
| 搬迁 llama_cpp | `git mv extensions/builtins/llama_cpp → features/llama_cpp`（`__init__/huggingface/router/service/state` 5 文件）。 |
| 删除空包 | `extensions/builtins/` 三个子包全部搬走后删除该包（只剩 docstring 的 `__init__.py`）。 |
| 注册表字符串化 | `builtin_registry` 统一 `_load_feature_setup(module_path)`（`importlib.import_module(...).setup`，`cast` 到 `Callable[..., None]`）；llama/subagents/mcp 的 5 个 setup 包装全部改用它，消除对 feature 的静态 import（S1a）。`BUILT_IN_EXTENSIONS` 的 name（"llama.cpp"/"subagents"/"mcp"）不变，行为不变。 |
| 测试搬迁 | `test_llama_cpp_extension.py` → `tests/features/llama_cpp/`；`test_mcp_extension.py` → `tests/features/mcp_tools/`（+ 包 `__init__.py`）。`test_phase6_hardening.py` 是通用硬化套件（非专属 llama_cpp），**保留在 `tests/` 根**，仅改其 llama_cpp 导入路径。 |
| conftest 路径修正 | `tests/conftest.py` 的 `_WIN32_SKIPS` 里一条 POSIX 权限测试的 nodeid 从旧路径改到 `tests/features/llama_cpp/...`（否则该 POSIX 测试会在 Windows 真跑并失败）。 |
| 基线重算 | `structure-baseline.json`、`suppressions-baseline.json` 因路径变更重算；核对为**纯路径重命名**（suppression 总数仍 138）。搬移中一度因 `# noqa: ANN202` 让抑制数 +1，改为 `-> Callable[..., None]` 类型标注后归零。 |

## 与本轮计划的分歧/取舍

1. 计划 §5 C「同 B」——沿用 B 的收敛：ExtensionRuntime 注入（阶段 F）、platform 目录（阶段 E）不提前建。C 只做物理搬迁 + 注册表字符串化解耦 + 测试迁移。
2. `test_phase6_hardening.py` 不搬入 `tests/features/llama_cpp/`：它是覆盖 lifecycle/race/ownership/persistence 的通用硬化套件，只是恰好触及 llama_cpp；搬入会误导归属。保留原位、仅改导入。
3. mcp 包名改 `mcp_tools`（计划 §3.3），**extension 注册名仍是 "mcp"**（`disabled_built_in_extensions` 等按 name 匹配，改 dir 不改 name 保行为）。

## 影响面（逐处核对）

- 全仓 `extensions.builtins.{llama_cpp,mcp}` 引用：`builtin_registry`（4 处 in-body import）+ `test_phase6_hardening.py` + `test_llama_cpp_extension.py` + `test_mcp_extension.py`（19 处 `import mcp as mcp_extension`）+ `builtins/__init__.py`（已删）。全部改指 `features.{llama_cpp,mcp_tools}`；grep 校验零残留。
- 包内相对 import 不动（`from .router import ...` 等）。
- 删除 `extensions/builtins/` 空包；`extensions/` 下不再有 builtins。
- 两基线 JSON diff 为路径重命名成对；suppression 总数 138 不变。

## 验收（证据）

- 全量 fast suite（除 TUI）：**2282 passed / 52 skipped / 0 failed**。
- TUI 套件：**767 passed / 74 skipped / 0 failed**。
- llama/mcp/phase6 三组：**97 passed / 1 skipped**（该 skip 为 Windows POSIX 权限，符合预期）。
- `ruff check .` / `ruff format --check .` / `check_import_graph` / `check_agent_guidance` / `check_suppressions` / `check_structure`：全绿。
- `uv run mypy`：14 个已知 Windows-only 基线错误，无新增（一度因 `import_module().setup` 返回 Any 出现 1 个新错误，`cast` 后归零）。
- **S1a**：`runtime.core/platform/frontends/extensions` 静态 import `runtime.features.*` = 0（builtin_registry 全部走 importlib）。

## 留给后续阶段

- 阶段 D：`auth/ → providers/auth/`、`backends/ → providers/backends/` 合并。
- 阶段 E：建 `runtime/platform/`，把 `builtin_registry` 与其余 `runtime/extensions/*` 收口为 platform；`FEATURES` 静态声明归位。
- 阶段 F：`runtime/app.py` 组合根 + `ExtensionRuntime` 注入，完成 core→platform 反转。
