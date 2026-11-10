# Bundled Baldric self-knowledge

Baldric follows Pi's progressive-disclosure approach to product knowledge. The default system prompt identifies installed documentation and examples, then routes Baldric-specific requests to those files without loading them into every conversation.

## Packaged resources

Self-knowledge lives under `src/baldric_coding/data/`:

```text
docs/       concise routing references and contributor workflows
examples/   readable extension examples
```

The prompt points directly to extension creation, skills, custom and built-in providers/models, CLI commands, TUI behavior, and architecture. It tells the agent to read relevant documents and examples completely and follow their cross-references before implementing.

Baldric does not expose its own maintenance workflows as Agent Skills. Skills are user and project resources, so Baldric's product documentation does not appear in the skills sidebar, compete with user skill names, or disappear when skill loading is disabled.

## Why

Repository `AGENTS.md` helps only when Baldric is running inside its source checkout. Packaged documentation lets an installed Baldric retain product knowledge without bloating the base prompt. Keeping that documentation separate from skills also preserves a clean user-owned skill namespace and matches Pi's design.

The extension and model/provider documents contain the detailed workflows previously carried by the bundled `create-baldric-extension` and `baldric-model-catalog` skills. The packaged extension example remains available as a concrete starting point.

## Architecture

Self-documentation belongs to `baldric_coding`, not the portable `baldric_agent` harness. `self_docs.py` resolves installed documentation and example paths, while `system_prompt.py` emits the routing hints. `BaldricResourcePaths` discovers only user and project skills. Hatch packages the documentation and examples as part of `baldric_coding`.

## Verification

```bash
uv run pytest tests/test_system_prompt.py tests/test_skills.py tests/test_resources.py tests/test_package_metadata.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
cd website && hugo --minify && npx --yes pagefind@latest --site public
```
