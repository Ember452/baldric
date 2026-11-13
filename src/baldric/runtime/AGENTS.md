# baldric.runtime - Application Layer

The coding-agent application: CLI, session orchestration, providers, platform,
features, frontends. This layer may know about files, terminals, and user
interaction.

## Responsibilities

- `cli.py`: argument parsing, print/JSON/RPC/TUI mode selection, `baldric
  install` and `baldric extensions` subcommands.
- `session/`: session orchestration (`session.py`), event plumbing and retry
  policy (`runtime.py`), provider helpers.
- `providers/`: settings, catalog, credentials, auth, backends.
- `platform/` (extension framework), `features/` (string-loaded bundles),
  `frontends/` (surfaces: TUI), `commands/`, `tools/`, `context/`,
  `rendering/`, `update/`, `trust/`.

## Boundaries

- `session`, `tools`, `trust`, `context`, `providers`, and backends must not
  import `baldric.runtime.frontends`; CI enforces this.
- All rendering goes through `rendering/` or the frontend adapter; the agent
  harness must not learn about Textual.
- Extensions are loaded behind the `ExtensionRuntime` generation boundary; new
  registrations go through the extension API, never through direct imports into
  session internals.

## Known Limitations (do not "fix" these)

- TUI tests are occasionally flaky on Windows (asyncio). Re-run the domain
  instead of adding sleeps; the same code passes on Linux CI.
- `providers/config` uses schema version 2 with provider preferences; legacy
  migration paths are load-bearing. Do not delete them.
- `session/runtime.py` deliberately keeps separate overflow-compaction and
  Hugging Face failover retries distinct from image-tool recovery. Do not merge
  these paths.
- `frontends/tui/app.py` is the largest file in the repository.
  `scripts/check_structure.py` locks its size; shrink it, never grow it.

## Tests

- TUI tests use Textual's `app.run_test()` and the fakes in `tests/helpers/`.
- Prefer deterministic fakes over timing waits; if a test needs a sleep, the
  behavior is probably wrong.
