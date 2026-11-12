# 阶段 G 执行记录：frontends 收口（G1/G2/G3）

- 日期：2026-11-13
- 对应计划：[../plans/2026-11-12-structural-rearchitecture.md](../plans/2026-11-12-structural-rearchitecture.md) §5 阶段 G
- 分支：`refactor/structural-v2`
- 前置：A0–F 已提交。

## G1：`tui → frontends/tui`（提交 88a2305）

- `git mv runtime/tui → runtime/frontends/tui`（40 文件）；新增 `runtime/frontends/__init__.py`。
- 全仓 `baldric.runtime.tui → baldric.runtime.frontends.tui`（75 文件 / 420 处），UTF-8 显式 IO，校验：旧 token 0 残留、`E2 80 3F` 损坏 0、em-dash 计数与 HEAD 一致。
- scanner RULES：7 条「core 不得 import TUI」改为 `baldric.runtime.frontends.tui`；stage D 后冗余的 `backends` 条并入 `providers` 前缀。
- scoped instructions (`runtime/AGENTS.md`) 重写为新布局，且**字节数变小**（1975 < 基线 2004），agent-guidance ratchet 收紧；用户文档 `custom-frontend.md` 同步。
- 基线：40 条 tui 条目重命名 + 新增 `frontends/__init__.py`，行数零变化；supp 138 不变。

## G2：`modes/rpc → frontends/rpc`（提交 06285e6）

- `git mv runtime/modes/rpc → runtime/frontends/rpc`；删除空 `runtime/modes/`（其 `__init__` 仅 docstring）。
- 6 处引用改 `baldric.runtime.frontends.rpc`（cli.py + rpc 内部 + 2 个测试）。
- 基线：4 条 rpc 条目重命名、删掉 `modes/__init__`；supp 138 不变。

## G3：`cli print 路径 → frontends/print/`（本提交）

- 新增 `frontends/print/mode.py`：搬入 `run_openai_print_mode`、`run_print_mode`、`_MemorySessionStorage`、`_format_terminal_command_result`、`_command_name`（逐字等价搬迁，~390 行）。
- 新增 `frontends/print/__init__.py`（re-export 两个入口）。
- 新增 `frontends/session_records.py`：`resolve_mode_session_record` / `create_mode_session`（原 `_print_session_record` / `_create_print_session`）——**print 与 rpc 共用**，故放 frontends 共享模块而非 print 子包（避免 frontends 子包互相依赖）。
- `cli.py`：删除搬走的 print 代码块（1539 → 1031 行）与因其失用的 16 个 import；`run_openai_rpc_mode` 改调 `resolve_mode_session_record`；从 `frontends.print` / `frontends.session_records` 导入。
- 测试：3 个文件的 `run_print_mode` 导入改新位置；`test_cli.py` 里对 `_print_session_record`/`_create_print_session` 的调用改公开名；monkeypatch 目标从 `cli.*` 改为 `print_mode.*`（符号已不在 cli 模块内）。
- 渲染实现**不搬**：`frontends/print` 只消费 `core/rendering`（`create_event_renderer`），符合 §3.1。

## 验收（证据）

- G1：fast suite 2284 passed；TUI 767 passed；guards 70；mypy 无新增。
- G2：RPC 测试 92 passed；guards 70；fast 2283 passed（1 个已知 TUI 抖动，重跑通过）。
- G3：cli 域 120 passed；fast suite **2284 passed / 52 skipped**；TUI **767 passed**（首次整套运行为已知 Windows asyncio 挂起，重跑全绿）；guards 70；`ruff`/`format`/`import-graph`/`agent-guidance`/`structure`/`suppression` 全绿；mypy 14 个已知错误、无新增。
- 基线 diff：G3 新增 3 个文件（print/__init__、print/mode、frontends/session_records）；cli.py 1539→1031；supp 总数 138 不变。

## 遗留

- `platform/__init__` 导出面收窄、`baldric.api` 稳定面治理（可选清理）。
- 阶段 H：session 消肿（当前 2060 行 / 183 方法）。
