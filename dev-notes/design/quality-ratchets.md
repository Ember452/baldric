# Quality ratchets

Baldric keeps its quality bar with a mix of CI gates and committed baselines
that can only move in one direction. This note records what each ratchet
guards, where it runs, and how to tighten it.

These mechanisms were assembled from what mature agent projects do in practice:
Codex compiles constraints into the toolchain (clippy `deny`, one required
check, clean-worktree), DeepSeek Harness keeps 341 narrow guards plus counted
baselines, Kimi CLI injects a repo map and audits invariants, and DeerFlow
enforces architecture boundaries as ordinary pytest tests and makes instruction
files subject to a byte budget.

## Already gating in CI

| Gate | What it locks |
| --- | --- |
| `pytest` matrix (3.12/3.13/3.14) | Behavior must pass on every supported interpreter |
| `ruff check .` | Zero lint findings; any new violation fails (fail-on-error is itself a ratchet) |
| `ruff format --check .` | Formatting cannot drift |
| `mypy` | No type errors on Linux (the platform the CI runs on) |
| docs build + website tests | Published docs cannot break |
| `collection-gate` | Every test can be collected in a clean install |
| `all-checks-passed` | One required check; `always()` so a failed dependency cannot look green |
| `Assert a clean worktree` | CI must not leave uncommitted changes behind |


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

### Suppression ratchet

`scripts/check_suppressions.py` counts `# type: ignore` / `# noqa` comments per
file and per kind (`suppressions-baseline.json`). This closes the biggest hole
in a `mypy --strict` setup: a green mypy run says nothing about how many
suppression comments are holding it up. Current baseline: 141 comments across 41
files, dominated by 94 `noqa: BLE001` (broad exception handling) and 17
`noqa: F401` (re-exports).

Comment scanning uses `tokenize`, not a regexp, so the word `noqa` inside a
string or docstring is never counted as a suppression. Every ratchet script also
asserts a minimum corpus size so a wrong path cannot make the gate vacuously
green.

### Agent-guidance ratchet

`scripts/check_agent_guidance.py` records the byte size of every `AGENTS.md`
and `CLAUDE.md` (root and per package) plus the deepest root-to-package chain
(`agent-guidance-baseline.json`). Instruction files may only shrink; growing one
requires rerunning `--init`, which is the "explain why" moment. `CLAUDE.md` must
stay a thin `@AGENTS.md` shim so the rules have one home.

### Lint-configuration fingerprint

`tests/guards/test_lint_config_fingerprint.py` hashes the normalized ruff and
mypy configuration. Removing a ruff rule or turning off `mypy.strict` changes the
hash, so it requires editing the test - a disclosure step rather than a silent
relaxation.

### Golden files

`tests/helpers/golden.py` compares observable output against committed files in
`tests/expected/` (currently CLI `--help`, assistant-message JSON, and
tool-result JSON). Tests only read those files; updating them requires
`UPDATE_EXPECTED=1`, which prints the diff it accepts.

### Code invariants

`tests/invariants/test_code_invariants.py` walks `src/` with `ast` and enforces:
`subprocess` calls always pass a timeout, no bare `except:`, and file IO without
an explicit encoding stays at or below 18 call sites (a ratchet, since those
predate the rule).

### Gate self-tests

`tests/guards/` proves each gate still fires: a planted layer violation, a grown
file, a new suppression, and a grown instruction file must each be rejected. A
green gate that no longer catches anything is worse than no gate at all, so the
gates themselves are tested.

## Local workflow hooks

`.pre-commit-config.yaml` runs only the fast checks (ruff fix/format, the three
ratchets, version consistency) and deliberately does not run tests; CI owns the
full matrix. `.github/pull_request_template.md` asks for the commands actually
run, a behavior-proof checklist, and an AI-assistance disclosure.

`scripts/verify_versions.py` keeps `pyproject.toml`, `uv.lock`, and (during
releases) the git tag in agreement.

## Deliberately absent

Performance baselines (no hot-path benchmarks exist to guard), API-surface
snapshots (no external consumers yet), skip-count gates (Linux CI skips few
tests by design), PR-size limits (single-developer noise), pytest markers and
sharded test runs (the suite is ~3 minutes on Linux; sharding would add CI
machinery for little gain), and a Blockbuster-style blocking-IO gate (the code
currently has one `time.sleep` and no blocking calls on event-loop paths, so it
would guard a risk that does not exist yet).

