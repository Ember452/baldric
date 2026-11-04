---
title: "11 — Subagents Port Audit (Phase 2 pre-flight)"
---

Evidence gathered before porting `tau-subagents` into Baldric as a bundled
built-in extension. Nothing here is estimated: every number came from AST parsing
or a rename-normalized `git diff` against the upstream tree.

## Why the port looked cheap, and what was verified

`tau-subagents` targets upstream Tau, and Baldric is a rename of Tau `0.4.9`.
The workspace also contains that exact upstream tree (`tau-main`, `pyproject.toml:
version = "0.4.9"`), so divergence could be measured instead of assumed.

Method: copy each Baldric file, substitute `baldric|BALDRIC|Baldric` →
`tau|TAU|Tau` (case-sensitive: PowerShell's `-replace` is case-insensitive and
produced a false divergence report first — the corrected runs are below),
normalize CRLF, then `git diff --no-index -U0`. Map each hunk to its enclosing
`def`/`class` via `ast` to get symbol-level divergence.

File-level result: `tau_coding` has 48 top-level modules, `baldric_coding` has 49.
The only added file is `gitignore.py` (the #473 port).

Modules identical after rename normalization: `paths.py`, `thinking.py`,
`session_stats.py`, `events.py`, `extensions/__init__.py`.

## What the extension body actually needs

Parsed from `src/tau_subagents/**/*.py` with `ast.walk` (so deferred, in-function
imports are included): 13 modules, ~30 symbols. Every one resolves in Baldric.

| Need | Status in Baldric |
|---|---|
| `tau_coding.TauResourcePaths` | renamed: `BaldricResourcePaths`, re-exported by `baldric_coding/__init__.py` `__all__` |
| `tau_agent.events.AgentEvent`, `tau_agent.messages.AgentMessage` | present as PEP-695 `type` aliases (`events.py:73`, `messages.py:273`) |
| `provider_runtime.create_model_provider` | signature byte-identical; the only diff is one wrapped `raise` line from the ruff line-length-110 change |
| `tui.state.TuiState` attrs read by `ui/viewer.py` (`show_tool_results`, `load_messages`) | present (`state.py:126`, `state.py:719`) |
| `on("session_start")` / `on("session_shutdown")` | `extensions/runtime.py:1173-1179`, names declared in `extensions/api.py:56-57` |
| `resources.parse_markdown_resource` | same signature `(text) -> tuple[dict[str, str], str]` |
| `thinking.THINKING_LEVELS` | same 7-level tuple |

Conclusion: **the port requires no changes to the reusable core** and no new
third-party dependency (`tau-subagents` pins `tau-ai>=0.3.0` plus `textual>=8.2.8`,
which Baldric already declares verbatim).

## Where the real coupling lives: the tests, not the body

Splitting imports by directory: the extension body needs 13 modules; its test
suite needs 22. The deep/private coordinates appear only in tests:
`tau_coding.tui.app._theme_css_variables`, `PromptInput`, `TauTuiApp`,
`tau_coding.session.ModelChoice`, `TerminalCommandResult`,
`tau_coding.tools.create_coding_tools`, `tau_coding.session_stats.SessionStats`,
`tau_coding.system_prompt.ProjectContextFile`, `tau_coding.events.QueueUpdateEvent`,
`tau_ai.FakeProvider`.

Test inventory (AST-enumerated, 144 tests): `test_extension.py` 73,
`test_ui.py` 41, `test_schedule.py` 18, `test_integration_tui.py` 12.

Decision recorded here: Baldric writes its own tests for this feature rather than
importing the upstream suite, using the upstream inventory above as the coverage
checklist. The upstream tests reach into TUI internals that have since diverged
(`tui/state.py` +113/−48, `tui/widgets.py` +86/−97, `tui/app.py` +148/−203), so
importing them would import that divergence too.

## Two deliberate deviations from upstream

1. **Project trust.** Upstream reads `<cwd>/.tau/agents/*.md` and
   `<cwd>/.tau/subagents.json` unconditionally. Baldric gates project resources on
   project trust (`session.py:576` calls `resource_paths_with_project_trust(...)`;
   `session.py:607` loads project extensions only when trusted). Porting upstream's
   behavior as-is would let an untrusted repository inject a subagent system
   prompt and tool allow-list, which is a security regression, not a style choice.
   The extension context exposes `cwd` and `paths` but not the session's trust
   decision, so the read-only trust flag is surfaced on the extension context
   instead of being re-derived inside the extension (re-deriving could disagree
   with the decision the session already made).
2. **Worktree cleanup failure.** Upstream `worktree.py` ends cleanup with
   `except Exception: _remove_worktree(); return WorktreeResult(has_changes=False)`,
   i.e. a failed commit/branch is reported as "nothing changed" and the child's
   work is silently lost. Baldric reports the failure explicitly through the
   resource-diagnostics path added by the #477 port.

## Path roots

Upstream uses eight `.tau` roots (user and project scopes of `agents/`,
`subagents.json`, `subagents/` transcripts, `agent-memory/`, plus
`agent-memory-local/`) and one install-doc string. These map onto new
`BaldricPaths` properties rather than being hand-assembled inside the extension,
so that `BALDRIC_HOME` overrides keep working and the naming matches the existing
`extension_state_dir` convention used by the llama.cpp built-in.

## Cost measured, not guessed

`baldric_coding` is covered by `[tool.mypy] strict = true`. `tau-subagents` declares
no mypy configuration at all. Running Baldric's mypy 2.1.0 with `--strict
--ignore-missing-imports` over the upstream source reports **44 errors across 8
files**: `schedule_store.py` 16, `extension.py` 16, `prompts.py` 3,
`notification_render.py` 3, `ui/viewer.py` 2, `agents_menu.py` 2, `fork.py` 1,
`ui/controller.py` 1 — by code: `no-untyped-def` 14, `arg-type` 11,
`no-untyped-call` 6, `type-arg` 5, `no-any-return` 3, `union-attr` 2,
`assignment`/`unused-ignore`/`attr-defined` 1 each.

All 44 are fixed as part of this port. No per-module `strict = false` override is
added, so the port does not leave a new exemption behind.
