# Build journal: MCP client support

What was built, why it looks the way it does, how it maps to pi's design, and
how to test it. The full product spec lives in
[mcp-client-support.md](mcp-client-support.md); the implementation plan (with
its binding execution rules and the deviations log D1–D8) is
[plans/mcp-client-implementation.md](../../plans/mcp-client-implementation.md).

## What was added

- **`baldric_mcp`** — a new top-level package beside `baldric_coding`,
  delegating the wire protocol to the official `mcp` SDK (pinned `>=1.0,<2`,
  1.30.0 at build time):
  - `config.py`: `mcp.json` parsing (user + trusted project), merge with
    project replacement and `enabled`-only overrides, `${VAR}` and `~`
    expansion, and `/mcp on|off` write-back that preserves the file's
    indentation and unrelated keys.
  - `client.py`: one supervised connection per server — the six-state
    machine, transient-error retry for initial HTTP connects, HTTP 401 →
    `needs-auth`, lazy reconnect on a dropped connection, and a per-call
    deadline watchdog that progress notifications reset.
  - `supervisor.py`: ownership of all connections — concurrent start,
    bounded `wait_ready` for the first-turn wait, tool-call routing, and the
    `/mcp on|off|restart` operations. It never reads config files.
  - `adapter.py`: ecosystem tool naming (`mcp__<server>__<tool>`, sanitized,
    hash-suffixed on overflow/collision), schema normalization, and result
    conversion with the 20 KiB middle cut.
- **A thin built-in extension** (`baldric_coding/extensions/builtins/mcp/`)
  that boots the supervisor on `session_start`, registers/withdraws tools
  through the live seam as servers change state, publishes the `MCP servers`
  prompt section, admits the first turn (bounded wait), and serves `/mcp`.
- **Generic agent seams** (no MCP semantics in them): `bind_live_tools` +
  `unregister_tool` on the extension runtime (registrations reach the
  harness's per-run tool list immediately), `update_system_prompt` on the
  harness, `refresh_system_prompt` on the session and the `BoundSession`
  protocol, and upsert semantics for titled prompt sections.
- **Composition-level child gate**: `CodingSessionConfig.disabled_built_in_extensions`
  filters the built-in registry; the subagents child passes `frozenset({"mcp"})`
  so children never boot MCP servers.
- **Tests**: unit suites per module (`tests/mcp/`), extension tests with a
  fake supervisor (`tests/coding/extensions/test_mcp_extension.py`), a
  real-process stdio integration test against a FastMCP fixture, and the
  resume-repair regression.

## Why it looks this way (pi mapping)

- The state machine, transient retry, lazy reconnect, and per-call timeout
  with progress reset port `pi-main/packages/coding-agent/src/extensions/mcp/runtime.ts`.
- The naming rule is a line-by-line port of `pi-main/packages/mcp/src/naming.ts`;
  the 20 KiB middle cut ports `pi-main/packages/mcp/src/output-limit.ts`.
- The `mcpServers` config shape, project replacement, override entries, and
  write-back semantics port `packages/coding-agent/src/extensions/mcp/config.ts`.
- One deliberate Baldric difference: `command` + `url` together is a
  diagnostic (pi silently prefers `url`) — an ambiguous config should fail
  visible.
- pi reuses one runtime across `/new` and `/resume`; Baldric stages a fresh
  runtime per generation (trust boundary), so the MCP extension boots one
  supervisor per generation and always shuts it down on `session_shutdown` —
  keeping connections across generations would orphan server processes.

## How to test

```bash
uv run pytest -q tests/mcp tests/coding/extensions/test_mcp_extension.py
uv run pytest -q tests/mcp/test_integration_stdio.py   # spawns a real server
uv run pytest -q --ignore=tests/coding/tui             # full fast suite
```

Manual smoke: put a server in `~/.baldric/mcp.json`, run `uv run baldric`,
`/mcp` should list it connected, a tool call should work, and `/mcp off
<name>` should persist the choice.
