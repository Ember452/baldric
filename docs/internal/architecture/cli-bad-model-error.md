# CLI：把错误的 `--model` 呈现为干净错误（issue #265）

## 变更了什么

所选 provider 未声明该模型时，`baldric --model <bad-model>` 不再以 `anyio`/`asyncio` 堆栈崩溃。`src/baldric_coding/cli.py` 的两个 `except` handler 从 `RuntimeError` 放宽为
`(RuntimeError, ValueError)`：

- **TUI** 启动分支（`main()` → `anyio.run(run_openai_tui, …)`），与
- **print-mode** 分支（`main()` → `anyio.run(run_openai_print_mode, …)`）。

`ProviderConfigError(ValueError)` 由 `validate_provider_model()` 在事件循环深处抛出
（经 `resolve_provider_selection()` →
`_resolve_tui_startup_selection()` / `run_openai_print_mode`）。因为 handler 只捕获 `RuntimeError`，`ValueError` 子类作为未处理异常逃逸并打印多帧堆栈。捕获 `ValueError` 让 `typer.BadParameter` 原样呈现既有的友好消息：

> Invalid value: Model is not configured for provider local: llama. Available
> models: qwen

同文件的 `export` 命令已用正确模式
（`except (RuntimeError, ValueError)`），是参照。

## 为什么存在

报告于 https://github.com/huggingface/tau/issues/265。provider 目录刻意 provider 特定，未知/拼错的模型名是常见用户错误。可执行的消息（列出该 provider 的有效模型）早已存在于 `provider_config.validate_provider_model`；只是没有经 CLI 入口干净呈现。

这让校验逻辑留在 `provider_config.py` 作为消息的唯一事实来源，并恢复所有 `--model` 入口（TUI、print mode、导出）的一致性。

## 与设计的对应

纯 CLI 层修复。不触碰：

- 可移植 agent harness（`baldric_agent`）、
- provider/model 流式层（`baldric_ai`）、或
- Textual TUI 渲染。

校验本身已住在 `baldric_coding.providers.config`；错的只是 CLI 的错误边界。这与"CLI 错误处理应消费低层错误而不是让它们以原始堆栈泄漏"的架构原则一致。

## 怎么测试

回归测试（验证过修复前失败、修复后通过）：

```bash
uv run pytest tests/test_cli.py -k "bad_model" -v
```

- `test_tui_surfaces_bad_model_as_clean_error`
- `test_print_mode_surfaces_bad_model_as_clean_error`

两者 monkeypatch `load_provider_settings`（在 `cli` 与 `tui.app`
两个命名空间，因为各自导入了它），返回唯一模型为 `qwen` 的 provider，然后以 `--model llama --provider local`（TUI）与加 `-p hello`（print mode）调用 CLI runner。断言 `exit_code == 2`（Typer 的
`BadParameter` 约定）且输出面板包含
`"Model is not configured for provider local: llama. Available models: qwen"`。

全量：

```bash
uv run pytest -q
uv run ruff check src/baldric_coding/cli.py tests/test_cli.py
uv run ruff format --check src/baldric_coding/cli.py tests/test_cli.py
```

## 注记 / 后续

- 原 issue 草稿错误地声称 print mode 路径已处理 `ValueError`；那段 `except (RuntimeError, ValueError)` 其实来自 `export` 命令。实证复现确认 print mode *也*坏了，所以两条路径一起修。
- 更大的后续（不在本范围）：审计剩余的 `anyio.run(...)` 调用点，抽一个共享错误处理 helper，让所有入口用同一个 handler、不再漂移。循环前校验（进事件循环前解析 provider/model）是另一项可选打磨。
