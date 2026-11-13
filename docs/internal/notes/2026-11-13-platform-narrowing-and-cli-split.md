# platform 根收窄 + cli 拆分 + 阶段 H issue（2026-11-13）

- 背景：维护者确认「H 不做、其余都做」，并在 GitHub 记录 H：
  [issue #73](https://github.com/Ember452/baldric/issues/73)。
- 分支：`refactor/structural-v2`

## 一、`platform/__init__.py` 收窄：116 → 82，只剩平台自有模块

**规则**：平台包根只 re-export `baldric.runtime.platform.*` 自己的模块；provider 域契约与 protocol 形状从各自归属模块导入。

- 实测原 116 个导出里 **34 个来自 `providers.backends.contracts`**（stage E 的聚合泄漏），其中 3 个仍被从根使用（`LocalBackendRegistry`、`LocalConfirmationChoice`、`LocalConfirmationRequest`）。
- 改动：删除该 import 块与对应 `__all__` 条目；6 个测试文件 9 处导入改为从 `providers.backends.contracts` 取。
- 新增守卫 `test_platform_root_reexports_only_platform_owned_names`（AST 断言包根无跨域 import），防聚合面复活。
- 结果：249 行 / 116 导出 → **179 行 / 82 导出**，零消费方 churn（除上述 3 个符号的 9 处导入）。

## 二、cli 拆分：1139 → 591 行（达成计划 <600 目标）

| 新模块 | 内容 |
|---|---|
| `frontends/rpc/mode.py`（141 行） | `run_openai_rpc_mode`（provider 选择 + RPC 生命周期），与 `frontends/print/mode.py` 对称 |
| `frontends/tui/mode.py`（84 行） | `run_openai_tui` + 其启动 banner 策略（release notes / 延迟 PyPI 检查），与 print/rpc 对称 |
| `cli_io.py`（30 行） | `_is_utf8_encoding` / `_force_utf8_streams` |
| `cli_commands/`（8 文件） | providers / install / extensions / setup / update / sessions / export + 包 `__init__` |

- `cli.py` 保留：`app`（typer）、`main()`（参数解析 + 模式分派）、update-notice/host 辅助、prompt 输入解析。
- 命令仍是普通函数（CLI 用 `allow_extra_args` 手工路由，非 typer 子命令），`cli` 导入它们到命名空间 → `monkeypatch.setattr(cli, "<command>")` 仍生效。
- 测试 patch 目标随之迁移到新模块（`install_extension`/`read_extension_registry`/`update_extension`/`remove_extension`/`BaldricPaths`/`update_baldric`/`ModelsDevRefreshResult`/`refresh_models_dev_catalog`/`export_session_command`/`render_provider_settings`，约 18 处），notice 相关测试改 patch `frontends.tui.mode`。
- `frontends.tui.mode` 现在拥有 TUI 启动 banner 策略（原在 cli），因此 cli 的 print 路径仍用 `_startup_update_notice`，TUI 路径的 release-notes/deferred 检查归前端。

## 三、阶段 H

不实现，已在 GitHub 建 issue 记录动机（"非现在更便宜型"+ 无功能驱动）、启动切入点（先切纯委托尾部 + 状态收拢）与验收标准：
[issue #73](https://github.com/Ember452/baldric/issues/73)

## 验收（证据）

- 全量 fast suite（除 TUI）：**2291 passed / 52 skipped / 0 failed**。
- TUI：**767 passed / 74 skipped / 0 failed**。
- cli 域：**120 passed**；guards：全绿（含 2 条新守卫）。
- `ruff check .` / `ruff format --check .` / `check_import_graph` / `check_agent_guidance` / `check_suppressions` / `check_structure`：全绿；`uv run mypy` 14 个已知 Windows-only 错误、无新增。
- 基线：suppression 总数 138 不变（`type: ignore[union-attr]` 随 `_force_utf8_streams` 迁到 `cli_io.py`，纯路径迁移）；structure 收紧（cli.py 1139→591、platform/__init__ 249→179）。

## 遗留（未做，均有明确理由）

- 阶段 H：issue #73（维护者决定暂不做）。
- `baldric_coding` 旧名：仅 1 处测试名已随公共面测试重写消失；`docs/internal` 130 文件 + CHANGELOG + release-notes 属历史记录，不改（维护者指示不写该口径）。
- `platform/__init__` 是否继续收窄 82 → 更小：当前 82 全是平台自有符号，无跨域聚合，已无"aggregation"问题。
