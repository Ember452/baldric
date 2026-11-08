# MCP client support (baldric_mcp package + built-in extension)

Status: approved design, pending implementation plan.

Baldric gains an MCP (Model Context Protocol) **client**: users configure MCP
servers, Baldric connects to them, and their tools become ordinary agent tools.
The protocol is delegated to the official `mcp` Python SDK
(modelcontextprotocol/python-sdk); Baldric writes only the product layer around
it: configuration, trust gating, connection supervision, tool adaptation, and
the `/mcp` command.

This mirrors Pi's own shape: a standalone protocol package (`pi-mcp`) plus a
thin built-in extension in the coding app. The agent core never learns that
MCP exists.

## Goals

- A mature terminal coding agent must accept the MCP ecosystem: users already
  run MCP servers (browser, databases, issue trackers, internal APIs) and
  expect an agent to reuse them.
- Tool-name stability, config format, and trust behavior must be frozen before
  1.0: they become backward-compatibility promises the first day real users
  exist.
- The layered architecture is preserved: `baldric_agent`/`baldric_ai` gain no
  MCP awareness; MCP is a tool source that arrives through the extension API.

## Non-goals (explicit MVP boundary)

- **OAuth for remote servers.** MVP authenticates via `${ENV}` expansion in
  headers/commands only. An HTTP 401 surfaces as an `auth-required` state.
- **MCP server mode** (exposing Baldric itself to other agents).
- **resources / prompts / sampling.** Tools only.
- **Deferred tool loading** (pi's `tool_search`/codemode). Token budget is
  managed by per-server enable/disable in MVP.
- **Hot reload of project config changes.** Config is read at session start;
  `/mcp restart` re-reads it.
- **First-turn admission wait.** If a turn starts while servers are still
  connecting, their tools are simply absent that turn. (Pi waits up to ~10 s;
  revisit if it bites.)

## Architecture

```text
baldric_coding/extensions/builtins/mcp/   thin extension: config load, dynamic
        │ depends on                       tool registration, /mcp command
baldric_mcp (NEW top-level package)        client core: config, supervisor,
        │ depends on                       adapter (protocol delegated to `mcp` SDK)
baldric_protocol                           conversion target: AgentTool / AgentToolResult
```

Dependency direction: `baldric_coding → baldric_mcp → baldric_protocol`.
`baldric_mcp` must not import `baldric_agent`, `baldric_ai`, `baldric_coding`,
`textual`, or `rich`. `baldric_agent`/`baldric_ai` must not import
`baldric_mcp`. The `mcp` SDK dependency lives only in `baldric_mcp`.

The SDK is built on anyio + httpx + pydantic — all three are already Baldric
dependencies. Pin the stable `mcp` 1.x line at implementation time (2.0 is
pre-release; do not adopt).

## Package: `baldric_mcp`

Four focused modules:

### `config.py`

- `McpServerConfig` — frozen dataclass: `name`, transport (stdio:
  `command`/`args`/`env`/`cwd`; http: `url`/`headers`), `enabled`.
- `load_mcp_config(user_path, project_path) -> McpConfigLoadResult` — merges
  user-level then project-level; a project entry with the same name overrides
  the user entry. Validation problems become diagnostics; a bad entry never
  tears down the session.
- `${VAR}` expansion uses only an injected environment snapshot, never
  `os.environ` directly (testability, no ambient reads). Unresolvable
  variables are diagnostics; the server entry stays disabled.

### `client.py`

- `McpServerConnection` — one server connection wrapping the SDK session.
  States: `connecting → ready / failed / auth-required`. Methods:
  `list_tools()`, `call_tool(name, arguments, timeout)`, `close()`.
- stdio servers: child stderr is captured to
  `~/.baldric/logs/mcp/<server>.log` for debuggability.

### `supervisor.py`

- `McpSupervisor` — owns all connections. `start(configs)`, a tool-set-changed
  callback, `restart(name)`, `shutdown()`.
- Bounded retry on connection failure; budget exhaustion marks the server
  `failed` and removes its tools (notify, never hang the session). `/mcp
  restart` revives manually and re-reads config.
- Concrete defaults (tunable in the plan review): connect timeout 10 s, tool
  call timeout 60 s, retry budget 3 attempts per process lifetime with 1 s
  then 3 s backoff.

### `adapter.py`

Pure conversion layer, fully unit-testable. Rules:

- **Naming:** `<server>_<tool>` with invalid characters folded to `_`,
  final name ≤ 64 chars (provider tool-name limits); deterministic suffix on
  collision. **This scheme freezes with 1.0** — tool names are written into
  session JSONL history.
- **Schema:** normalized to `type: object` with `properties` present; empty
  schema becomes `{"type": "object", "properties": {}}`. MCP `$ref` quirks are
  passed through when usable; validation failures produce readable errors.
- **Results:** text blocks → `TextContent`; `isError` → `AgentToolResult.
  is_error`; image/resource blocks become placeholder text
  (`[image: image/png, N bytes]`) until provider support for image tool
  results is verified. Output capped at 256 KiB with a truncation note.
- Cancellation token is accepted but MVP maps it to the call timeout, not
  mid-flight SDK cancellation.

## Built-in extension: `baldric_coding/extensions/builtins/mcp/`

- Registered in `builtin_registry.py` as `name="mcp"`, `hidden=True`
  (consistent with other product capabilities), using `setup_with_context` to
  receive `paths` and the environment snapshot. Capabilities:
  `ExtensionCapabilities(tools=True, hooks=True)` — never Textual.
- **Lifecycle.** Sync `setup()` only loads config and registers an async
  `session_start` handler (the house pattern: subagents schedule background
  work from handlers via `asyncio.get_running_loop().create_task`). The
  handler boots the supervisor; tools register dynamically as servers become
  ready (the runtime registry accepts post-setup registration; first per name
  wins). `session_shutdown(quit|reload)` closes every subprocess and
  connection; `new`/`resume`/`branch` keep connections (same cwd, same
  config).
- **`/mcp` command** (sync handler; async work scheduled onto the loop like
  subagents do): no args lists servers (name, state, transport, tool count);
  `/mcp restart <name>` re-reads config and reconnects that server;
  `/mcp off <name>` closes the connection and withdraws its tools;
  `/mcp on <name>` reconnects (runtime-only toggle in MVP, not persisted).
- Server failure / auth-required surfaces via `ui.notify`, no UI components.

## Configuration format

User: `~/.baldric/mcp.json`; project: `<cwd>/.baldric/mcp.json` (paths added
to `BaldricPaths`). Top-level key `mcpServers` — deliberately compatible with
pi and Claude Desktop so users can paste existing config:

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_TOKEN": "${GITHUB_TOKEN}" }
    },
    "docs": {
      "url": "https://example.com/mcp",
      "headers": { "Authorization": "Bearer ${DOCS_TOKEN}" }
    }
  }
}
```

Per-server optional `"enabled": false`. Unknown fields warn but are tolerated
(forward compatibility); unknown transports are rejected.

**Trust gate:** the project-level file loads only when
`api.context.project_trusted` is true; otherwise a single diagnostic ("project
MCP servers ignored: project not trusted"). Trusting a project means allowing
it to spawn processes — the same trust level as project extensions and bash.

## Security & failure semantics

- Auth is env/header only in MVP; tokens are expanded from the environment
  snapshot and never logged. A 401 marks the server `auth-required` with a
  notify suggesting the header/env configuration.
- Windows command resolution gets a small deterministic helper (`npx` → probe
  `.cmd`/`.exe` on PATH); pi upstream needed exactly this, it is a maturity
  detail, not an optional extra.
- Crash policy: bounded retry → `failed` → tools removed + notify; no
  unbounded respawn.

## Existing-code touchpoints (authorized modifications)

Every change traces to this design; nothing adjacent is "improved":

| File | Change |
| --- | --- |
| `pyproject.toml` | add `mcp>=1.x` dependency; add `src/baldric_mcp` to wheel packages and mypy packages |
| `scripts/check_import_graph.py` | add RULES: `baldric_mcp` may not import agent/ai/coding/textual/rich; `baldric_agent`/`baldric_ai` may not import `baldric_mcp` |
| `tests/guards/test_import_boundaries.py` | same new rules (the guard test exercises the same scan) |
| `src/baldric_coding/config/paths.py` | add `user_mcp_config_path` and `project_mcp_config_path(cwd)` |
| `src/baldric_coding/extensions/builtin_registry.py` | declare the `mcp` built-in extension |
| `src/baldric_coding/extensions/runtime.py` + `api.py` | add a minimal `unregister_tool` seam (source-owned removal), mirroring `register_tool`; needed for server failure / `/mcp off` to actually withdraw tools |

No structure-ratchet baseline changes are expected; new modules start small.

## Testing strategy

- `tests/helpers/` gains a fixture stdio MCP server speaking real JSON-RPC.
- Unit: config parse/merge/expansion/trust-gate; supervisor lifecycle
  (ready/failed/restart/shutdown) with controlled fake connections; adapter
  naming, schema normalization, result conversion, truncation, `is_error`.
- Extension flow with a fake supervisor (deterministic, no real
  subprocesses), plus one integration test spawning the fixture server.
- Windows command-resolution helper gets its own table tests.

## Phases (input to the implementation plan)

1. `baldric_mcp.config` + paths additions + config tests.
2. `baldric_mcp.client` + `supervisor` over the SDK, fixture-server tests.
3. `baldric_mcp.adapter` (+ tests).
4. Extension wiring: built-in registration, trust gate, dynamic registration,
   `/mcp`, shutdown/reload lifecycle, `unregister_tool` seam (+ tests).
5. Polish: Windows command resolution, stderr logs, output caps (+ tests).
6. Docs: `website/content/` MCP guide, `dev-notes/` build journal, ratchet
   checks green.

## Deliberately deferred (post-MVP)

OAuth flows, MCP server mode, resources/prompts/sampling, deferred tool
loading, persisted per-server toggles, first-turn admission wait, hot config
reload, direct `ImageContent` tool results.
