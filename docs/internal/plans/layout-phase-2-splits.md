# 蓝图对齐第二阶段实施计划：C 类拆分（行为保持优先）

**Goal:** 把 Phase 1 停车/保留的 C 类大文件拆成可独立阅读、可独立测试的模块；同时处理 Phase 1 明确排除、但从维护性看已经超载的少数文件。所有拆分必须保持现有行为、公开符号和测试断言不变。

**Baseline:** `main` @ `57e6908`（Phase 1 已合并，公共 API 稳定化已合并）。
**Spec:** `dev-notes/architecture/target-project-layout.md`
**Phase 1 state:** `dev-notes/architecture/layout-migration-log.md`
**Public API policy:** `dev-notes/architecture/public-api-policy.md`

> 本计划是决策文档，不代表已经执行。Phase 2 与 Phase 1 的根本差别：Phase 1 是“只搬不改”，可以用 `R100` 和 `check_move_only.py` 证明；Phase 2 必然产生新的文件和新的 import 关系，**不能用 R100 做正确性证明**，必须靠行为测试、导入图检查和人工边界评审。

## 1. 独立判断：哪些文件真的需要拆

判断依据：文件行数、顶层符号数、类方法数、职责数量、现有测试覆盖、直接引用者数量。**不是“蓝图列了 C 类就拆”**；蓝图是目标位置图，不是拆分清单。

### 1.1 必须拆（Phase 2 主体）

| 文件 | 现状 | 判断 | 建议目标 | 主要风险 |
|---|---:|---|---|---|
| `tui/app.py` | 9,106 行 / 109 顶层符号 / `BaldricTuiApp` 169 方法 | **最高优先级**：30+ 个独立 Screen 类与一个巨型 App 类混在一起 | `tui/app/`：`app.py`（核心 App）、`screens/`（登录、模型、会话、主题、工具参考等）、`runtime.py`（启动/装配辅助） | 启动路径、Screen 生命周期、`tui/__init__.py` 再导出、测试量最大 |
| `session/session.py` | 5,224 行 / 83 顶层符号 / `CodingSession` 169 方法 | **必须拆**：类同时管理状态、持久化、模型选择、prompt 装配、扩展/资源、运行循环 | `session/session.py`（状态/历史/公开 API）+ `session/runtime.py`（turn 执行）+ `session/services.py`（注入能力/资源刷新）；先拆模块级 helper，再拆类方法 | 类状态耦合最深；任何拆分都可能改变异常/事件顺序；测试文件 `test_coding_session.py` 7,435 行 |
| `tui/widgets.py` | 3,351 行 / 114 顶层符号 | **必须拆**：Transcript、Sidebar、Markdown、Tool 渲染等多个 widget 家族 | `tui/widgets/`：`transcript.py`、`sidebar.py`、`markdown.py`、`tool_render.py`、`chat.py`；`widgets/__init__.py` 再导出原有名字 | `tui/app.py` 与 `tui/__init__.py` 大量引用；Textual 生命周期；渲染快照 |
| `tools/registry.py` | 1,230 行 / 53 顶层符号 | **必须拆**：工具注册、read/write/edit/bash 实现、截断、diff、进程、文件锁全部混在一起 | `tools/base.py`、`truncate.py`、`output_accumulator.py`、`read.py`、`write.py`、`edit.py`、`bash.py`、`image_processing.py`、`renderers/`；`registry.py` 只保留注册与公共入口 | 工具 schema 字符串必须逐字不变；跨工具 helper 归属；`test_coding_tools.py` |
| `commands/registry.py` | 940 行 / 45 顶层符号 | **必须拆**：命令行基础设施 + 20 个命令 + 格式化/解析 helper | `commands/registry.py`（`CommandRegistry`/基础类型/`create_default_command_registry`）+ 每命令一个 `commands/<name>.py`；共享格式化进 `commands/formatting.py` | 命令名字、help 文本、参数行为必须不变；`test_commands.py` |
| `session/export.py` | 1,936 行 / 43 顶层符号；`render_session_html` 约 1,000 行 | **必须拆**：文件导出、HTML/CSS、树渲染、entry 渲染混在一起 | `session/export/`：`writer.py`、`html.py`、`tree.py`、`entry.py`、`theme.py`、`format.py`；`session/export/__init__.py` 保留原 API | HTML 输出必须逐字节/逐结构等价；CSS/脚本内嵌资源；`test_session_export.py` |
| `rpc.py` | 783 行 / 14 顶层符号 | **应拆，但先移动后拆**：协议 server 与 wire 序列化分开 | 先 `rpc.py → modes/rpc.py`（Phase 2 第一个动作，零逻辑），再 `modes/rpc/{server.py,wire.py,session.py,__init__.py}` | 行分隔协议兼容性；`test_rpc.py`；必须先移动再拆分 |

### 1.2 强烈建议拆，但不属于原 7 文件（我的独立判断）

| 文件 | 现状 | 判断 | 建议目标 |
|---|---:|---|---|
| `providers/config.py` | 2,545 行 / 118 顶层符号 | **建议拆**：数据类、设置读写、catalog 合并、JSON 校验、thinking 解析、provider 转换全部堆在一文件。蓝图写单文件，但按当前规模已超过维护阈值 | `providers/config/`：`models.py`（数据类/异常）、`settings.py`（load/save/migrate）、`catalog.py`（合并/差异）、`validation.py`（JSON 校验）、`selection.py`（选择/thinking）、`__init__.py` 原路径再导出 |
| `cli.py` | 1,409 行 / 30 顶层符号 | **建议拆，但入口契约敏感**：argv 解析、Typer command、TUI/print/RPC 模式驱动混在一起；入口点 `baldric_coding.cli:app` 不能变 | `cli/` package：`__init__.py` 暴露 `app`，`app.py`（Typer 定义）、`options.py`（argv/选项）、`modes.py`（模式选择/装配）；具体模式逻辑移到 `modes/`（见 Task 9） |

### 1.3 不建议在本阶段拆

| 文件 | 行数 | 理由 |
|---|---:|---|
| `extensions/runtime.py` | 1,328 / `ExtensionRuntime` 69 方法 | 单一 class 是扩展运行时契约；拆分风险高，且会改变扩展作者可见的生命周期。先加边界测试，等真实增长再做 |
| `extensions/api.py` | 1,253 / 28 顶层符号 | 公开扩展 API 契约，拆分会改变 import 路径；必须与扩展版本策略一起做 |
| `backends/contracts.py` | 1,276 / 34 | 契约数据类集中，职责一致；拆成多个文件收益低 |
| `tui/state.py` | 1,094 / 26 | 状态模型集中；与 TUI 渲染耦合但不是多职责 |
| `session/usage.py` | 972 / 13 | 采集与图表渲染可拆，但当前规模可控；列入观察清单 |
| `providers/loader.py` | 779 / 40 | catalog 解析/合并职责集中，规模可接受 |
| `tui/backends.py` | 1,285 / 12 | 多个 Screen 但只服务本地后端，先按 TUI 拆包时一起处理 |
| `baldric_ai/openai_compatible.py` | 1,445 / 47 | provider 适配器，单 provider 职责；先完成 `baldric_ai/providers/` 目录整理 |

### 1.4 其他需要处理/新增的文件（不是“拆分”但缺）

蓝图目标中还没有落地、且 Phase 2 要触达的：
- `modes/`：`interactive/`、`print.py`、`json.py`、`rpc/`（从 `cli.py` 与 `rpc.py` 抽出）；
- `session/runtime.py`、`session/services.py`（从 `session/session.py`）；
- `session/export/` 目录（从 `session/export.py`）；
- `tools/base.py`、`truncate.py`、`output_accumulator.py`、`read.py`、`write.py`、`edit.py`、`bash.py`、`renderers/`；
- `commands/` 下每个命令一个文件；
- `providers/virtual_models.py`、`providers/compose/`；
- `extensions/package_manager.py`（预期新增，今天不存在）；
- `tui/app/`、`tui/widgets/` 两个目录；
- `baldric_ai/providers/`、`catalog/`、`net/`、`internal/`；
- `baldric_agent/contracts/`、`tools/`；
- `mcp/`、`security/` 只能等真实功能落地，不建空包。

### 1.5 测试文件也要拆（但独立进行）

`tests/` 目前仍是平铺的，且几个文件已经失控：

| 测试文件 | 行数 | 处理 |
|---|---:|---|
| `tests/test_tui_app.py` | 13,539 | 按 Screen/主题/模型选择/聊天/文件拖拽拆分，镜像 `tui/app/`；**在 `tui/app.py` 拆分稳定后做** |
| `tests/test_coding_session.py` | 7,435 | 按 session 状态、运行循环、模型选择、上下文、队列拆分；**在 `session/session.py` 稳定后做** |
| `tests/test_baldric_ai.py` | 4,000 | 按 provider 拆分，镜像 `baldric_ai/providers/` |
| `tests/test_extensions.py` | 3,519 | 按扩展 API/loader/runtime 拆分 |
| `tests/conftest.py` 的跨测试 import | — | 先解决 `from test_tui_app import ...` 这类跨文件依赖，再搬测试 |

测试树镜像不是本计划第一优先级，但必须在对应源码拆分的**下一阶段**完成，否则大文件会从 src 搬到 tests。

## 2. 拆分对项目的影响面（必须逐项处理）

| 影响面 | 具体要求 |
|---|---|
| **公开 API** | `baldric_coding.__all__` 保持 139；`baldric_ai.__all__` 保持 37；`baldric_agent.__all__` 保持 56。新增 `tests/test_public_surface_coding.py` 或扩展现有契约测试，对 `baldric_coding` 的 139 个导出做 AST/内容双检 |
| **内部 import** | 每个拆分 commit 必须更新 `src/`、`tests/`、`scripts/` 全部引用；不允许留旧路径 shim；用 AST import graph 而非 grep 做最终确认 |
| **Facade / re-export** | `baldric_coding/__init__.py` 只改 import 路径，不改导出集；新增子包 `__init__.py` 只写 docstring + 必要 re-export（内部包不要 eager import 子模块） |
| **扩展 API** | `extensions/api.py` / `extensions/__init__.py` 的公开符号不变；扩展作者 import 路径不变；builtins 内部拆分不得改变 `setup(baldric)` 行为 |
| **测试** | 现有断言零修改；新增 characterization tests 可以；每个拆分 commit 跑对应测试，批次末跑全量 |
| **文档** | `layout-mapping.md` / 蓝图标注目标文件；`website/content` 与 `dev-notes` 中公开路径仅在文档描述用户可见 API 时改；历史 phase 记录不改 |
| **打包** | 每个批次末 `uv build --wheel`；检查新增子包和资源是否进入 wheel；`py.typed` 仍只在三个包根 |
| **启动性能/环** | 新包 `__init__.py` 不 eager import；`import baldric_coding`、`import baldric_coding.session`、`import baldric_coding.tui.app`、`uv run baldric --version` 全过 |
| **会话格式/序列化** | `session/export` 拆分不得改变 JSONL/HTML 输出；`session/session.py` 拆分不得改变 `CodingSession` 事件顺序、异常类型、队列语义 |
| **测试执行时间** | `test_tui_app.py`/`test_coding_session.py` 很大；拆分时给 pytest 加 per-test `timeout` 不是修复，必须保持现有 skip 语义 |

## 3. 全局约束（每个拆分 commit 都适用）

- 一次 commit 只拆一个文件或一个明确的小阶段；不混入 bug 修复、性能优化、格式清理。
- 新文件命名、包深度以蓝图为准；蓝图没有给出位置时，先写入 `layout-mapping.md` / ADR 再动手，不自行发明。
- 每个新模块顶部写一行 docstring；内部模块不需要 `__all__`，需要稳定再导出的模块显式声明。
- 不新增第三方依赖；Python >=3.12；ruff line-length 110；mypy strict。
- 不修改任何现有测试断言，不新增 skip/xfail；无法在现有测试下证明的行为先补 characterization test。
- 拆分前先跑基线：`uv run pytest -q`、`uv run mypy`、`uv run ruff check .`、`uv run ruff format --check .`，记录到台账。
- 每批次末跑全量 + CI；本计划不采用 Phase 1 的 `check_move_only.py` 作为拆分证明（它只适用于零逻辑搬移）。

## 4. 拆分方法论（保证全面处理）

### 4.1 每个目标文件先做“四张表”

1. **符号表**：顶层类/函数/常量、各自行号、公开/私有、是否从 facade 导出；
2. **依赖表**：该文件 import 谁、谁 import 它（AST，含 `from ... import` 与 `import ... as`）；直接引用者数量；
3. **测试表**：哪个测试文件覆盖哪个符号/行为；无测试覆盖的路径单独列出；
4. **状态表**：模块级可变状态、缓存、单例、循环依赖、延迟 import（如 `commands.py` 的历史延迟 import）。

只有四张表齐了才允许开始拆。缺失一项就补，不靠“看起来不高耦合”。

### 4.2 每个拆分的执行顺序

1. **先写 characterization tests**：针对该文件当前行为的关键输出/异常/事件顺序；不修 bug。
2. **先提取叶子 helper**（无状态、无循环依赖）；再提取类型/数据类；最后拆主类或主流程。
3. **每步保持可导入**：每完成一小步就跑 `python -m compileall` + 全仓 import-all + 相关测试。
4. **不保留旧 shim**：内部路径更新完；公开 facade 用 `baldric_coding/__init__.py` 再导出，但内部旧模块路径不保留。
5. **拆完做差异检查**：`git diff --stat` 行数变化合理；符号表前后集合一致；facade `__all__` 不变；测试断言零改动。

### 4.3 新增的自动化检查（建议在 Task 0 先加）

- `scripts/check_import_graph.py`：用 AST 生成模块 import 图，检测：
  - `baldric_agent` 不得 import `baldric_coding` / `textual` / `rich`；
  - `baldric_ai` 不得 import `baldric_coding` / `baldric_agent`；
  - `session/` 不得 import `tui/`；
  - `tools/`、`backends/`、`trust/` 不得 import `tui/`；
  - 新拆分文件不得产生未解析 import。
- `tests/test_public_surface.py`：覆盖 `baldric_coding` 139、`baldric_ai` 37、`baldric_agent` 56；`__all__` 静态 list literal（前半已完成 ai/agent）。
- `scripts/check_split_inventory.py`：对每个拆分目标做“拆分前符号集合 vs 拆分后 public import 集合”的集合差；缺一项即失败。

## 5. 任务分解

### Task 0：安全网与基线（Phase 2 的“M-1”）

- 记录 `main` @ `57e6908`；跑基线四件套并写台账。
- 加 `scripts/check_import_graph.py`、`tests/test_public_surface.py`（`baldric_coding` 139 + ai/agent 当前契约）。
- 建立 `plans/layout-phase-2-ledger.md` 或在 Phase 1 台账续页记录每个拆分的：目标文件、符号表、测试表、commit、全量结果。
- **验收：** 新增检查全绿；基线四件套全绿。

### Task 1：`rpc.py → modes/rpc/`（先移动后拆分）

- 1a：`git mv src/baldric_coding/rpc.py src/baldric_coding/modes/rpc.py`（新建 `modes/`；零逻辑；更新 `cli.py` import；`test_rpc.py` 通过）。
- 1b：拆成 `modes/rpc/{__init__.py,server.py,wire.py,session.py}`；原 `run_rpc_session` 等公开入口在 `modes/rpc/__init__.py` 再导出。
- 测试：`tests/test_rpc.py` 全部；新增 JSON line 协议 golden test（输入/输出逐行）。
- **验收：** `uv run baldric --version`、TUI/print 不回归；`test_rpc.py` 全绿。

### Task 2：`commands/registry.py` → `commands/` 一命令一文件

- 文件：`registry.py` 保留 `CommandSession`、`CommandResult`、`CommandContext`、`SlashCommand`、`CommandRegistry`、`create_default_command_registry`、解析/格式化公共 helper；每个 `_xxx_command` 移入 `commands/<name>.py`。
- 测试：`tests/test_commands.py` + 新增 `command name`/help/参数/返回 shape 表。
- **验收：** 35 个命令注册顺序、名字、帮助文本、返回值类型不变；`test_commands.py` 全绿。

### Task 3：`tools/registry.py` → `tools/` 一工具一文件 + 公共 helper

- `base.py`：`ToolDefinition`、`ToolInputError`、`ImageSupportState`、`ReadOperations` 等；
- `truncate.py`/`output_accumulator.py`：截断/输出累计；
- `read.py`/`write.py`/`edit.py`/`bash.py`：各工具 schema + executor + 私有 helper；
- `renderers/`：每个工具的渲染器；
- `registry.py`：`create_coding_tools` 聚合；`image_processing.py` 保持独立模块。
- 测试：`tests/test_coding_tools.py`、`test_tool_arguments.py`、`test_tool_history.py` + 工具 schema golden JSON。
- **验收：** 所有 tool name/description/参数 schema 与当前完全一致；`create_coding_tools` 返回的列表顺序不变。

### Task 4：`session/export.py` → `session/export/` package

- `writer.py`（JSONL/HTML 文件写入、路径/格式）、`html.py`（`render_session_html`）、`tree.py`（tree/active path）、`entry.py`（entry 渲染）、`theme.py`（CSS/主题）、`format.py`（时间/摘要/转义）。
- 测试：`tests/test_session_export.py` + 全量 HTML golden（对固定 fixture 的完整输出做 hash）。
- **验收：** JSONL/HTML 输出与基线 hash 完全一致；`export_session_html`/`export_session_jsonl` 签名不变。

### Task 5：`providers/config.py` → `providers/config/` package（独立判断新增）

- 拆分：`models.py`、`settings.py`、`catalog.py`、`validation.py`、`selection.py`、`thinking.py`、`__init__.py` 再导出。
- 测试：`tests/test_provider_config.py`、`test_provider_catalog.py`、`test_provider_runtime.py` + provider settings golden JSON。
- **备注：** 这是对蓝图 `providers/config.py` 单文件的偏离，理由：2,545 行/118 顶层符号；按蓝图规则 4 更新蓝图树为 `providers/config/` 包。
- **验收：** `baldric_coding.providers.config` 的公开符号集合不变；`baldric_coding/__init__.py` import 路径不变；provider settings 读写字节级一致。

### Task 6：`session/session.py` 分阶段拆

- 6a：提取模块级纯 helper（tree layout/format、provider selection、resource signatures、prompt append）到 `session/session_helpers.py` 或对应目标模块；`CodingSession` 类不变。
- 6b：把 turn 执行循环/事件派发抽到 `session/runtime.py`（`SessionRuntime` 或函数集合），`CodingSession` 保留公开方法委托。
- 6c：把资源加载/刷新/扩展能力抽到 `session/services.py`；`session.py` 只保留状态/历史/公开 API。
- 测试：`tests/test_coding_session.py`、`test_session.py`、`test_session_manager.py` + 新增事件序列 golden tests（开始/结束/错误/取消/队列）。
- **停止条件：** 任何事件顺序、异常类型、取消语义、队列语义变化 → 停下，不继续拆。

### Task 7：`tui/app.py` → `tui/app/` package

- 先按 Screen 类拆分：`screens/login.py`、`screens/session_picker.py`、`screens/model_picker.py`、`screens/theme_picker.py`、`screens/tools_reference.py`、`screens/prompt_templates.py`、`screens/extensions.py`；
- 再拆 `BaldricTuiApp` 核心：`app.py`（生命周期/事件循环）、`runtime.py`（启动/装配）、`bindings.py`（keybindings/help）；
- `tui/app/__init__.py` re-export `BaldricTuiApp`、`run_tui_app`（仅此二名保持公开）。
- 测试：`tests/test_tui_app.py` 按 Screen 分组；`test_tui_components.py`、`test_tui_adapter.py`；Textual 启动 smoke。
- **验收：** 所有 Screen 的交互路径与快捷键不变；`from baldric_coding.tui import BaldricTuiApp` 不变；启动/退出/调整窗口无回归。

### Task 8：`tui/widgets.py` → `tui/widgets/` package

- 按 widget 家族拆：`transcript.py`、`sidebar.py`、`markdown.py`、`tool_render.py`、`chat.py`、`files.py`；
- `tui/widgets/__init__.py` 再导出原有 18 个公开 widget/helper 名称。
- 测试：`tests/test_tui_components.py`、`test_tui_app.py` 中 widget 部分；渲染快照（plain text / Rich styles）对比。
- **验收：** `tui/__init__.py` 导出的 widget 名称不变；聊天/侧栏渲染快照逐项一致。

### Task 9：`cli.py` → `cli/` package + `modes/` 拆分（独立）

- `cli/__init__.py` 暴露 `app`，保证 `baldric_coding.cli:app` 不变；
- `cli/app.py`（Typer 定义）、`cli/options.py`（argv）、`cli/modes.py`（选择 TUI/print/RPC）；
- 具体 `run_openai_tui`/`run_openai_print_mode`/`run_openai_rpc_mode` 移到 `modes/` 对应模块；`cli` 只负责决定模式与装配。
- 测试：`tests/test_cli.py` + 入口点 smoke；`uv run baldric --version`/`-p`、TUI 启动、RPC smoke。
- **验收：** 入口点 `baldric_coding.cli:app` 不变；`baldric --help` 输出不回归；三种模式 cold start 正常。

### Task 10：可选扩展（P2，独立评估后做）

- `extensions/builtins/subagents/extension.py`（1,782 行）→ `subagents/manager.py` + `formatting.py` + `tools.py` + `extension.py` 轻编排；
- `extensions/builtins/llama_cpp/service.py`（1,727 行）→ `service.py` + `router.py` + `models.py` + `probe.py`；
- 不在核心 wave 内，等前 9 个任务稳定后再做；先写行为测试。

### Task 11：测试树与仓库卫生（独立）

- 按 §1.5 拆测试文件；先把 `tests/conftest.py` 的跨文件 import 解耦。
- `examples/extensions/` 与 `data/examples/extensions/` 去重（单独小 PR）。
- `dev-notes` / `website/content` 路径收口（只改用户可见文档，不追改历史 phase 记录）。

## 6. 批次与停止点

| 批次 | 内容 | 停止点 |
|---|---|---|
| **2A** | Task 1 `rpc`、Task 2 `commands`、Task 3 `tools` | 每任务一个 commit；批次末全量 + 包根导入 + wheel |
| **2B** | Task 4 `session/export`、Task 5 `providers/config`、Task 6 `session/session` | Task 6 开始前单独停一次；批次末全量 + 事件 golden |
| **2C** | Task 7 `tui/app`、Task 8 `tui/widgets` | 每任务拆 Screen/widget 家族；批次末全量 + TUI smoke |
| **2D** | Task 9 `cli`/`modes`、Task 10 可选扩展、Task 11 测试树/卫生 | 终报 |

## 7. 每个任务的验收清单

- [ ] 符号表/依赖表/测试表/状态表已写进 Phase 2 台账；
- [ ] characterization tests 先绿；
- [ ] 拆分后全仓 import-all 通过；`uv run mypy` 无新增错误；
- [ ] `uv run ruff check .`、`ruff format --check .` 通过；
- [ ] 相关测试全绿；批次末全量 `uv run pytest -q` 0 failed；
- [ ] `baldric_coding.__all__` 139、`baldric_ai.__all__` 37、`baldric_agent.__all__` 56 不变；
- [ ] `uv build --wheel` 成功，新增子包/资源在 wheel 内；
- [ ] 文档（蓝图、layout-mapping）已更新到实际位置；
- [ ] 无行为变化：无断言修改、无新增 skip/xfail、无 `# type: ignore`。

## 8. 明确不做

- 不搬 `baldric_ai` / `baldric_agent` 目录（另行计划，但 API 策略已就绪）；
- 不拆 `extensions/api.py` / `extensions/runtime.py`（公开扩展契约，风险大于收益）；
- 不为拆分新建空包（`mcp/`、`security/` 等实际功能未落地）；
- 不为了“看起来整齐”拆 `providers/loader.py` / `backends/contracts.py` 这类单一职责文件。
