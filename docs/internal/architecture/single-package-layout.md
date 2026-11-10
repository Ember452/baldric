# Single-package `src/baldric/` layout

Status: done (2026-11-10, branch `refactor/single-package-src-layout`).

## What changed

The five top-level import packages were consolidated under one package root so
the import path matches the distribution name (`pip install baldric` →
`import baldric`):

| Before | After |
| --- | --- |
| `src/baldric_protocol` | `src/baldric/protocol` |
| `src/baldric_ai` | `src/baldric/ai` |
| `src/baldric_agent` | `src/baldric/agent` |
| `src/baldric_coding` | `src/baldric/coding` |
| `src/baldric_mcp` | `src/baldric/mcp` |

A new `src/baldric/__init__.py` (docstring only, no re-exports) is the package
root. The five per-package `py.typed` markers collapsed into one at
`src/baldric/py.typed` (PEP 561 package root).

This is a **pure mechanical rename**: no behavior change, no renames beyond the
map above, no reformatting of untouched code.

## Why

For a single distribution, one import root (`baldric.*`) is the more
conventional layout than five sibling top-level packages. Pre-1.0 is the cheap
moment to make the move. The layer boundaries that the multi-package layout
expressed physically are still enforced by `scripts/check_import_graph.py`
(now with translated prefixes) and `tests/guards/`.

## How (bulk-rewrite discipline)

Per `AGENTS.md` the bulk rewrite was done with a reviewed, token-level script:

1. `git mv` each package directory under `src/baldric/` (history preserved).
2. Token-level rewrite of `src/`, `tests/`, `scripts/`, `examples/`, and the
   tracked project extension `.baldric/extensions/`: `NAME` tokens and
   `STRING`/`COMMENT`/`FSTRING` token text renamed; byte content outside edited
   spans preserved; every rewritten `.py` re-parsed with `ast` and line-count
   checked before writing.
3. Text rewrite of live docs (root `AGENTS.md`/`README.md`/`CONTRIBUTING.md`,
   scoped `AGENTS.md`, bundled `data/docs`, `website/content`, `landing.html`,
   `website/src/data.ts`, `Home.astro`, `roadmap.yaml`).
4. Dry-run report reviewed line by line before `--apply`; a second dry-run
   produced zero changes (idempotent).
5. Manual fixes for the file-path segments the script could not split
   (`"src" / "baldric.coding"` → `"src" / "baldric" / "coding"`) and for the
   gate scripts' path logic.

Directories that are historical records were deliberately **not** rewritten and
still use the old names by design: `dev-notes/**`, `plans/**`,
`docs/superpowers/**`, `src/baldric/coding/data/release-notes/**`.

## Gate-script changes

- `check_import_graph.py`: RULES / surface prefixes translated; `_module_name`
  is path-generic and needed no change.
- `check_structure.py`: module fan-out project-root set is now
  `{baldric.agent, baldric.ai, baldric.coding}`; the membership test switched
  from first-segment match to prefix match so nested dotted names still count
  (protocol/mcp stay excluded, identical metric semantics).
- `check_agent_guidance.py`: scoped-file discovery now globs `src/baldric/*`
  (one level deeper than before).
- `check_suppressions.py`, `check_move_only.py`, `verify_versions.py`: no change
  (path-generic / distribution-name based).

## Baselines

- `structure-baseline.json`, `suppressions-baseline.json`,
  `agent-guidance-baseline.json`: regenerated with `--init`. Diff reviewed and
  proven to be pure key renames — structure/suppressions values identical;
  guidance values equal-or-tighter (`src/baldric_x/AGENTS.md` → `src/baldric/x/`
  is one byte shorter, so the ratchet tightened, which is allowed).
- `tests/guards/session_state_write_baseline.json`: keys remapped
  `src/baldric_coding/...` → `src/baldric/coding/...` with values preserved.
- `tests/guards/test_lint_config_fingerprint.py`: `EXPECTED_FINGERPRINT`
  updated because the mypy `packages` list intentionally changed from five
  entries to `["baldric"]`.

## Breaking change for third parties

This is a public import break at 0.3.0. Update imports:

```python
# before
from baldric_coding.extensions import ExtensionAPI
from baldric_protocol.tools import AgentTool, AgentToolResult
# after
from baldric.coding.extensions import ExtensionAPI
from baldric.protocol.tools import AgentTool, AgentToolResult
```

The bundled examples (`src/baldric/coding/data/examples`, `examples/`, and the
tracked `.baldric/extensions/ask_user_question.py`) were updated in the same
change.

## Verification

- `ruff check .` / `ruff format --check .`: green.
- `mypy`: exactly the 14 known Windows-only errors in `trust/policy.py` +
  `session/storage.py` (new paths), matching the baseline; CI runs green on
  Linux.
- `check_import_graph.py`, `check_structure.py`, `check_suppressions.py`,
  `check_agent_guidance.py`, `verify_versions.py`: OK.
- Resource smoke: `files("baldric.coding").joinpath("data/catalog.toml")`
  reads; `import baldric.{protocol,ai,agent,coding,mcp}` all succeed.
- `uv build`: wheel ships `baldric/...` paths only (no `baldric_*`),
  includes `baldric/py.typed` and the `data/` resources.
- `baldric --version` → `baldric 0.3.0`; console entry point resolves to
  `baldric.coding.cli:app`.
- `uv.lock` unchanged (`baldric==0.3.0`, same source).
- Full `pytest`: behavior-equivalent to baseline; the only failures were known
  Windows TUI asyncio flakes in `test_tui_app.py`, which pass on re-run.
