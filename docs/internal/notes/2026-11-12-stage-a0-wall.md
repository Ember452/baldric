# 阶段 A0 执行记录：先砌墙（结构重构 v2）

- 日期：2026-11-12
- 对应计划：[../plans/2026-11-12-structural-rearchitecture.md](../plans/2026-11-12-structural-rearchitecture.md) §5 阶段 A0
- 分支：`refactor/structural-v2`
- 性质：**纯增量、零行为变化**。不搬实现类、不删旧路径；搬家具在阶段 B 之后。

## 做了什么

| 产出 | 说明 |
|---|---|
| `src/baldric/api/__init__.py` | 稳定公共面兼容 facade，re-export 63 个扩展契约名（先指向旧 `extensions.api`，后续阶段内部改指 protocol/platform，对外路径不变） |
| `src/baldric/protocol/extension.py` | 扩展契约**纯形状**：18 个事件/结果 dataclass、`ExtensionCapabilities`、`CustomMessageView`/`CustomEntryView`/`MessageRenderOptions`/`MarkdownRenderContext`、`MessageRenderer`/`CustomMessageMarkup`/`ToolCallMarkup`/`ToolResultMarkup` 等别名、`AGENT/LIFECYCLE/PROVIDER_EVENT_TYPES` 等常量、`EXTENSION_API_VERSION`、Literal 别名 |
| `src/baldric/protocol/ports.py` | 跨域 port：`HookDispatcher`（依赖已迁入的 `UserBashEvent`）+ `FeatureSetup`（setup 返回 teardown disposer 的对称契约） |
| `src/baldric/runtime/extensions/api.py` | 删除已迁出的定义，改为从 `protocol.extension` 以 `X as X` 显式 re-export（46 处消费点零改动）；实现类保留 |
| `scripts/check_import_graph.py` | 新增 `AllowRule` + `LAYER_MATRIX` + `scan_allow_violations`（白名单形状，现有 RULES 不动） |
| `scripts/measure_structure.py` | 基线测量脚本（所有行数/符号数由此生成，禁手写） |
| `tests/guards/test_import_boundaries.py` | 新增 11 个 guard 测试：protocol 形状模块运行时无上层依赖、AST 形状闸门（含自证有牙）、AllowRule 合成样例 |

## 动工前的现实核对（计划不是铁律）

逐字段重扫代码后发现计划正文三处与代码现实不符，按「现实为准」处理并回写计划（§0.1）：

1. **`ExtensionAPI` 是带行为的实现类**：每个方法 `self._generation.assert_active()` 并委托 `ExtensionRuntime`，依赖 `TuiTheme`/`ExtensionRuntime`/`ModelChoice` 等 runtime/TUI 类型。搬进 `protocol/` 会同时违反「protocol 只放形状」和 guard 测试 `test_protocol_loads_no_upper_layer_at_runtime`。→ A0 只迁纯形状，实现类留 runtime。
2. **`PluginManifest` 全仓不存在**（P9 产物）。凭空造空壳是投机设计，违反「不为一种实现建抽象」。→ A0 不创建。
3. **`ports.py` 的 `ProviderCatalog` 返回 `ProviderRecord`（不存在）**、`DynamicProvider` 在 runtime 层。→ A0 只定无歧义的 `HookDispatcher`+`FeatureSetup`，其余推迟到 D/E 真实类型出现。

## 影响面（逐处核对）

- `CustomMessageMarkup` 消费点：`rendering/__init__.py`、`rendering/transcript.py`、`tui/state.py` —— 均仅作类型注解，零改动（`extensions/api.py` 保留 re-export）。
- `extensions/api.py` 的 46 处导入点（src 19 + tests 27）—— 路径与符号不变，零改动。
- 顶层 `import baldric.protocol.extension` / `baldric.protocol.ports` 经子进程验证**不拉起** `baldric.agent/ai/runtime/textual/rich`（guard 测试固化）。
- 抑制计数不得增长：re-export 用 `X as X` 显式重导出而非 `# noqa`，`FeatureSetup` 参数用 `object` 而非 `# noqa: F821`，suppression ratchet 保持基线不增。

## 验收（证据）

- 全量 fast suite（除 TUI）：**2276 passed / 52 skipped / 0 failed**（较基线 2265 增加 11 个新 guard 测试）。
- `ruff check .` / `ruff format --check .`：全绿（484 文件已格式化）。
- `uv run mypy`：14 个已知 Windows-only 基线错误（`storage.py`/`trust/policy.py` 的 fcntl），**无新增**。
- `uv run python scripts/check_import_graph.py`：`import-graph: OK`（含新增 AllowRule 通道，真实树 0 违规）。
- `uv run python scripts/check_structure.py`：OK（`extensions/api.py` 因迁出而缩小，improvement available）。
- `tests/guards/`：62 passed。

## 留给后续阶段的接口位

- `baldric.api` 已是稳定入口；阶段 B–F 把 `protocol.extension`/platform 的真实来源接过来时不改公共路径。
- `protocol.ports.HookDispatcher`/`FeatureSetup` 已备好，阶段 B 的 subagents 试点即可用 `FeatureSetup` 统一 teardown、用 `HookDispatcher` 断开 `core→platform` 硬依赖（见计划 §4.1 的 11 处）。
- `scan_allow_violations` + `LAYER_MATRIX` 已就绪；阶段 B 起 `features/` 目录出现时自动生效，无需改脚本逻辑。
- `scripts/measure_structure.py` 为后续每阶段的「数字由脚本生成」提供入口。
