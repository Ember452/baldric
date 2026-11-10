# Baldric Agent Instructions

Baldric is a Python implementation of Pi's minimalist coding-agent harness architecture. The goal is to develop it incrementally, with each phase clearly documented and tested.

## Behavioral Guidelines

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

Tradeoff: These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

Touch only what you must. Clean up only your own mess.

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

Define success criteria. Loop until verified.

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

These guidelines are working if: fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## Hard Rules

These are not style preferences; each one comes from a real incident in this
repository's history.

- **Never edit files with scripts, `sed`, or batch replacements.** Use the editor
  tools one change at a time. A PowerShell rewrite with a wrong escape level once
  replaced a 3,519-line test file with 45 lines, and another one silently dropped
  `async def` from a function. If a bulk rewrite is genuinely required, do it in
  a separate commit and review `--dry-run`-style output first.
- **Assert whole objects; never weaken an assertion to make it pass.** If a test
  fails, the implementation or the behavior contract is wrong until proven
  otherwise. Change an existing assertion only when the behavior intentionally
  changed, and say so in the commit message. Never delete tests, add `skip`, or
  loosen a comparison just to get green.
- **Keep the change face equal to the review face.** A change carries only the
  lines its stated behavior needs. Do not reformat, rename, or "improve"
  adjacent code in the same commit.
- **Read before you write.** Before editing, read the current implementation,
  the actual function signature, and (for ported behavior) the upstream
  reference. Guessing an API from memory produced wrong `AgentTool` arguments, a
  wrong `ImageContent` field type, and a call into the wrong module during recent
  work here.

## Quality Gates

CI runs all of these and blocks a merge. Locally you do not need the full suite
for every small edit - CI owns exhaustive verification. Pick the cheapest tier
that can still falsify your change; escalate when the change is cross-cutting.

| Tier | Command | Cost (Windows, local) | When |
| --- | --- | --- | --- |
| Static | `uv run ruff check . && uv run ruff format --check . && uv run mypy` | ~20 s | Every edit; catches most mistakes |
| Fast suite | `uv run pytest -q --ignore=tests/runtime/tui` | ~75 s | Before every commit; 1,700+ tests, everything except the TUI |
| TUI only | `uv run pytest -q tests/runtime/tui` | ~190 s | When changing `tui/` or the rendering layer |
| Full | `uv run pytest` | ~4 min | Cross-package refactors, releases, or when CI disagrees with you |

Why the fast suite is enough for most work: the TUI is a frontend adapter and
accounts for roughly 75% of local suite time while covering the least
type-checked surface. The agent loop, providers, session orchestration, tools,
commands, and guards - the parts where a logic error is expensive - all live
outside it and run in under a minute.

| Gate | Command | Guards |
| --- | --- | --- |
| Tests + coverage | `uv run pytest --cov` | behavior; coverage floor 80% |
| Lint | `uv run ruff check .` | rule violations (fail-on-error) |
| Format | `uv run ruff format --check .` | formatting drift |
| Types | `uv run mypy` | `mypy --strict` on Linux |
| Layer direction | `uv run python scripts/check_import_graph.py` | package import boundaries |
| Structure ratchet | `uv run python scripts/check_structure.py` | file size, function length, inheritance depth, module fan-out |
| Suppression ratchet | `uv run python scripts/check_suppressions.py` | `# type: ignore` / `# noqa` counts may only shrink |
| Agent-guidance ratchet | `uv run python scripts/check_agent_guidance.py` | instruction files and their root-to-module chain may only shrink |
| Clean worktree | CI only | uncommitted generated files |

The ratchet scripts read committed baselines. The structure ratchet lets small
units grow freely; above its limits a unit must split or record the growth with
`--init`. Shrinking tightens a baseline. `tests/guards/` proves each gate still
detects violations - a green gate that no longer fires is worse than no gate.

## Known Limitations (do not "fix" these)

- **14 mypy errors on Windows only** (`trust/policy.py`,
  `baldric/runtime/session/storage.py`):
  `fcntl` does not exist on Windows. CI runs mypy on Linux where it is green. Do
  not add platform shims or delete the POSIX code to silence local output.
- **121 skipped tests on Windows**: POSIX/timing semantics that run on Linux CI.
  Do not weaken or delete them to reduce the local skip count.
- **TUI tests are occasionally flaky on Windows**: the whole suite can hang in
  the asyncio Windows backend. Re-run the domain before treating it as a
  regression; the same code passes on Linux CI.
- **94 `# noqa: BLE001`**: broad exception handling is recorded debt, not a
  target. The suppression ratchet only stops it from growing.
- **The TUI is a frontend, not the architecture**: do not add Textual imports to
  `baldric.agent` or `baldric.ai` to make a feature easier.

## Scoped Instructions

Before changing a package, read the nearest scoped instructions:

- `src/baldric/ai/AGENTS.md` - provider and model streaming layer
- `src/baldric/agent/AGENTS.md` - portable agent harness
- `src/baldric/runtime/AGENTS.md` - CLI, session, TUI, and extensions
- `docs/AGENTS.md` - documentation placement and writing rules

## Project Roadmap

The implementation roadmap is tracked in GitHub issue #2:

- https://github.com/Ember452/baldric/issues/2

Use that issue as the primary reference for phase ordering and architectural intent.

## Architecture Principles

Preserve Pi's core separation of concerns:

```text
AgentHarness = reusable agent brain
AgentSession = coding-agent environment
TUI = one possible frontend
```

Baldric should be organized around these layers:

```text
baldric.ai      provider/model streaming layer
baldric.agent   portable agent harness, loop, tools, events
baldric.runtime  CLI app, resources, skills, extensions, commands, TUI integration
```

Keep the core agent package independent of CLI, Textual, Rich rendering, session file locations, and app-specific resource loading.

## TUI Direction

Use Textual for the full interactive TUI, but only behind an adapter boundary. The agent harness should emit events; UI layers should consume those events.

Early phases should prioritize:

1. print-mode CLI
2. Rich renderers
3. Textual interactive app

Do not let Textual become a dependency of the reusable agent harness.

## Development Workflow

- Work in small, documented phases.
- Keep changes aligned with the roadmap issue.
- Add or update docs when introducing architectural concepts.
- Add tests for behavior before expanding features.
- Run tests and Python commands through `uv` (for example, `uv run pytest` or `uv run python ...`) so they use the project environment.
- Prefer simple, explicit abstractions over framework-heavy designs.
- Keep commits atomic: one coherent feature, fix, docs update, refactor, or cleanup per commit.

## GitHub Issue and PR Formatting

- When creating or editing GitHub issues and pull requests from the CLI, write multiline Markdown bodies through a temporary file or heredoc and pass them with `--body-file`.
- Do not pass escaped newlines like `\n` inside quoted `--body` strings; GitHub will render them literally instead of as line breaks.
- Use Markdown headings, blank lines, bullets, and backticks for commands/paths so issue and PR descriptions are readable.
- After creating or editing a GitHub issue or PR body, verify the rendered source with `gh issue view ... --json body` or `gh pr view ... --json body` when practical.

## Python Guidelines

- Target the Python version declared in `pyproject.toml`.
- Prefer typed dataclasses or schema models for core messages, events, tools, and sessions.
- Keep async boundaries explicit.
- Use fake providers and fake tools for deterministic agent-loop tests.
- Avoid provider-specific assumptions in core agent code.

## Documentation Expectations

Each substantial phase should leave behind beginner-friendly notes under `docs/internal/` (build journals, design docs, ADRs), explaining:

- what was added
- why it exists
- how it maps to Pi's design
- how to test or use it

When a phase adds or changes user-facing behavior, also update the published docs
under `docs/user/` (the "Use Baldric" guides and reference).

