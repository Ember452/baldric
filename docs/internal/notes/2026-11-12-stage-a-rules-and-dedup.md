# 阶段 A 执行记录：规则 + 删重复契约 + jsonl 移出 protocol（结构重构 v2）

- 日期：2026-11-12
- 对应计划：[../plans/2026-11-12-structural-rearchitecture.md](../plans/2026-11-12-structural-rearchitecture.md) §5 阶段 A
- 分支：`refactor/structural-v2`
- 前置：阶段 A0 已提交（`refactor(structure): stage A0 …`）。

## 做了什么

| 产出 | 说明 |
|---|---|
| `CredentialReader` 去重 | 唯一真源放 `runtime/providers/config/models.py`；`runtime/extensions/providers.py`、`runtime/providers/runtime.py` 以 `as` 形式 re-export 同一对象（验证 `is` 恒等）。 |
| `ClosableModelProvider` 去重 | 迁入 `protocol/provider.py`（`ModelProvider` + `aclose` 纯形状）；`extensions/providers.py`、`providers/runtime.py` 从 protocol 导入并以 `as` re-export。消除了原计划"留 providers/runtime.py"会造成的 `extensions.providers ↔ providers.runtime` 循环导入。 |
| `protocol/session/jsonl.py` 移出 | 移到 `runtime/core/session/jsonl.py`（行为：解析+迁移+TypeAdapter），新建 `runtime/core/__init__.py`、`runtime/core/session/__init__.py` 重新导出；`protocol/session/__init__.py` 不再导出 jsonl（消除 protocol→runtime 潜在依赖）。4 处 importer 改新路径：`runtime/session/storage.py`、`tests/agent/test_session_entry_contract.py`、`tests/agent/test_session_entry_versioning.py`、`tests/runtime/session/test_session.py`（含其动态 `import jsonl`）。 |
| `protocol/extension.py` 拆分 | 原 528 行 > 400 预算，事件 dataclass 全部移入新 `protocol/extension_events.py`（198 行），`extension.py` 现 317 行；`extension.py` 以 `as` 形式 re-export 事件，旧导入路径不变。三个共享 Literal（`SessionLifecycleReason`/`DeliverAs`/`NotifyLevel`）随事件移入 events 模块，`extension.py` 再导出，`extensions/api.py` 消费点零改动。 |
| protocol 形状/预算闸门（Task 4） | `tests/guards/test_import_boundaries.py` 新增：① 每个 protocol 模块行数 ≤ 400；② 每个 protocol 模块必须被分类为「纯形状」（受 AST 形状闸门约束）或「遗留行为债务」白名单，新模块未分类即失败（ratchet，防 protocol 再长成 god module）。 |

## 动工前的现实核对（计划有误，已按现实修正并回写计划）

1. **`ClosableModelProvider` 计划落点会循环导入**：`providers/runtime.py` 已从 `extensions/providers.py` 导入多个符号；若让 extensions 反向从 runtime 导入 `ClosableModelProvider` 即形成循环。→ 改迁 `protocol/provider.py`（纯形状，`ModelProvider` 本就在此）。
2. **jsonl 计划落点 `runtime/core/session/` 当时不存在**（阶段 E 才建）。经评估：`runtime/core/session/` 本就是 session 的最终家，现在建不增加未来成本、避免二次移动，且一次性原子完成（非半迁移）。→ 按计划落点执行。
3. **protocol 已有合法的辅助函数**（`messages.py` 的 `sum_usage`/`message_text`、`session/entries.py`、`tree.py`、`provider.py` 的 `RequestHooks.is_empty`、`tools.py` 的 `AgentTool.execute`）。计划的"protocol 只放形状"对既有协议**不能回溯强制**（需一次独立的大迁移，波及海量消费方）。→ 阶段 A 采用 ratchet 式：新模块必须纯形状，既有行为模块登记为债务白名单、只减不增；把辅助函数迁出列为后续独立任务。

## 影响面（逐处核对）

- `CredentialReader` 定义从 `extensions/providers.py` 移除 → 该文件顶部新增从 `providers/config/models.py` 的 `as` 导入；`providers/runtime.py` 原本就从 `extensions.providers` 拿（现经 re-export，恒等）。
- `ClosableModelProvider` 两个定义删除；`protocol/provider.py` 新增一个类；8 处从 `providers.runtime` / `extensions.providers` 导入的消费点（session/*、tui/app.py、cli.py、extensions/__init__.py）经 `as` re-export 继续可用（mypy strict 的"未显式导出"因此修复）。
- jsonl：`protocol/session/__init__.py` 的 `__all__` 从 23 项降到 17 项（去 6 个 jsonl 名）；importers 全部改指 `runtime.core.session.jsonl`。
- `protocol/extension.py` ↔ `extension_events.py`：单向依赖（extension → extension_events），无环；`extensions/api.py` 的 re-export 因 `extension.py` 仍导出全部事件名而零改动。

## 验收（证据）

- 全量 fast suite（除 TUI）：**2277 passed / 52 skipped / 0 failed**（+ 1 个 TUI 集成测试在首次运行时因 Windows asyncio 抖动失败，单跑与连跑两次均 12/12 通过——AGENTS.md 记录的已知 Windows TUI 抖动，非本次改动引起）。
- `ruff check .` / `ruff format --check .`：全绿（487 文件）。
- `uv run mypy`：**14 个已知 Windows-only 基线错误**（storage.py/trust/policy.py 的 fcntl），无新增（过程中曾因 re-export 未显式导出出现 8 个新错误，改用 `X as X` 后归零）。
- `scripts/check_import_graph.py`：OK（protocol 不再依赖 session.jsonl）。
- `scripts/check_structure.py`：OK。
- protocol 模块行数（由 `measure_structure.py` 生成）：`extension.py` 317、`extension_events.py` 198、`ports.py` 54、其余均 < 400。

## 留给后续阶段

- `protocol/messages.py`、`provider.py`、`tools.py`、`session/entries.py`、`session/tree.py` 的既有辅助函数/方法仍属"遗留行为债务"，建议单独立项迁移（届时把事件/形状与辅助函数彻底分家）。
- `runtime/core/` 已开张，阶段 E 把 session 其余文件整体迁入时，`core/session/jsonl.py` 已就位。
