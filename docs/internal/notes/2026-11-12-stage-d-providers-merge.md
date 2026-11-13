# 阶段 D 执行记录：providers 域合并 + backends→extensions 依赖反转（结构重构 v2）

- 日期：2026-11-12
- 对应计划：[../plans/2026-11-12-structural-rearchitecture.md](../plans/2026-11-12-structural-rearchitecture.md) §5 阶段 D
- 分支：`refactor/structural-v2`
- 前置：A0、A、B、C 已提交。

## 做了什么

| 产出 | 说明 |
|---|---|
| 搬迁 auth | `git mv runtime/auth → runtime/providers/auth`（9 文件含 `flows/`）。包内 import 前缀改写为 `providers.auth.*`。 |
| 搬迁 backends | `git mv runtime/backends → runtime/providers/backends`（`contracts.py` + `__init__.py`）。 |
| **依赖反转（本阶段核心）** | 原 `backends/contracts.py` 直接 import `runtime.extensions.provider_registry.DynamicProviderRegistry`（构造依赖 `.generation_id`/`.layer_token()`/`.effective()`）。→ 把纯形状 `ProviderLayerToken` 迁入 `protocol/provider.py`（`extensions.provider_registry` 以 `as` 重新导出保公共面）；在 `protocol/ports.py` 新增 `ProviderCatalog` + `EffectiveProviderView` 两个 Protocol；`contracts.py` 构造参数改为 `ProviderCatalog`（Protocol），删掉对 `runtime.extensions.provider_registry` 的静态 import。`DynamicProviderRegistry` 结构化满足该 Protocol（mypy 通过）。 |
| import 改写 | 全仓 `runtime.auth → providers.auth`、`runtime.backends → providers.backends`（src 26 文件 + tests 9 文件；含 `runtime/__init__.py` 公共 re-export、内部包 import）。前缀改写后受 isort 影响，用 `ruff --fix --select I001` 统一排序。 |
| 基线重算 | `structure-baseline.json`、`suppressions-baseline.json` 因路径变更重算；核对为**纯路径重命名**（suppression 总数 138 不变）。 |

## 与计划的分歧（按"长期最优"选择了依赖反转）

计划 D 原文仅写「`git mv auth/ → providers/auth/`、`backends/ → providers/backends/`。更新 import」——**未提及 `backends → extensions.provider_registry` 这条跨域边**。若只照字面搬迁，边会变成 `providers.backends → runtime.extensions`，而计划 §4.3 矩阵要求 `providers ✗→ platform(extensions)`，这条边须在阶段 E（platform 抽取）解决。维护者明确要求"选长期最优、别把将来更贵的债留到几十万行"——故本阶段**直接做依赖反转**（`ProviderCatalog` port + `ProviderLayerToken` 上移），把这条边**消除**而非推迟，而不是等 E 再做。这也是 A0 当时按维护者确认"推迟"的 `ProviderCatalog` port 的正确落地时点。

## 影响面（逐字核对）

- `ProviderLayerToken`：原定义在 `extensions/provider_registry.py`，仅被 `provider_registry.py` 自身、`backends/contracts.py`、`extensions/__init__.py`（re-export）引用。迁入 protocol 后 `provider_registry` 以 `ProviderLayerToken as ProviderLayerToken` 重新导出，`is` 恒等（已验），消费点零改动。
- `ProviderCatalog`/`EffectiveProviderView`：仅 `backends/contracts.py` 使用；`DynamicProviderRegistry` 的 `generation_id`/`layer_token`/`effective` 三成员结构化匹配。`contracts.py` 里对 `effective_provider` 只读 `.layer_token`，故 `EffectiveProviderView` 只需该成员。
- import 前缀：全仓 grep 旧路径零残留；`runtime/__init__.py` 导出的 OAuth* 公共名不变。
- 基线 diff：suppression 键 `runtime/auth/oauth.py → providers/auth/oauth.py`、`runtime/backends/contracts.py → providers/backends/contracts.py`（成对、总数 138 不变）。

## 验收（证据）

- 全量 fast suite（除 TUI）：**2281 passed / 52 skipped / 0 failed**（首跑 1 个 `test_subagents_integration_tui` 因 Windows asyncio 抖动失败，单跑/整文件跑均通过——已知抖动，非本次改动）。
- D 直接影响域（auth/providers/config-credentials/llama_cpp/mcp_tools/phase6/guards）：**349 passed / 2 skipped**（Windows POSIX）。
- TUI 套件：**767 passed / 74 skipped / 0 failed**。
- `ruff check .` / `ruff format --check .` / `check_import_graph` / `check_agent_guidance` / `check_suppressions` / `check_structure`：全绿。
- `uv run mypy`：14 个已知 Windows-only 基线错误，无新增（依赖反转未引入类型错误）。
- `import-graph: OK`：`providers.backends` 不再 import `runtime.extensions`。

## 留给后续阶段

- 阶段 E：`extensions/{api,runtime,loader,installer,provider_registry,providers,builtin_registry} → platform/`；`extensions/__init__.py` 按消费方拆；`FEATURES` 静态声明归位。此时 `runtime.extensions → runtime.platform` 收口，且 `SessionLifecycle` port 可在平台域定型。
- 阶段 F：`runtime/app.py` 组合根 + `ExtensionRuntime` 注入，完成 core→platform 反转。
