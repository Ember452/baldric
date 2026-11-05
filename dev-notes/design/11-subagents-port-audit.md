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
   The gate needs no new plumbing: `extensions/api.py` already exposes
   `ExtensionContext.project_trust_resolution` (:977) and
   `ExtensionContext.project_trusted` (:991), whose docstring already instructs a
   host that builds child sessions to forward `CodingSessionConfig(trust_override=...)`
   so children inherit the decision instead of re-resolving headlessly. The port
   consumes that; it does not re-derive trust inside the extension.
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

## Open item found while porting `prompts.py`

`(Skill "x" not found)` is an upstream placeholder that becomes untrue in one
case: when the project is not trusted, `BaldricResourcePaths.skills_dirs`
(`resources.py:86-104`) simply omits the project directories, so a skill that
does exist in the repository is reported to the model as missing, and the model
tends to relay that as "you have no such skill".

The fix belongs at the call site in `extension.py`, which holds both
`project_trusted` and `definition.skills`: emit one note saying the preload was
skipped for lack of trust. It does **not** belong inside `resolve_skill_blocks`.
**Deferred, not done:** the landed `extension.py` keeps that call site as written,
so an untrusted project still produces no message about its skipped preloads.
An earlier draft of this port added a `diagnostics` + `missing` split there on
the theory that it would separate "repository not authorized" from "typo". That
theory is wrong on the facts: the untrusted case produces no diagnostic at all,
and `_load_skills_from_dir_with_diagnostics` (`skills.py:176-177`) returns
`([], [])` for a missing or non-directory path, so its diagnostics report bare
`.md` files and precedence overrides - not unreadable directories. The caller
already knows the trust decision, so a channel for it here would be redundant at
best and misleading at worst.

## Second open item, from `schedule.py`

`_execute_job` records only `last_status="error"`: the `except Exception` around
`manager.spawn` and the one around awaiting the run's task both discard the
exception, so a job that has been failing every night for a week shows a status
and nothing else. Retaining the message would need a `last_error` field on the
stored job, which is a schema change rather than an adaptation, so it is left
out of this port and recorded here. Deciding it also means deciding whether the
store file should keep history or only the last failure.

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

## Landed state, after the full copy

Thirteen modules are in `extensions/builtins/subagents/` plus `ui/`: `cron`,
`settings`, `schedule_store`, `schedule`, `worktree`, `group_join`, `memory`,
`agents`, `prompts`, `fork`, `output_file`, `notification_render`, `agents_menu`,
`extension`, `ui/{__init__,controller,strip,viewer}`. The last five arrived as a
straight copy with mechanical name rewrites only (module paths, `BaldricPaths`,
`BALDRIC_DARK_THEME`, `BaldricTuiApp`, `baldric-agent-`, `.baldric/`), then the
conflicts below were resolved one at a time, each against a declared type rather
than a judgement: `BaldricPaths` and `project_trusted` at the loader call sites,
`resolve_store_path` needing paths, `CodingSessionEvent` for observed events
(`session.py:3227`), the storage protocol's `append_batch` (`storage.py:36`),
block-list message and tool content, the host's `ThinkingLevel` parameter, the
renderer's must-return-text contract, `isinstance` in place of a `getattr` role
check so the union narrows, the menu protocol's `Literal` notify level, and the
host's tool/command handler signatures.

Reversals recorded because they were wrong the first time. Claims of an
original defect in the settings merge order, the memory prompt path, the
silent frontmatter fallbacks, the best-effort worktree cleanup, the swallowed
transcript write errors and the lock-file deletion were all mistaken: the
corresponding tests assert those behaviours as intended, or the code says so in
a comment. Each was reverted to the original form, and the local protocol in
`group_join.py` and `schedule.py` went away once `extension.py` existed to name
the real run record.

Checks at the copy commit: mypy at its 14-error `fcntl` baseline with zero errors
in `subagents`, `ruff check` and `ruff format --check` clean, and the suite at
2238 passed / 119 skipped - the same numbers as before the copy, because none of
this code was under test yet.

What remains: adding the extension to `BUILT_IN_EXTENSIONS` so it actually
loads. The original suites for the manager, menu, fleet UI and scheduler are in,
so the capability now has 236 cases exercising it rather than only its parts.

One environment note: a full-suite run blocked once with zero CPU in an existing
TUI test and had to be killed. Re-runs of that group standalone (672 passed) and
of the whole suite (2238 passed, 134s) do not reproduce it. Nothing in these
modules is imported by any test, so this port is not the cause; it is left
alone rather than chased.

## Full re-comparison, once the suites were in place

Method repeated on the finished tree: every file was normalised back to the
source naming and diffed against it hunk by hunk - 1867 diff lines, 207 hunks
across 17 files (`ui/__init__.py` came back identical). Each hunk then got one
of three verdicts, and the verdict had to be traceable to a declared type, a
test assertion, or the base tree.

Kept because the host forces it: `BaldricPaths` and the trust flag at every
loader, the home-based schedule location, `validate_session_id` on the session
component, `CodingSessionEvent` for observed events, the storage protocol's
`append_batch`, block-list content for messages and tool results,
`_int_field` (a `JSONValue` union cannot be handed to `int()`), the typed
renderer and handler signatures, the must-return-text adapter around
`render_notification`, `isinstance` in place of a role string test, and the
thinking level taken from the provider-selection branches.

Reverted after re-checking, in four separate changes: the fork's thinking level
is optional again (nothing forced it and its absence has a meaning), an unknown
schedule patch key raises again instead of being filtered,
the settings read catches a decode error rather than every `ValueError`, and the
notification card reads text fields with the original conversions instead of a
helper that blanked non-text values. The suppression comment on the record
loader is gone too, so this port still adds no exemption.

Kept as a deliberate simplification: `load_available_skills` was dropped because
it had exactly one caller here and no external consumer, and the many
line-joining differences are what this project's formatter produces at 110
columns - no statement changed.

Not a defect but worth recording: comments inherited from the source still name
the protocol family it follows ("matching pi", "pi parity", "ADR 0003"-style
references were removed where they pointed at documents that do not exist here).
Those notes explain why a behaviour looks the way it does, so they stay as they
are rather than being scrubbed for tidiness.

Two test-side flakiness observations in this environment, neither reproducible:
one full-suite run blocked in an existing TUI test with zero CPU, and one run of
the ported suites failed `assert False is True` on a viewer-mount check that
passes standalone, in every pairwise combination, and on two further full runs
(236 passed twice). Both are recorded rather than chased.

