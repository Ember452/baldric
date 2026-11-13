# runtime 包根瘦身：139 名聚合 facade → 仅版本号（2026-11-13）

- 计划依据：§6.1「`runtime/__init__.py` 瘦身（只 `__version__` + 必要符号）」、
  §0.2（外审修正第 3 条的延续）；维护者确认走「方案 A」。
- 变更性质：**有意的公共契约变更**（AGENTS 允许：仅在行为有意改变时改动断言，
  并在提交信息中说明）。这是本分支唯一一处删除已冻结公共面的改动。

## 为什么做

实测 `import baldric.runtime` 会**一次性带出 156 个 `baldric.runtime.*` 模块**
（auth flows、session、tools、frontends…）——包根是一个 139 名的聚合 facade，
把整个应用变成了一行 import 的副作用。消费面却极小：src 里只有 **1 个**文件
（`features/subagents/extension.py`）从包根导入，其余 22 个全是测试。

## 做了什么

| 项 | 变更 |
|---|---|
| `runtime/__init__.py` | 317 行 / 139 名 → **18 行 / 1 名**（`__version__`）；eager 带出 **156 → 1** 个模块 |
| 消费方改归属子模块 | 1 个 src 文件 + 22 个测试文件改为从归属子模块导入（`session.session` / `session.manager` / `providers.config` / `providers.auth.credentials` / `context.resources` / `context.prompts` / `context.skills.skills` / `config.paths` / `config.shell_config` / `tools.registry` / `platform.builtin_registry`）；`from baldric.runtime import cli`（4 处）保留——子模块导入不依赖包根导出 |
| 冻结测试迁移 | `tests/test_public_surface.py` 从「冻结 `baldric.runtime` 139 名」改为「冻结 **`baldric.api`** 63 名」（唯一稳定面，受 `EXTENSION_API_VERSION` 治理），并新增两条守卫：`baldric.runtime.__all__ == ["__version__"]`；干净子进程里 `import baldric.runtime` 不得带出应用模块（防止聚合 facade 悄悄回来） |
| 用户文档 | `docs/user/how-to/extensions.md` 2 处示例改指 `baldric.api` / `baldric.runtime.context.resources` |
| 基线 | `runtime/__init__.py` 317→18 行（structure 基线收紧）；`subagents/extension.py` 1673→1672 |

## 影响面（逐字核对）

- 全仓 `from baldric.runtime import ...` 现仅剩 4 处，且全部是 `cli` 子模块导入（合法，不依赖包根导出）。
- `baldric.runtime.__version__` 语义不变（仍来自 `runtime.version.current_version()`）；顶层 `baldric/__init__.py` 不依赖包根导出。
- 示例（`examples/`、`data/examples/`）此前已改用 `runtime.platform`，本次无需改。
- 文档里 `from baldric.runtime import` 的旧示例已清零（`git grep` 校验）。

## 验收（证据）

- eager import：**156 → 1**（实测 `sys.modules` 差集），并有子进程回归测试钉住。
- 全量 fast suite（除 TUI）：**2291 passed / 52 skipped / 0 failed**（+2 新公共面测试）。
- TUI：**767 passed / 74 skipped / 0 failed**。
- `ruff check .` / `ruff format --check .` / `check_import_graph` / `check_agent_guidance` / `check_suppressions` / `check_structure`：全绿；`uv run mypy` 14 个已知 Windows-only 错误、无新增。
- `tests/test_public_surface.py`：3 passed（api 冻结 / runtime 仅版本 / 无 eager 导入）。
