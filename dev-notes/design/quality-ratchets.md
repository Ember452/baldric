# Quality ratchets

Baldric keeps its quality bar with a mix of CI gates and committed baselines
that can only move in one direction. This note records what each ratchet
guards, where it runs, and how to tighten it.

## Already gating in CI

| Gate | What it locks |
| --- | --- |
| `pytest` matrix (3.12/3.13/3.14) | Behavior must pass on every supported interpreter |
| `ruff check .` | Zero lint findings; any new violation fails (fail-on-error is itself a ratchet) |
| `ruff format --check .` | Formatting cannot drift |
| `mypy` | No type errors on Linux (the platform the CI runs on) |
| docs build + website tests | Published docs cannot break |

## Ratchets added with this note

### Coverage floor

`pyproject.toml` sets `[tool.coverage.report] fail_under = 80` and CI runs
`uv run pytest --cov`. The floor is deliberately conservative: the Windows
development suite measures ~85.7% while skipping the POSIX-only tests, and the
Linux CI suite exercises those too, so real CI coverage is higher. Tighten
`fail_under` whenever coverage grows; it never loosens.

### Architecture layer direction

`scripts/check_import_graph.py` enforces the AGENTS.md layering rules
(`baldric_agent` stays free of `baldric_coding`/`textual`/`rich`,
`baldric_ai` stays free of `baldric_coding`, frontend modules stay out of
session/tools/trust/providers/context). The script existed but was manual;
CI now runs it on every push and PR.

Note: `scripts/check_move_only.py` intentionally stays out of CI. It is a
narrow audit for the phase-1 move-only refactor and rejects ordinary code
changes by design.

### Structure ratchet

`scripts/check_structure.py` measures, over `src/`:

- per-file line count and longest function body (direct statements);
- global deepest project-defined inheritance chain;
- global widest module fan-out (distinct in-project modules imported).

The committed `structure-baseline.json` records the current values. A check
fails when any metric regresses past its baseline or when a file with no
baseline entry exceeds the hard limits (1200 lines / 150 statements). Metrics
that improved are reported as a prompt to run
`uv run python scripts/check_structure.py --init`, which rewrites the baseline
tighter. The baseline is committed; the ratchet only ever tightens.

Current baseline highlights (as of this note): `tui/app.py` 5781 lines,
`session/session.py` 2220 lines, max fan-out 51 modules, inheritance depth 1.
These are the numbers future work has to beat, not reach.

## Deliberately absent

Performance baselines (no hot-path benchmarks exist to guard), API-surface
snapshots (no external consumers yet), skip-count gates (Linux CI skips few
tests by design), and PR-size limits (single-developer noise).
