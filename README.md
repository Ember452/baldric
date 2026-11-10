<p align="center">
  <img src="docs/assets/baldric-header.svg" alt="Baldric — a Python coding-agent harness inspired by Pi" width="100%" />
</p>

<p align="center">
  <strong>A small, readable terminal coding agent — and a working example of how coding agents are built.</strong>
</p>

<p align="center">
  <a href="https://ember452.github.io/baldric/">Documentation</a>
  ·
  <a href="https://ember452.github.io/baldric/quickstart/">Quickstart</a>
  ·
  <a href="https://ember452.github.io/baldric/internals/architecture/">Architecture</a>
  ·
  <a href="https://pypi.org/project/baldric/">PyPI</a>
  ·
  <a href="https://github.com/Ember452/baldric/issues/2">Roadmap</a>
</p>

<p align="center">
  <strong><a href="https://github.com/Ember452/baldric/issues">Join the community →</a></strong>
</p>

---

## What is Baldric?

**Baldric is a coding agent that lives in your terminal.** You type requests like
"explain this repo", "add tests", or "fix this stack trace"; Baldric can read files,
edit code, run commands, and keep a durable session history while streaming what
it is doing.

Baldric is also meant to be read. It is a teaching project for understanding the
shape of a coding-agent system without starting from a giant production
codebase.

```text
baldric.coding  →  baldric.agent  →  baldric.ai
```

- `baldric.ai` translates model providers into Baldric's provider-neutral stream.
- `baldric.agent` owns the portable brain: messages, tools, events, loop, harness,
  and session primitives.
- `baldric.coding` wraps the brain as a real coding app: CLI, TUI, file/shell tools,
  provider config, project instructions, skills, and on-disk sessions.

The important boundary is:

```text
AgentHarness = reusable brain
CodingSession = coding-agent environment
TUI = one possible frontend
```

The core does not know about Textual, Rich, local config paths, slash commands,
or rendering. Frontends consume events.

## Install

Baldric is published on PyPI as `baldric` and installs a `baldric` command.
It requires Python 3.12 or newer. The recommended installers use
[`uv`](https://docs.astral.sh/uv/) and install it first when necessary.

macOS and Linux:

```bash
curl -LsSf https://ember452.github.io/baldric/install.sh | sh
```

Windows PowerShell:

```powershell
irm https://ember452.github.io/baldric/install.ps1 | iex
```

The installers do not use `sudo`. They announce before installing `uv`, install
Baldric in an isolated tool environment, verify `baldric --version`, and report if a
shell restart is needed. You can [inspect the shell installer](https://ember452.github.io/baldric/install.sh)
or [PowerShell installer](https://ember452.github.io/baldric/install.ps1) before running it.

Already have a package manager? Install Baldric directly:

```bash
uv tool install baldric
# or
pipx install baldric
# or
python -m pip install baldric
```

Then check it worked:

```bash
baldric --version
```

Baldric is also available on [conda-forge](https://conda-forge.org), and can be installed using [pixi](https://pixi.prefix.dev/latest/#installation):

```bash
pixi global install baldric
```

Upgrade a normal installation with:

```bash
baldric update
```

For local development:

```bash
git clone https://github.com/Ember452/baldric.git
cd baldric
uv sync --dev
uv run baldric --version
```

To make the checkout-backed command available globally, install it as an
editable tool:

```bash
uv tool install --editable --force .
```

Run that command again after `git pull`. Editable installs expose source-code
changes immediately, but the tool environment's package metadata, dependencies,
and entry points are only refreshed when uv reinstalls the tool. Without the
refresh, `baldric --version` can still show the version from the previous install.

## Quickstart

Run Baldric from the project you want it to work on:

```bash
cd my-project
baldric
```

Then type a request and press **Enter**:

```text
explain what this project does
```

One-shot print mode is useful for scripts and quick prompts:

```bash
baldric -p "summarize the architecture"
baldric --cwd /path/to/project -p "find the CLI entry point"
```

Baldric needs a model provider. Start Baldric and connect one with `/login`:

```bash
baldric
```

```text
/login
/login openai
/login openai-codex
/model
```

Baldric ships with support for OpenAI, Anthropic, OpenAI Codex subscription auth,
OpenRouter, Hugging Face, and custom OpenAI-compatible endpoints, including local
models. See the [providers guide](https://ember452.github.io/baldric/guides/providers-and-models/).

The built-in catalog lives in `src/baldric/coding/data/catalog.toml`; add your own
providers and models by dropping a `~/.baldric/catalog.toml` with the same schema —
no code changes required.

## What Baldric can do

- Interactive Textual TUI and non-interactive print mode.
- Built-in coding tools: `read`, `write`, `edit`, and `bash`.
- Durable JSONL sessions under `~/.baldric/sessions/` with resume and branching.
- Slash commands for login, model selection, sessions, compaction, export, theme,
  and more.
- Project instructions from `AGENTS.md`, `.baldric/`, and `.agents/` resources.
- User skills, prompt templates, and custom TUI themes.
- Context accounting, manual compaction, and optional automatic compaction.
- Provider-neutral event rendering for Rich, plain text, JSON, transcripts, and
  custom frontends.

## Philosophy

Baldric follows a few rules:

- **Small layers beat magic.** Each package has one job and can be read alone.
- **Events are the contract.** Providers, renderers, the TUI, and custom
  frontends meet at a typed event stream.
- **The core stays portable.** The reusable harness does not depend on the CLI,
  Textual, Rich, or Baldric's file layout.
- **Tools are ordinary typed functions.** A tool is a schema plus an async
  executor returning a structured result.
- **Sessions are durable and inspectable.** History is append-only JSONL; active
  context can be compacted without rewriting the record.
- **Documentation follows implementation.** The public docs explain the result;
  `dev-notes/` preserves the phase-by-phase build journal.

## Use Baldric as a library

```python
from baldric.agent import AgentHarness, AgentHarnessConfig

harness = AgentHarness(
    AgentHarnessConfig(
        provider=provider,
        model="my-model",
        system="You are a helpful coding agent.",
        tools=tools,
    )
)

async for event in harness.prompt("Explain this package"):
    print(event)
```

Because the harness emits events instead of rendering UI directly, the same core
can drive the built-in TUI, print mode, or a frontend you build yourself.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for project philosophy, layer boundaries, testing expectations, and pull request guidelines.

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Run Baldric from the checkout:

```bash
uv run baldric
uv run baldric -p "explain this repo"
```

Run the Astro documentation site (Node 22.12+):

```bash
cd website
npm ci
npm run dev
```

Open <http://localhost:4321/>. Build with `npm run build`, then
`npm run preview` to test Pagefind search. Run `npm run check`,
`npm run format:check`, and `npm test` (after building) for website checks.

## Documentation

User docs are published at <https://ember452.github.io/baldric/> and live in
`website/content/`.

Useful entry points:

- [What is Baldric?](https://ember452.github.io/baldric/what-is-baldric/)
- [Quickstart](https://ember452.github.io/baldric/quickstart/)
- [Core concepts](https://ember452.github.io/baldric/concepts/)
- [Architecture overview](https://ember452.github.io/baldric/internals/architecture/)
- [The agent loop & events](https://ember452.github.io/baldric/internals/agent-loop/)
- [CLI reference](https://ember452.github.io/baldric/reference/cli/)

Baldric is under active development. The implementation roadmap is tracked in
[GitHub issue #2](https://github.com/Ember452/baldric/issues/2).

## License

Baldric is released under the [MIT License](LICENSE).
