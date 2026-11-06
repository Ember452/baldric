# Large-file decomposition: what was split, and what was deliberately not

**Status:** TUI and session decompositions complete (2026-11-06).

This note records where the big modules' logic lives now, the constraints that
shaped the split, and the units left whole on purpose — so a future change starts
from a reasoned position instead of re-discovering the same edges.

## The pattern: typed facade over module functions

`CodingSession` and `BaldricTuiApp` are wide by design. The project's existing
convention (`session/runtime.py`, `session/tree_helpers.py`, …) is:

- **real logic lives in module-level functions**, fully typed;
- **the class keeps thin members** with the original signature and docstring, so
  call sites never change.

This matters for type safety. Typing `self` as the concrete class inside a mixin
is rejected by mypy:

```text
The erased type of self "…CodingSession" is not a supertype of its class "…Mixin"
```

The only mixin-compatible option is `self: Any`, which silently disables
`--strict` on exactly the code that needs it. So:

- **core logic → module functions** taking `session: CodingSession` (full checking);
- **presentation glue → mixins with `Any`** (TUI pickers/reconcile; the bodies are
  screen orchestration, not algorithms).

## What was extracted

| Area | Before | After | New home |
| --- | --- | --- | --- |
| `tui/app.py` | 5782 | **4472** | `tui/pickers.py` (model/theme), `tui/session_pickers.py` (session/tree/skill/login), `tui/extension_components.py` (slot/sidebar/main-view reconcile + its handle/bridge classes), plus neutral `tui/session_records.py`, `tui/text_utils.py`, `tui/login_providers.py` |
| `session/session.py` | 2232 | **1931** | `session/model_runtime.py` (HF route failover, header-driven routing, runtime provider build/activate/refresh, model limits, cost pricing), `session/branching.py` (branch/tree/labels + `TREE_RUNNING_MESSAGE` and the two tree dataclasses, re-exported) |

(Baseline line counts from `structure-baseline.json`.)

## Constraints discovered while splitting

1. **Textual registers `@on(...)` handlers from the concrete class `__dict__`
   only.** A decorated handler moved into a mixin never fires — the sidebar tests
   catch it. `on_sidebar_file_open_requested` therefore stays on `BaldricTuiApp`.
2. **`tui/screens/login.py` resolves OAuth through `_app_module().get_oauth_provider(name)`**
   (and `screens/sidebar.py` likewise for its write helpers). Those names must
   stay importable from `baldric_coding.tui.app`, or every OAuth login without an
   explicit login closure raises `AttributeError` **inside a worker** — invisible
   to the user, only the missing screen gives it away.
3. **`monkeypatch` targets move with the code.** Tests patching
   `tui_app.<name>` broke when the consumer moved; each patch now points at the
   module that actually calls the name.
4. **Name collisions.** `session/compaction/` is already a package; a new
   `session/compaction.py` would be shadowed by it. New session modules live
   beside it, not at the package's name.

## Left whole on purpose

Each item below was evaluated and kept as-is. Revisit only on the stated trigger.

| Unit | Size | Why not split |
| --- | --- | --- |
| `CodingSession.load()` | 297 lines, 47 top-level statements | One linear constructor flow whose stages share ~12 locals (`config`, `state`, `entries`, `pending_initial_entries`, `extension_runtime`, `resource_paths`, `resources`, `summary`, `trust_resolution`, …). Splitting means either 8 functions with 10+ parameters each or a new mutable context object — both add indirection around trust/persistence ordering, which is where a mistake is most expensive. **Trigger:** a change that needs one stage tested or reused in isolation. |
| `CodingSession.__init__()` | 80 lines, 51 statements | Pure field assignment (60+ state fields). There is no logic to extract; moving the assignments only relocates them and risks dropping one silently. **Trigger:** fields become grouped enough to justify a second state object. |
| `session/lifecycle.reload()` | 216 lines | Already a module function; the same shared-locals argument as `load()`. **Trigger:** the reload steps diverge enough to be independently tested. |
| rest of `tui/app.py` | 4472 lines, 61-stmt hot spot | Remaining members are the app lifecycle, prompt/run path, event handlers and rendering glue — the part that *is* the app. The extracted families were the ones with a clean seam. **Trigger:** a new cohesive family appears, or the Textual adapter boundary moves. |
| `session/export/html.render_session_html()` | 1005 lines, but 24 statements | Measured rather than assumed: 59% of the file is string literals and this function is one 11,316-character HTML/CSS/JS template with interpolations. It is a template artifact, not logic; the structure ratchet already scores it low. **Trigger:** the template grows sections that belong in separate documents. |

`compaction` was prototyped and **reverted**: those methods are already pure
delegations into `session/runtime.py`, so extracting them added a module and a
layer without removing any logic.

## Guards

- `scripts/check_structure.py` — file size, function statements, fan-out; records
  reviewed growth with `--init`.
- `scripts/check_suppressions.py` — `# type: ignore` / `# noqa` may only shrink.
- `scripts/check_agent_guidance.py` — instruction files (`AGENTS.md`/`CLAUDE.md`)
  may only shrink; **architecture notes belong in `dev-notes/`, not there.**
- `tests/coding/tui/test_picker_extraction.py` — picker/reconcile methods come
  from the mixins and are never redefined on the app.
- `tests/coding/session/test_session_module_layout.py` — the session class stays a
  plain facade (no mixin bases), the tree types are single-sourced and
  re-exported, and the module functions back the class members.

## Verifying a future change here

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run python scripts/check_structure.py
uv run python scripts/check_suppressions.py
uv run python scripts/check_agent_guidance.py
uv run python scripts/check_import_graph.py
uv run pytest -q tests/coding/tui/test_picker_extraction.py tests/coding/session/test_session_module_layout.py
```

Full TUI suite is flaky on Windows (asyncio backend); run it on Linux CI, and on
Windows run `tests/coding/tui/test_tui_app.py` plus the other modules
individually.
