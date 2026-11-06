# Pull request

## What changed

<!-- One paragraph. What behavior changed, and why. -->

## How it was verified

<!-- List only the commands you actually ran. -->

- [ ] `uv run pytest --cov`
- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run mypy`
- [ ] `uv run python scripts/check_import_graph.py`
- [ ] `uv run python scripts/check_structure.py`
- [ ] `uv run python scripts/check_suppressions.py`
- [ ] `uv run python scripts/check_agent_guidance.py`

## Behavior proof

- [ ] Tests prove the fix works (a bug fix includes a test that failed before it)
- [ ] Golden-file diffs under `tests/expected/` are intentional and reviewed
- [ ] No existing assertion was weakened, deleted, or skipped to get green
- [ ] Ratchet baselines were only tightened, never loosened

## AI assistance

<!-- Skip only if no AI tool was used. This section exists so reviewers know
how carefully to read the diff. -->

- Tool and model:
- How it was used (drafting, refactor, tests, docs):
- [ ] I read and understand every line of this change and take responsibility
      for it. This is not unreviewed AI output.

## Notes for reviewers

<!-- Tradeoffs, follow-ups deferred, or anything surprising. -->
