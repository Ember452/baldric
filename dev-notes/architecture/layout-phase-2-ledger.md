# Layout migration ledger — phase 2 (splits)

Branch: `refactor/layout-phase-2`
Plan: `plans/layout-phase-2-splits.md`
Baseline: `main` @ `36fcc69` (Phase 2 plan merge; source identical to `57e6908`)
Phase 1 ledger: `dev-notes/architecture/layout-migration-log.md`

## Baseline (Task 0)

| Check | Result |
|---|---|
| CI baseline | PR #31 (API stabilization) all green on Python 3.12 / 3.13 / 3.14 |
| `tests/test_rpc.py` baseline | `19 passed, 1 skipped` |
| `tests/test_public_surface.py` | 139 coding facade names pinned |
| `scripts/check_import_graph.py` | `import-graph: OK` |

## Task 0 — safety net

- **Commit:** `e9dca2b` `test(architecture): add phase 2 import-graph and public-surface guards`
- `scripts/check_import_graph.py`: AST import-direction guard; rules cover
  `baldric_agent → coding/textual/rich`, `baldric_ai → coding`, and
  `session/tools/backends/trust/context/providers → tui`.
- `tests/test_public_surface.py`: pins the explicit `baldric_coding.__all__`
  (139 names, no module objects).
- Existing `tests/test_public_api_contract.py`: pins `baldric_ai` 37 /
  `baldric_agent` 56 symbols and static-list form.

## Task 1 — `rpc.py` → `modes/rpc/`

- **Start commit:** `36fcc69`
- **Move commit:** `0a856bb` `refactor(layout): move rpc into modes package`
- **Content:** `git mv src/baldric_coding/rpc.py src/baldric_coding/modes/rpc.py`;
  new `modes/__init__.py` docstring only; `cli.py` and `tests/test_rpc.py` imports.
- **Move checks:** rename detection `rpc.py => modes/rpc.py (100%)`; residual old
  `baldric_coding.rpc` references `(none)`; `tests/test_rpc.py` `19 passed, 1 skipped`.
- **Split commit:** `a2aa2e9` `refactor(layout): split rpc into modes/rpc package`
  - `modes/rpc/session.py`: `RpcSession` Protocol
  - `modes/rpc/wire.py`: wire serializers and command argument helpers
  - `modes/rpc/server.py`: `RpcServer` + `run_rpc_session`
  - `modes/rpc/__init__.py`: `__all__ = ["RpcServer", "RpcSession", "run_rpc_session"]`
- **Split checks:** `import-graph: OK`; `import baldric_coding.modes.rpc` →
  `['RpcServer', 'RpcSession', 'run_rpc_session']`; `tests/test_rpc.py` +
  `test_cli.py` + public-surface tests `110 passed, 14 skipped`; mypy
  `14 errors in 2 files (checked 164 source files)` (same baseline errors);
  ruff/format pass.
- **Next:** Task 2 `commands/registry.py` split (Wave 2A).

## Task 2 — `commands/registry.py` → domain modules

- **Commit:** `0e203f5` `refactor(layout): split commands registry into modules`
- **Structure:** `commands/base.py` (types/`CommandRegistry`), `core.py`
  (lifecycle/export/status/help), `session.py` (resume/tree/name),
  `resources.py` (skills/prompts/context/diagnostics/system), `config.py`
  (model/thinking/theme/local/login/logout), `formatting.py` (diagnostics/reload/session),
  `registry.py` (only `create_default_command_registry` + re-exports).
- **Independent deviation:** not one file per every tiny command; grouped by domain
  to avoid 20 boilerplate files. The registry remains the single public import path.
- **Checks:** `tests/test_commands.py` + `test_prompt_templates.py` +
  `test_tui_autocomplete.py` → `116 passed`; broader consumers
  (`test_extensions.py`, `test_cli.py`, `test_coding_session.py`) → `418 passed, 21 skipped`.
  `import baldric_coding.commands.registry` re-exports the original public names and
  registers 23 commands; ruff/format pass.

## Task 3 — `tools/registry.py` → base + per-tool modules

- **Commit:** `9f8e935` `refactor(layout): split tools registry into modules`
- **Structure:** `tools/base.py` (constants/types/arg + file-lock primitives),
  `output_accumulator.py`, `truncate.py`, `read.py`, `write.py`, `edit.py`,
  `bash.py`, and `registry.py` (only `create_coding_tools` + re-exports).
- **Checks:** `tests/test_coding_tools.py` + `test_tool_arguments.py` +
  `test_tool_history.py` → `48 passed, 8 skipped`; with `test_image_processing.py`
  → `64 passed, 8 skipped`; import smoke (`create_coding_tools`, `ToolInputError`) OK;
  `ruff`/format pass; mypy `14 errors in 2 files (checked 177 source files)`
  (same baseline Windows `fcntl` errors).
- **Note:** kept `asyncio` imported in `tools/registry.py` because
  `tests/test_coding_tools.py` monkeypatches `tools_module.asyncio.to_thread`
  (checked: test passes).

**Batch 2A end full suite:** `2355 passed, 122 skipped in 242.56s` — 0 failed.

## Task 4 — `session/export.py` → `session/export/`

- **Commit:** `17f01d0` `refactor(layout): split session export into writer and renderer`
- **Structure:** `session/export/writer.py` (paths/formats/file writes),
  `html.py` (HTML render pipeline), `jsonl.py` (JSONL serialization),
  `__init__.py` (original public API re-export).
- **Checks:** `tests/test_session_export.py` → `19 passed`.
- **Known residual:** `html.py` is still 1,846 lines (`render_session_html` ~1,004
  lines); further helper/asset extraction is deferred. It is a single rendering
  pipeline, and splitting it now has high output-formation risk for low structural
  gain; this is recorded rather than silently claimed complete.

## Task 5 — `providers/config.py` → `providers/config/`

- **Commit:** `0e94274` `refactor(layout): split provider config into layered modules`
- **Structure (acyclic layers):**
  - `models.py`: dataclasses/types/constructors + model validation helpers
  - `credentials.py`: credential lookup and `provider_has_usable_credentials`
  - `validation.py`: JSON parsing/preferences + `_provider_from_json`
  - `catalog.py`: effective catalog, provider merge, catalog persistence
  - `selection.py`: provider/model selection, thinking, runtime config conversion
  - `settings.py`: load/save/migrate/write settings
  - `__init__.py`: original public surface re-export (44 names, incl. `ProviderConfig`)
- **Dependency correction:** first split exposed real cycles (`models ↔ validation`,
  `catalog → selection`, `selection ↔ validation`); regenerated by dependency layers
  instead of adding shims. `models` owns model validators; selection imports catalog
  and validation; settings imports all lower layers.
- **Compatibility:** preserved module-level `environ`, `copy2`,
  `_write_provider_settings`, `save_user_catalog_entries` on the package module and
  made the relevant call sites resolve them dynamically, because existing tests
  monkeypatch those package attributes.
- **Checks:** `tests/test_provider_config.py` + `test_provider_catalog.py` +
  `test_provider_runtime.py` → `140 passed`; `test_public_surface.py` +
  `test_public_api_contract.py` → 3 passed; ruff/format pass; mypy
  `14 errors in 2 files (checked 186 source files)` (same Windows `fcntl` baseline).
- **Full suite note:** first Task 5 full run found one monkeypatch-compat failure
  (`test_dynamic_provider_operations_never_call_durable_write_paths`) — fixed and
  re-verified. A subsequent full run timed out inside a known async/TUI test
  (no assertion failure); targeted provider and command tests remain green.

## Task 6a — `session/session.py` top-level helpers extracted

- **Commit:** `8e4a45d` `refactor(layout): extract session helper modules`
- **Structure:** `session/tree_helpers.py` (message/tree/export helpers),
  `session/provider_helpers.py` (`_PreparedProvider`, provider/thinking setup),
  `session/resource_helpers.py` (`SessionResources`, `TerminalCommandRequest`,
  terminal parsing, resource signatures/loading, prompt/history helpers).
  `CodingSession`, `CodingSessionConfig`, and the dataclass definitions that are
  part of the session object model remain in `session.py`.
- **Staging decision:** only top-level helpers moved in 6a; the 169-method
  `CodingSession` class is unchanged. `session.py` shrinks from 5,224 to 4,171 lines;
  class/state splitting is deliberately deferred to 6b/6c.
- **Compatibility found and fixed during split:**
  - dataclass decorators for `_PreparedProvider`, `SessionResources`,
    `TerminalCommandRequest` had to move with their classes;
  - `create_model_provider` is resolved through `session.session` dynamically
    because tests monkeypatch that module attribute;
  - helper imports in `session.py` use explicit `name as name` re-exports so both
    mypy and external imports keep working.
- **Checks:** `test_coding_session.py` → `182 passed, 7 skipped`; broader session/CLI/
  extension/TUI-adapter group → `613 passed, 25 skipped`; `test_public_surface` and
  public contract pass; ruff/format pass; mypy
  `14 errors in 2 files (checked 189 source files)` (same Windows `fcntl` baseline).

## Task 6b — turn loop, persistence, and compaction moved to `session/runtime.py`

- **Commit:** `ac40933` `refactor(layout): move session turn loop and compaction runtime`
- **Structure:** `session/runtime.py` owns `prompt`, `continue_`, persistence
  (`_persist_*`, `_append_*`, `_ensure_session_*`), auto-naming, auto-compaction,
  compaction planning/summary, and the `_PendingMessageWrite` / `CompactionPlan` /
  `_GeneratedSummary` dataclasses.
- **Design decision:** free functions taking `session: CodingSession` + thin
  method delegates, not mixins. This keeps mypy strict usable: every moved function
  is checked against the real `CodingSession` type instead of an under-annotated mixin.
- **Size:** `session.py` 4,171 → 3,538 lines; 36 methods delegated.
- **Compatibility risks found and fixed:**
  - keyword-only arguments had to be passed as keywords in wrappers;
  - async-generator wrappers must explicitly `aclose()` the inner runtime stream,
    otherwise closing `session.prompt(...)` does not run the original cleanup
    (auto-naming cancellation test caught this);
  - `DEFAULT_COMPACTION_KEEP_RECENT_TOKENS` is read through `session.session`
    dynamically so existing monkeypatch tests still affect compaction;
  - runtime generator return types use `AsyncGenerator[..., None]` so `.aclose()` is
    typed.
- **Checks:** `test_coding_session.py` → `182 passed, 7 skipped`; broad group
  (session/CLI/extensions/TUI adapter/full-output/chat/subagent integration) →
  `639 passed, 25 skipped`; one TUI subagent test failed in the batch but passed in
  isolation (known flake, not a deterministic regression); ruff/format pass; mypy
  `14 errors in 2 files (checked 190 source files)` (same Windows `fcntl` baseline).

### Remaining Task 6 work

- `session.py` is 3,538 lines / 133 methods after 6b. Remaining seams:
  model/thinking selection (`set_model`, `select_provider_model`, preview/commit),
  lifecycle (`reload`, `resume`, `new_session`, `_adopt_replacement`),
  session-tree/query surface.
- These are state-heavy and are intentionally not being moved in the same commit
  as the turn loop.

## Task 6c — model/thinking selection moved to `session/model_selection.py`

- **Commit:** `84cbe3e` `refactor(layout): move session model selection and thinking`
- **Moved:** `ModelChoice` / `ModelSelectionResult`, `set_model`,
  `apply_startup_model_override`, `select_provider_model`, inference-provider
  selection, scoped models, preview/commit, `set_provider`, thinking level
  apply/persist/sync/image-support helpers.
- **Design:** same free-function + thin-delegate pattern; `ModelChoice` remains a
  public re-export from `session.session`.
- **Size:** `session.py` 3,538 → 3,014 lines; `model_selection.py` 881 lines.
- **Checks:** `test_coding_session.py` → `182 passed, 7 skipped`; broad
  session/CLI/extensions/TUI-adapter group → `613 passed, 25 skipped`; ruff/format
  pass; mypy `14 errors in 2 files (checked 191 source files)` baseline.
- **Remaining Task 6 seams:** lifecycle (`reload`, catalogs, `resume`,
  `new_session`, `_adopt_replacement`, `aclose`) and tree/query surface.

## Task 6d — lifecycle moved to `session/lifecycle.py`

- **Commit:** `95f0650` `refactor(layout): move session lifecycle to lifecycle module`
- **Moved:** `reload`, model-catalog refresh/publish, `resume`, session naming
  persistence, `new_session`, `_adopt_replacement`, `compact`/`compact_detailed`,
  `aclose`/owned-resource close, command handling, session indexing, prompt
  expansion, terminal command execution.
- **Size:** `session.py` 3,014 → **2,216 lines** (from 5,224 originally);
  `lifecycle.py` 1,173 lines.
- **Compatibility fixes:** lifecycle calls back into the session module for
  `create_model_provider`, `load_provider_settings`, `_load_session_resources`,
  `_await_cleanup_completion`, `_finish_*_close`, and dataclass construction, so
  existing monkeypatch tests still affect the implementation; `cast(..., "Type")`
  used for runtime class lookups only needed by typing.
- **Checks:** `test_coding_session.py` → `182 passed, 7 skipped`; broad
  session/CLI/extensions/TUI-adapter group → `613 passed, 25 skipped`; ruff/format
  pass; mypy `14 errors in 2 files (checked 192 source files)` baseline.

### Task 6 final state

`session/session.py` now contains the state object, properties/query surface, and
remaining tree/branch methods. Turn runtime, persistence/compaction, model/thinking
selection, lifecycle, providers, resources, and tree helpers are separate modules.
A further split of the remaining tree/branch query surface is possible but lower
value than moving to the 9k-line TUI app; Task 7 is the next high-value target.

## Task 7 — TUI screens extracted from `tui/app.py`

- **Commit:** `f9cc9ae` `refactor(layout): extract tui screens package`
- **Result:** `tui/app.py` 9,106 → **6,207 lines**; new `tui/screens/` package:
  `extension`, `tools_reference`, `prompt_templates`, `sidebar`, `session_picker`,
  `skill_picker`, `tree_picker`, `command_output`, `login`, `theme`, `model_picker`,
  plus `support.py` for the shared `SessionCompletionRecord` and 12 picker helpers.
- **Boundary:** extracted the contiguous screen block (33 screen classes) and the
  13-name support closure. `PromptInput` and the `BaldricTuiApp` core remain in
  `app.py`; `tui/screens/__init__.py` exports 36 screen names.
- **Compatibility fixes:**
  - `app.py` keeps explicit re-exports for all screen/support names imported by
    tests (`name as name`), including private picker helpers and `BindingEntry`;
  - screens resolve `BaldricTuiApp` only under `TYPE_CHECKING` and use
    `cast("BaldricTuiApp", ...)`, avoiding a runtime import cycle;
  - `get_oauth_provider` (login) and `_atomic_write_sidebar_file` /
    `_write_staged_utf8` (sidebar) resolve through `tui.app` dynamically because
    existing tests monkeypatch those module attributes.
- **Checks:** `test_tui_app.py` → `457 passed, 40 skipped`; all TUI test files
  except the known slow subagent integration → `671 passed, 75 skipped`, with one
  model-picker test failing in batch and passing in isolation (known flake);
  public-surface contract passed; ruff/format pass; mypy
  `14 errors in 2 files (checked 205 source files)` baseline.
- **Known residual:** `BaldricTuiApp` itself is still ~4.2k lines and `PromptInput`
  remains in `app.py`; both are state-heavy. The next candidates are widgets
  (`tui/widgets.py`, 3,351 lines) and `cli.py`/`modes`, not another screen split.

## Task 8 — sidebar widgets split out of `tui/widgets.py`

- **Commit:** `6f4fadf` `refactor(layout): split tui widgets sidebar family`
- **Structure:** `tui/widgets/` package:
  - `core.py`: transcript/markdown widgets and helpers (2,411 lines)
  - `sidebar.py`: sidebar widget family + 4 constants (981 lines)
  - `__init__.py`: full original import surface re-export (130 names)
- **Boundary evidence:** sidebar dependency closure was 47 names + 4 constants and
  had zero references to transcript/markdown names; this is why it was safe to move
  without touching the transcript core.
- **Compatibility fixes:**
  - package-level `TRANSCRIPT_WINDOW_*` constants and `run` are read dynamically
    from `tui.widgets` because tests monkeypatch the package attributes;
  - `_GIT_BRANCH_CACHE` moved with `_GitBranchLookup`/`_git_branch`;
  - package `__init__.py` re-exports every original widget name, including private
    names imported by tests.
- **Checks:** `test_tui_app.py` + `test_tui_components.py` + `test_tui_chat_channels.py`
  + `test_subagents_ui.py` → `518 passed, 43 skipped`; ruff/format pass; mypy
  `14 errors in 2 files (checked 207 source files)` baseline.
- **Remaining:** transcript/markdown `core.py` still 2.4k lines; further split would
  need cross-cutting helpers and is deferred.








