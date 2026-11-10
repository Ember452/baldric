# Rename `baldric.coding` → `baldric.runtime`

Status: done (2026-11-10, branch `refactor/coding-to-runtime`).

## What changed

The application/host package was renamed to drop the "coding" narrowness while
keeping the distribution name (`baldric`) intact:

| Before | After |
| --- | --- |
| `src/baldric/coding/` | `src/baldric/runtime/` |
| `import baldric.coding` | `import baldric.runtime` |
| `files("baldric.coding")` | `files("baldric.runtime")` |
| console entry `baldric.coding.cli:app` | `baldric.runtime.cli:app` |
| `tests/coding/` | `tests/runtime/` |

`baldric` remains the package root; the layers are now
`baldric.{protocol, ai, agent, runtime, mcp}`.

## What deliberately did NOT change

- **Identifiers**: `CodingSession`, `CodingSessionEvent`, `CodingSessionRecord`,
  `CodingSessionConfig`, `create_coding_tools`, `CodingReloadSummary`,
  `FakeCodingSession` and friends keep their names. They name a *coding session*
  — a legitimate concept — and sit in the frozen public API (139 exports). The
  package is a host for such sessions; renaming the host package does not make
  the session type less a coding session. pi/tau likewise keep a `coding`-flavored
  class inside a differently-named package.
- **Unrelated strings** that merely contain the word "coding":
  `"https://api.kimi.com/coding/v1"` (a real provider URL) and the test module
  filename `test_coding_session.py` / `test_coding_tools.py`.
- **Historical records**: `dev-notes/**`, `plans/**`, `docs/superpowers/**`,
  `data/release-notes/**` still use the old paths by design.

## How (boundary-safe bulk rewrite)

- Directories moved with `git mv` (src and tests).
- A one-shot script replaced only bounded package paths:
  `baldric.coding` → `baldric.runtime`, `baldric/coding` → `baldric/runtime`,
  `tests/coding` → `tests/runtime`. Its 16-case self-test proves the regexes
  never touch `CodingSession`, `create_coding_tools`, `api.kimi.com/coding`, or
  `baldric_coding`. 273 files rewritten; a second run produced zero changes.
- Note: an earlier token-level variant failed to rewrite real `from baldric.coding
  import` statements (those are three tokens — `baldric . coding` — not a single
  STRING token), which the whole-text, boundary-safe regexes fixed. Caught by the
  dry-run + leftover scan before committing.
- Path-segment literals the regexes correctly left alone
  (`Path / "baldric" / "coding"` in a handful of tests) were fixed by hand.
- Gate scripts: `check_import_graph.py` RULES and `check_structure.py` fan-out
  root set translated by the script; `check_agent_guidance.py` globs
  `src/baldric/*` and needed no change.

## Config / baselines

- `pyproject.toml`: entry point and coverage `omit` → `runtime`.
- `structure-baseline.json`, `suppressions-baseline.json`,
  `agent-guidance-baseline.json`: regenerated with `--init` (pure key renames).
- `tests/guards/session_state_write_baseline.json`: keys remapped
  `src/baldric/coding/...` → `src/baldric/runtime/...`, values preserved (61
  (field, count) pairs unchanged).
- `.github/workflows/ci.yml`: a path list updated to `tests/runtime/...`.

## Verification

- `ruff check .` / `ruff format --check .`: green (the `coding`→`runtime` rename
  needed import re-sort (I001) and two long-line wraps; nothing behavioral).
- `mypy`: exactly the 14 known Windows-only errors (`trust/policy.py`,
  `session/storage.py`, now under `src/baldric/runtime/`).
- `check_import_graph.py`, `check_structure.py`, `check_suppressions.py`,
  `check_agent_guidance.py`, `verify_versions.py`: OK.
- Imports: `import baldric.{runtime,ai,agent,protocol,mcp}` all succeed;
  `files("baldric.runtime").joinpath("data/catalog.toml")` reads.
- `uv build`: wheel ships `baldric/runtime/...` only (no `coding` paths),
  includes `baldric/py.typed` and `data/` resources.
- `baldric --version` → `0.3.0`; entry point `baldric.runtime.cli:app`.
- `uv.lock` unchanged.

## Breaking change for third parties

Update the import path (identifiers are unchanged):

```python
# before
from baldric.coding.extensions import ExtensionAPI
from baldric.coding.session.session import CodingSession
# after
from baldric.runtime.extensions import ExtensionAPI
from baldric.runtime.session.session import CodingSession
```
