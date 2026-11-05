# Layout migration ledger — phase 1

Branch: `refactor/layout-phase-1`
Phase-1 starting commit: `80a1417e3c29832d2b3cd3cc1ef2c3f8a33d6bdd` (`main`, clean working tree)
Plan: `plans/layout-phase-1-moves.md`
Blueprint: `dev-notes/architecture/target-project-layout.md`
Authoritative mapping: `dev-notes/architecture/layout-mapping.md`

This ledger records, per cluster: starting commit, closure size, which recipe-M
steps ran, the three zero-behaviour-change checks, and the resulting commit hash.
It is the only process artifact of this phase; phase 2's entry conditions are
derived from it.

## Baseline (M-1 / Task 1 Step 1)

Recorded on `main` @ `80a1417e3c29832d2b3cd3cc1ef2c3f8a33d6bdd`, clean working tree
(`git status --porcelain` empty), after `uv sync --dev`.

| Check | Command | Result |
|---|---|---|
| pytest | `uv run pytest -q` | `2352 passed, 122 skipped in 225.91s` — 0 failed |
| mypy | `uv run mypy` | 14 errors in 2 files — all pre-existing Windows `fcntl` family errors (list below) |
| ruff check | `uv run ruff check .` | `All checks passed!` |
| ruff format | `uv run ruff format --check .` | `239 files already formatted` |

### Baseline mypy output (verbatim)

```text
src\baldric_agent\session\storage.py:266: error: Unused "type: ignore" comment  [unused-ignore]
src\baldric_agent\session\storage.py:270: error: Module has no attribute "LOCK_EX"  [attr-defined]
src\baldric_agent\session\storage.py:270: error: Module has no attribute "LOCK_SH"  [attr-defined]
src\baldric_agent\session\storage.py:271: error: Module has no attribute "flock"  [attr-defined]
src\baldric_agent\session\storage.py:279: error: Unused "type: ignore" comment  [unused-ignore]
src\baldric_agent\session\storage.py:283: error: Module has no attribute "flock"  [attr-defined]
src\baldric_agent\session\storage.py:283: error: Module has no attribute "LOCK_UN"  [attr-defined]
src\baldric_coding\project_trust.py:134: error: Module has no attribute "fcntl"  [attr-defined]
src\baldric_coding\project_trust.py:655: error: Unused "type: ignore" comment  [unused-ignore]
src\baldric_coding\project_trust.py:659: error: Module has no attribute "flock"  [attr-defined]
src\baldric_coding\project_trust.py:659: error: Module has no attribute "LOCK_EX"  [attr-defined]
src\baldric_coding\project_trust.py:670: error: Unused "type: ignore" comment  [unused-ignore]
src\baldric_coding\project_trust.py:674: error: Module has no attribute "flock"  [attr-defined]
src\baldric_coding\project_trust.py:674: error: Module has no attribute "LOCK_UN"  [attr-defined]
Found 14 errors in 2 files (checked 144 source files)
```

Baseline facade `__all__`: see `facade_before.txt` snapshot procedure in plan §4.4.
Baseline `__all__` length recorded in Task 11 Step 2.

## Task 1 — safety net and baseline

- Step 2: blueprint + `index.md` were already committed in `7b2d30c`, the plan in
  `c94c7c1`, `AGENTS.md` in `749611a`, release in `444befe` — **already pre-committed,
  skipped**.
- `scripts/check_move_only.py`: created (stdlib only; parses
  `git diff --find-renames -U0 <commit>^ <commit>`; scoped to `src/` + `tests/*.py`).
- `.gitignore`: `.venv` → `.venv*/` (the only infrastructure change authorised).
- `dev-notes/architecture/layout-mapping.md`: table header created (filled in Task 2).
- Self-check on pre-existing docs commit `80a1417`: `check_move_only: OK`.

### Task 1 Step 4 — guard self-check (rejection)

A throwaway commit `0e7f377` inserted one statement into the body of
`current_version()` in `src/baldric_coding/version.py`, then the guard was run:

```text
PS> uv run python scripts/check_move_only.py HEAD
check_move_only: 1 violation(s) in HEAD
  src/baldric_coding/version.py:13 +     _self_test_marker = 1
GUARD_EXIT:1
```

The commit was removed with `git reset --hard HEAD~1`; working tree clean again.
This proves the guard distinguishes an import-block rewrite from a function-body
change rather than merely accepting any Python diff.

Task 1 commit: `e0f02ee` (`chore(layout): add move-only guard script and migration ledger`).

## Task 2 — authoritative scan and differences vs the plan

Scan basis: branch `refactor/layout-phase-1` @ `80a1417` + Task 1 commit `e0f02ee`.
98 `.py` files under `src/baldric_coding/` (excluding `data/`), 49 at package root;
93 `.py` files under `tests/` (the plan said 91 — snapshot drift).

Full table: `dev-notes/architecture/layout-mapping.md`.

### Differences between the scan and the plan's Task 3–11 file lists

1. **`tui/config.py` is unassigned.** It exists (211 lines, `TuiSettings`/`TuiKeybindings`)
   but appears in neither the blueprint's `tui/` tree nor any task list. Phase-1 decision:
   leave in place (O) and flag for owner confirmation; Task 12 should add it to the
   blueprint tree.
2. **`tests/test_diagnostics.py` (Task 5) does not exist.** `diagnostics.py` has exactly
   one source reference (`session.py`) and one test reference; it is covered indirectly.
3. **`tests/test_catalog_loader.py` (Task 7) does not exist.** `catalog_loader` is covered
   indirectly by `test_provider_catalog.py` / `test_provider_config.py` / `test_cli.py`.
4. **Reference-count differences (plan → scan, distinct files; closure scope
   `src/` ∪ `tests/` ∪ `scripts/`, excluding the defining module file itself):**
   `paths.py` 30 → 53; `credentials.py` 13 → 21; `resources.py` 13 → 25;
   `commands.py` 8 → 13; `session.py` 7 → 13. The plan's numbers were a src-only
   snapshot; the full closure is larger because tests/ and scripts/ participate.
   Docs-only references (`website/`, `dev-notes/`) are counted separately:
   `resources` has 1 such dev-note reference (26 total across all areas),
   `commands` 1 (14), `session` 4 (17 across website+dev-notes), etc.
5. **Task 3 reference surface:** the 7 src-side `tui.themes` importers match the plan
   exactly (3 non-UI: `commands.py:766`, `session_export.py:51`, `session_usage.py:22`;
   4 UI: `tui/app.py:186`, `tui/config.py:11`, `tui/project_trust.py:15`, `tui/state.py:28`).
   Tests are **8 references across 6 files** (`test_tui_themes.py`, `test_commands.py`,
   `test_project_trust.py`, `test_session_export.py`, `test_tui_app.py` ×2,
   `test_tui_components.py`) — not 8 files. The earlier "8 files" was a hits-vs-files
   counting error, corrected here.
6. **Task 9 reference surface is understated in the plan.** Actual root-contract
   importers: `local_backends` 7 hits / 7 files (adds
   `extensions/builtins/llama_cpp/service.py:41`, `extensions/__init__.py:90`,
   `tui/local_backends.py:26`); `project_trust` 11 hits / 11 files (adds three test
   files and `tui/project_trust.py:14`). TUI-side modules are referenced by
   `tui/app.py` plus 2 test files each. Plan's "9处/7文件 + 2处" is a stale snapshot;
   M-2 must rescan.
7. **Blueprint gaps recorded for Task 12:** (a) no top-level `config/` subtree, although
   Task 5 targets `config/paths.py` and `config/shell_config.py`; (b) `auth/oauth.py`
   is not listed in the blueprint's `auth/` subtree, although Task 4 targets it;
   (c) `tui/config.py` missing; (d) the known `extensions/builtins.py` conflict →
   `extensions/builtin_registry.py`.
8. **`data/` does not move.** `catalog_loader.py:124` and `models_dev.py:158` use the
   absolute anchor `files("baldric_coding")`, so `data/` stays at
   `src/baldric_coding/data/`. Only the modules move (Tasks 7). Task 7 must still run a
   real read (plan hard requirement).
9. **Task 3 theme loader:** `tui/themes/__init__.py:374` uses `files(__package__)`,
   which follows the package to `rendering/themes/`; no path-expression edit is
   expected. Real-load verification still mandatory.

### String-reference findings (must be handled in the owning task)

- Functional string paths: `tests/test_extension_providers.py:1416-1417`
  (`monkeypatch.setattr("baldric_coding.provider_config...")`) → rewrite in Task 7.
- Display-only strings: `src/baldric_coding/system_prompt.py:96`
  (`source="baldric_coding.system_prompt"`) and the matching assertions in
  `tests/test_tui_app.py:9366,9391` → **left unchanged (D2)**. `source` is a
  human-readable provenance label (`str`, rendered only at `system_prompt.py:170`);
  its sibling values are natural language or a filesystem path, and no import or
  resource lookup uses it. Classification: **"stale but non-fatal display string"**,
  phase-2 documentation debt.
- Non-functional comment: `src/baldric_coding/prompt_templates.py:37` mentions
  `baldric_coding.commands`; left untouched per "do not edit comments".

### Task 2 Step 5 — three "待决" mappings (cross-validated)

- `context_window.py`: phase 1 treats as 1:1 `session/compaction/context_window.py`;
  compaction split registered as phase-2 candidate.
- `skills.py`: phase 1 keeps package depth `context/skills/skills.py`.
- `cli.py`: phase 1 O; argv/mode split registered as phase-2 candidate.

Task 2 commit: `2d28e27` (`docs(layout): add authoritative module-to-target mapping for phase 1`)

## Owner rulings and plan corrections (2026-11-05)

The owner independently re-verified four claims and issued two binding decisions.

| ID | Decision | Evidence / consequence |
|---|---|---|
| **D1** | `tui/config.py` stays **O** (no move). Task 12 adds `config.py` to the blueprint's `tui/` tree. | Blueprint omission = blueprint gap → fix document (blueprint rule 4). Moving it needs "its own reason" (rule 3); phase 1 has none. |
| **D2** | `system_prompt.py:96` `source="baldric_coding.system_prompt"` stays unchanged. Classified as **"stale but non-fatal display string"**. | `source` is `str` human-readable provenance, rendered only at `system_prompt.py:170`; siblings are natural language or a filesystem path; no import/resource lookup. Changing it has zero functional benefit and would break the frozen-assertion rule (`test_tui_app.py:9391`). |

Plan corrections landed in `plans/layout-phase-1-moves.md` (commit
`docs(plans): correct data-anchor rule, closure scope, and stale test paths`):

1. **`data/` never moves.** `catalog_loader.py:124` and `models_dev.py:158` use the
   absolute anchor `files("baldric_coding")`, independent of the caller's location →
   `data/` stays at `src/baldric_coding/data/`. Task 7 real-read verification retained
   (packaging behaviour still must be measured).
2. **Task 3 path-expression warning removed.** `tui/themes/__init__.py:374` uses
   `files(__package__)`, which follows the package; real-load verification retained
   as confirmation.
3. **Closure scope written into the plan:** `src/` ∪ `tests/` ∪ `scripts/` `.py`
   files, distinct files, excluding the defining module file itself. Corrected
   numbers: `paths` 53, `credentials` 21, `resources` 25, `commands` 13, `session` 13.
4. **Stale test paths removed:** `tests/test_diagnostics.py` (Task 5) and
   `tests/test_catalog_loader.py` (Task 7) do not exist; their task lines now say
   "按 4.2 扫描".

Safety rule adopted from this point on: self-test commits are made on a throwaway
branch (`tmp-guard-selftest`), never on the feature branch, and `git reset --hard`
is not used.

## M-1 failure-set record (Task 3 baseline, 2026-11-05)

Three consecutive full-suite runs on the same tree (`src/` and `tests/` byte-identical
to `main`; `git diff --stat main..HEAD -- src tests` empty). Each run failed exactly
one different TUI test; every run: `1 failed, 2351 passed, 122 skipped`.

| Run | Failing test full ID | Assertion text | Isolated rerun |
|---|---|---|---|
| A (18:31–18:35) | `tests/test_tui_app.py::test_tui_app_skills_picker_filters_and_inserts_without_submitting[asyncio]` | `tests/test_tui_app.py:5841: AssertionError: assert not <DOMQuery query='ListItem'>` (after setting search to "missing") | 3/3 passed (3.66 / 3.45 / 3.41 s) |
| B (18:36–18:40) | `tests/test_tui_app.py::test_streaming_code_block_hides_horizontal_scrollbar_until_finalized[asyncio]` | `tests/test_tui_app.py:5099: AssertionError: assert 0 > 0` (`BaldricMarkdownFence.max_scroll_x`) | 3/3 passed (0.91 / 0.84 / 2.08 s) |
| C (18:41–18:45) | `tests/test_subagents_integration_tui.py::test_real_app_mounts_extension_strip_and_viewer` | `tests/test_subagents_integration_tui.py:228: AssertionError: assert not <DOMQuery query='#subagents-conversation-viewer'>` | 2/3 passed; **1/3 failed under normal load** |

`F_before` (initial allowlist, 3 entries) = the three full IDs above.

### Concurrency investigation

- No `python.exe` / `pytest.exe` / `uv.exe` test process running during inspection;
  `Get-CimInstance Win32_Process` showed only two autopep8 language-server Python
  processes (started 08:38, unrelated) and the harness's own PowerShell runner.
- No `.git/index.lock`; the only worktrees are this checkout
  (`D:/DEVELOP/Solis/baldric` @ `fbaca0f [refactor/layout-phase-1]`) and a dormant
  `C:/Users/7/AppData/Local/Temp/opencode/prtriage/base` (detached `3cc0bdc`), with
  no process tied to it.
- CPU load sampled at 2%.
- `.pytest_cache/v/cache/lastfailed` contains stale entries from unrelated tests,
  indicating prior partial runs in this checkout at some earlier point; no active
  runner now.
- Run C's third case **reproduced 1/3 in isolation under normal load** → record
  "load normal yet reproduces"; this raises the weight that it may be a real
  test-side defect. Per owner ruling it belongs to phase 2, not this phase, and is
  not fixed here.

### Adopted protocol

Failure-set diffing replaces "baseline must be completely green": every cluster
records `F_before`/`F_after`; `F_after ⊆ F_before` may continue; a new failure needs
the three-evidence single-exception path (isolated 3× pass + cluster tests green +
no reference relation via 4.2). Hard limits: allowlist ≤ 5 cases; same case failing
in 3 consecutive clusters is a real defect (C-class); exact full-ID matching only.
Written into `plans/layout-phase-1-moves.md` §「执行与评审形态」 and §5/§5.1.

## Cluster log

| Task | Cluster | Start commit | Closure files | M steps | Rename detection | check_move_only | Facade `__all__` | Commit | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 3 | `rendering/themes` | _pending_ | | | | | | | |
| 4 | `auth/` | _pending_ | | | | | | | |
| 5 | leaf (`config/`, `update/`, `observability/`, `utils/`) | _pending_ | | | | | | | |
| 6 | `context/` | _pending_ | | | | | | | |
| 7 | `providers/` | _pending_ | | | | | | | |
| 8 | `session/` | _pending_ | | | | | | | |
| 9 | `tools/` `backends/` `trust/` | _pending_ | | | | | | | |
| 10 | `extensions/` `commands/` | _pending_ | | | | | | | |
| 11 | facade / O-class review | _pending_ | | | | | | | |
