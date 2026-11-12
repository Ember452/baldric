# 阶段 E 执行记录：platform 抽离 + FEATURES 声明（结构重构 v2）

- 日期：2026-11-12
- 对应计划：[../plans/2026-11-12-structural-rearchitecture.md](../plans/2026-11-12-structural-rearchitecture.md) §5 阶段 E
- 分支：`refactor/structural-v2`
- 前置：A0、A、B、C、D 已提交。

## 做了什么

| 产出 | 说明 |
|---|---|
| 搬迁 platform | `git mv runtime/extensions → runtime/platform`（7 模块 + `__init__.py`，共 ~4900 行）。文件同名保留（api/runtime/loader/installer/provider_registry/providers/builtin_registry）。 |
| 全仓 import 改写 | `baldric.runtime.extensions` → `baldric.runtime.platform`（70 个 .py 文件，含 src/tests/repo-examples/self-docs；token 一一对应）。 |
| `platform/features.py`（新） | 静态 `FEATURES: tuple[FeatureSpec, ...]`（`name`/`kind`/`setup="module:attr"`，无 order），§6.3 的静态 tuple 形态。`builtin_registry` 改为从 `FEATURES` 解析每个 feature 的 setup 模块路径（`_feature_setup_path`），`FEATURES` 成为唯一真源；B 阶段推迟的 FEATURES 声明在此归位。 |
| guard 校验 | `tests/guards/test_import_boundaries.py` 新增 2 测试：每个 `features/<name>` 目录必须在 FEATURES 中声明；每个 FEATURES 的 setup 路径必须在磁盘上可解析（S7）。 |
| scanner 清理 | `S1A_FORBIDDEN_IMPORTERS` 移除已不存在的 `runtime.extensions`（现有 `runtime.platform`），保持 `platform → features` 静态 import = 0。 |
| 文档 | 用户文档 `docs/user/how-to/extensions.md`、self-docs `data/docs/{extensions,architecture}.md` 的路径改 `platform`；历史 rename 日志保留原文。 |
| 基线重算 | `structure-baseline.json`、`suppressions-baseline.json` 因路径变更重算；核对为**纯路径重命名**（suppression 总数 138 不变）。 |

## 关键决策（长期最优）

1. **未拆 `extensions/__init__.py` 的 120 符号"按消费方分"**：计划 §5 E 说"按消费方拆"，但经核对，`platform → providers.backends.contracts` 的 re-export 边**符合 §4.3 矩阵**（platform → providers 允许），且重排 re-export 面会波及 60+ 根导入点。故本阶段保持 `platform/__init__.py` 的公共面等价（只改 import 前缀），把"按消费方收窄导出面"作为后续可选清理（计划 §6.3/§6.1 的稳定 api 面治理），不在 E 内做——避免为纯整理引入大范围破坏。
2. **一次 **严重教训**：首轮用 PowerShell `Get-Content/Set-Content` 做 token 替换，**把 UTF-8 em-dash 破坏成 `?`**（24 文件损坏）——正是 AGENTS.md 硬规则警示的事故。已 `git reset --hard` 回到阶段 D 干净点，改用 **.NET `UTF8Encoding($false)` 读写**（保留多字节），并逐项验证：旧 token 0 残留、`E2 80 3F` 损坏 0、em-dash 计数与 HEAD 一致（10=10/6=6/6=6）。此后全程用 `edit` 工具处理源码。**教训：非 ASCII 内容一律不用 PowerShell 文本重写。**

## 影响面（逐字核对）

- 7 个 platform 模块 + `__init__` 的 re-export 目标全部指向新路径；`api.py`/`runtime.py` 超 1200 行属既有债（基线登记）。
- 70 个 importer：`session`（lifecycle/runtime/session/provider_helpers/model_selection/resource_helpers）、`tui`（app/state/extension_components/screens/sidebar/screens/extensions）、`rendering`、`features/*`、`providers/runtime`、`api/__init__`、`cli`、`.baldric/extensions/*`、repo `examples/extensions/*`（首轮漏掉，测试暴露后补）。
- scanner：`runtime.platform` 已在 S1A 禁止集，删除失效的 `runtime.extensions` 项。

## 验收（证据）

- 全量 fast suite（除 TUI）：**2284 passed / 52 skipped / 0 failed**（=2282 + 2 新 FEATURES guard）。
- TUI 套件：**766 passed / 74 skipped / 0 failed**（1 个 skills-picker 用例 Windows Textual 抖动，单跑即过——已知抖动，非本次改动）。
- `ruff check .` / `ruff format --check .` / `check_import_graph` / `check_agent_guidance` / `check_suppressions` / `check_structure`：全绿。
- `uv run mypy`：14 个已知 Windows-only 基线错误，无新增。
- **S1a**：`runtime.platform` 静态 import `runtime.features.*` = 0；FEATURES 声明完备（2 个新 guard 测试）。

## 留给后续阶段

- 阶段 F：`runtime/app.py` 组合根 + `ExtensionRuntime` 注入（`session.py:587/687`、`lifecycle.py:314`），完成 core→platform 依赖反转；`platform/__init__` re-export 面收窄与 `api/` 稳定面治理可一并做。
- 阶段 G：tui → frontends/tui、rpc、print。
- 阶段 H：session 消肿。
