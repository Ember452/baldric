# MCP client support (baldric_mcp package + built-in extension)

Status: approved design v2 (external review incorporated), pending implementation plan.

Baldric gains an MCP (Model Context Protocol) **client**: users configure MCP
servers, Baldric connects to them, and their tools become ordinary agent tools.
The protocol is delegated to the official `mcp` Python SDK
(modelcontextprotocol/python-sdk); Baldric writes only the product layer around
it: configuration, trust gating, connection supervision, tool adaptation, and
the `/mcp` command.

The shape mirrors Pi's own: a standalone protocol package plus a thin built-in
extension in the coding app. The agent core never learns that MCP exists.

## Goals

- A mature terminal coding agent must accept the MCP ecosystem: users already
  run MCP servers (browser, databases, issue trackers, internal APIs) and
  expect an agent to reuse them.
- Tool-name stability, config format, and trust behavior must be frozen before
  1.0: they become backward-compatibility promises the first day real users
  exist. Frozen names follow the ecosystem convention, not an invented one.
- The layered architecture is preserved: `baldric_agent`/`baldric_ai` gain no
  MCP awareness; MCP is a tool source that arrives through the extension API.

## Non-goals (explicit MVP boundary)

- **OAuth for remote servers.** MVP authenticates via `${ENV}` expansion in
  headers/commands only. An HTTP 401 surfaces as a `needs-auth` state.
- **MCP server mode** (exposing Baldric itself to other agents).
- **resources / prompts / sampling.** Tools only.
- **Deferred tool loading** (pi's `tool_search`/codemode). Token budget is
  managed by per-server enable/disable in MVP. The `mcp__<server>__` naming is
  chosen so a future namespace/deferred layer slots in without a rename.
- **`list_changed` notifications.** A server that adds or removes tools
  mid-session keeps its connect-time tool set until `/mcp restart`.
- **Tool annotations** (`readOnlyHint`, `destructiveHint`, …). Baldric's
  `AgentTool` has no annotation field; fold hints into descriptions later.
- **Hot reload of project config changes.** Config is read at session start;
  `/mcp restart` re-reads it.

## Architecture

```text
baldric_coding/extensions/builtins/mcp/   thin extension: config load, trust gate,
        │ depends on                       live tool registration, /mcp, prompt section
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

The package split is justified by a second consumer: library users of
`AgentHarness` and a future MCP server mode reuse `baldric_mcp` unchanged.

## Package: `baldric_mcp`

### `config.py`

- `McpServerConfig` — frozen dataclass. Shared fields: `name`, `enabled`,
  `description` (feeds the prompt section), `timeout` (per-call, **seconds**,
  default 60; progress notifications reset the deadline, as in pi), optional
  `type` (`"stdio"` | `"http"`). Paste compatibility wins: `type` is inferred
  from `command` (stdio) or `url` (http) when absent; when present it must
  match the entry's fields, and a mismatch is rejected. stdio:
  `command`/`args`/`env`/`cwd`; http: `url`/`headers`.
- `load_mcp_config(user_path, project_path) -> McpConfigLoadResult` — merges
  user-level then project-level; a project entry with the same name overrides
  the user entry. Validation problems become diagnostics; a bad entry never
  tears down the session. Server names that would collapse to the same
  `mcp__<server>` namespace (differ only in `-` vs `_`) are rejected, as in
  pi.
- `${VAR}` expansion uses only an injected environment snapshot, never
  `os.environ` directly. Unresolvable variables are diagnostics; the entry
  stays disabled.
- **Child environment (stdio):** snapshot + config `env` merged, config wins.
  Decided semantics: many servers assume a full environment (PATH, HOME);
  passing only config `env` breaks them.
- `~` and `~/…` (and `~\…` on Windows) expand in `command`, `args`, and `cwd`.

### `client.py`

- `McpServerConnection` — one server connection wrapping the SDK session.
  State machine adopted from pi:
  `connecting | connected | disconnected | needs-auth | failed | closed`.
  - `disconnected`: the connection dropped mid-session (stdio server exited,
    HTTP socket died). Tools stay registered; the next call attempts a lazy
    reconnect. No background retry loop for drops.
  - `failed`: connect-time retries exhausted. Tools are withdrawn; `/mcp
    restart` revives.
  - `needs-auth`: HTTP 401 without usable credentials. Tools withdrawn;
    notify suggests header/env configuration.
- Initial connect: bounded retries on **transient** errors only (HTTP 408,
  429, 5xx except 501, connection-type errors), 3 attempts, 1 s then 3 s
  backoff.
- Per-call timeout from config (`timeout` seconds, default 60); a progress
  notification resets the deadline.
- stdio servers: child stderr captured to `~/.baldric/logs/mcp/<server>.log`;
  on connect failure the stderr tail joins the reported error.
- Exposes `instructions` (the `initialize` result field) and the tool list.

### `supervisor.py`

- `McpSupervisor` — owns all connections. `start(configs)` (non-blocking:
  connects run as background tasks), `wait_ready(timeout)` (resolves when no
  configured server is still `connecting`), tool-set-changed callback,
  `restart(name)` (re-reads config), `set_enabled(name, bool)`, `shutdown()`.
- `wait_ready` caps at 10 s regardless of argument, as in pi's first-turn
  admission.

### `adapter.py`

Pure conversion layer, fully unit-testable. Rules (porting pi's `tools.ts`
decisions where they apply):

- **Naming:** `mcp__<server>__<tool>` — the ecosystem convention (pi, Codex,
  Claude Code). Sanitize everything outside `[A-Za-z0-9_]` to `_`; cap at 64
  chars; on overflow or sanitization collision append `_` + first 8 hex of
  sha256 over `server\0tool`. **Frozen with 1.0** — tool names live in session
  JSONL history.
- **Label:** `"<server>/<tool>"` for renderers.
- **Description fallback chain:** `tool.description.strip() || tool.title ||
  "MCP tool <tool> from server <server>"`.
- **Schema:** normalized to `type: object` with `properties` present; empty
  schema becomes `{"type": "object", "properties": {}}`.
- **Results:** text blocks → `TextContent`; image blocks → `ImageContent`
  when the active model supports image tool results, else a placeholder line;
  resource blocks → placeholder text. `isError` → `AgentToolResult.is_error`;
  an `isError` result with no text gets `"MCP tool <server>/<tool> returned
  an error"`.
- **Progress:** MCP progress notifications map to the executor's `on_update`
  partial results (`progress/total/message` as text) — Baldric's
  `AgentTool.execute` already carries the callback.
- **Truncation:** the cap follows pi's battle-tested line: model-facing text
  over 20 KiB keeps its start and end with the middle cut, the full text is
  saved to an output file, and the truncation note names that path. The house
  pattern (`baldric_coding/tools/truncate.py`) implements it in the extension
  layer; `baldric_mcp` itself stays import-clean and returns full text plus a
  size measurement.

## Built-in extension: `baldric_coding/extensions/builtins/mcp/`

- Registered in `builtin_registry.py` as `name="mcp"`, `hidden=True`,
  `setup_with_context` (paths + environment snapshot). Capabilities:
  `ExtensionCapabilities(tools=True, hooks=True)` — never Textual.
- **Lifecycle.** Sync `setup()` loads config (user + project, project only
  when `api.context.project_trusted`; otherwise one diagnostic) and registers
  handlers. The async `session_start` handler boots the supervisor
  non-blocking (background connect tasks — the house pattern:
  `asyncio.get_running_loop().create_task`). `session_shutdown(quit|reload)`
  closes every subprocess and connection; `new`/`resume`/`branch` keep
  connections (same cwd, same config).
- **First-turn admission.** An async `input` hook (awaited by the session run
  path before the run starts) awaits `supervisor.wait_ready()` **once** per
  session when any server is still connecting; capped at 10 s, then proceeds
  regardless. TUI startup is never delayed; the first message just waits a
  little so fresh-server tools are actually callable.
- **Live tool registration.** The session binds the materialized tool list
  into the runtime (`bind_live_tools`); `register_tool`/`unregister_tool`
  mutate both the registry and that live list. Tools appear as servers become
  ready and disappear on `failed`/`needs-auth`/`/mcp off`. Registrations
  rejected by `allowed_tool_names` filtering are ignored with a diagnostic.
- **`mcp_servers` prompt section.** After the first `wait_ready` settles (or
  on server state change), the extension registers one prompt section: per
  enabled server, `name — first line of config.description or server
  instructions` (capped per server and in total). Rendered via the session's
  `refresh_system_prompt()` seam; servers without instructions contribute
  name and tool count only.
- **Child sessions.** Subagent child sessions do not get MCP in MVP — each
  child spawning its own server processes is waste. The decision is one gate
  function (`_session_wants_mcp`) with a docstring naming the future path
  (shared supervisor or per-child opt-in flag); nothing else in the design
  assumes top-level ownership, so enabling it later is a one-line change.
- **`/mcp` command** (sync handler; async work scheduled onto the loop):
  no args lists servers (name, state, transport, tool count, first error
  line); `/mcp restart <name>` re-reads config and reconnects; `/mcp off
  <name>` closes the connection, withdraws its tools, and writes
  `enabled: false` back to the file that defines the server (indentation and
  unrelated content preserved, as in pi's `mcp.json` write-back); `/mcp on
  <name>` reconnects and clears the flag the same way.
- Server state changes surface via `ui.notify`; no UI components.

## Configuration format

User: `~/.baldric/mcp.json`; project: `<cwd>/.baldric/mcp.json`. Top-level key
`mcpServers` — compatible with pi and Claude Desktop so existing config can be
pasted:

```json
{
  "mcpServers": {
    "github": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_TOKEN": "${GITHUB_TOKEN}" },
      "timeout": 60
    },
    "docs": {
      "type": "http",
      "url": "https://example.com/mcp",
      "headers": { "Authorization": "Bearer ${DOCS_TOKEN}" }
    }
  }
}
```

Per-server optional `enabled` (default true) and `description`. Unknown
fields warn but are tolerated; unknown `type` is rejected.

**Trust gate:** the project-level file loads only when
`api.context.project_trusted` is true; otherwise a single diagnostic. Trusting
a project means allowing it to spawn processes — the same trust level as
project extensions and bash.

## Resume, branch, and missing tools

Tool names are written into durable JSONL history. On resume/branch:

- Dangling tool calls (assistant call without a result) are repaired by the
  harness's existing `_append_interrupted_tool_results` prelude — synthetic
  results, no crash. A regression test pins this for MCP tool names.
- A model call to an MCP tool whose server is `failed`/`needs-auth`/disabled
  returns a synthetic "tool unavailable" error result; it never raises into
  the run.

## Security & failure semantics

- Auth is env/header only in MVP; tokens expand from the environment snapshot
  and are never logged.
- Windows command resolution: a small deterministic helper probes `npx` →
  `npx.cmd`/`npx.exe` on PATH (pi upstream needed exactly this).
- No unbounded respawn: connect retries are bounded; mid-session drops are
  lazy-reconnected on next call only.

## Existing-code touchpoints (authorized modifications)

Every change traces to this design; nothing adjacent is "improved":

| File | Change |
| --- | --- |
| `pyproject.toml` | add `mcp>=1.x` dependency; add `src/baldric_mcp` to wheel packages and mypy packages |
| `scripts/check_import_graph.py` + `tests/guards/test_import_boundaries.py` | `baldric_mcp` may not import agent/ai/coding/textual/rich; agent/ai may not import `baldric_mcp` |
| `src/baldric_coding/config/paths.py` | add `user_mcp_config_path` and `project_mcp_config_path(cwd)` |
| `src/baldric_coding/extensions/runtime.py` | add `bind_live_tools(list)`; `register_tool`/`unregister_tool` also mutate the bound live list |
| `src/baldric_coding/extensions/api.py` | add `unregister_tool(name)` (source-owned removal, generation-guarded) |
| `src/baldric_coding/session/session.py` | bind the composed tool list into the runtime; add `refresh_system_prompt()` re-running the existing builder from current registries |
| `src/baldric_agent/harness.py` | add `update_system_prompt(str)` (`AgentHarnessConfig` is a non-frozen slots dataclass and the run path reads `config.system` per run; the method assigns the field) |
| `src/baldric_coding/extensions/builtin_registry.py` | declare the `mcp` built-in extension |

If the structure ratchet flags `session.py` growth, record it with `--init`
per house rules rather than splitting in the same change.

## Testing strategy

- Supervisor/client lifecycle tests use scripted fake connections and the
  SDK's in-memory client/server pair where useful — deterministic, no real
  subprocesses outside integration tests.
- One to two integration tests spawn a real fixture stdio MCP server from
  `tests/helpers/` (spawn, list tools, call tool, exit).
- Unit: config parse/merge/expansion/trust-gate/namespace-clash; adapter
  naming (sanitize, 64-cap, hash suffix), schema normalization, result
  conversion, `is_error` fallback text; live tool-list seam (register after
  bind appears in the next run's tool list — fake provider).
- Regression: resume with dangling `mcp__…` calls produces synthetic results;
  call to a withdrawn tool yields "tool unavailable".
- Windows command-resolution helper gets table tests.

## Phases (input to the implementation plan)

1. `baldric_mcp.config` + `BaldricPaths` additions + config tests.
2. `baldric_mcp.client` + `supervisor` over the SDK (in-memory pair tests).
3. `baldric_mcp.adapter` (+ tests).
4. Agent seams: `bind_live_tools`, `unregister_tool`,
   `refresh_system_prompt`, `update_system_prompt` (+ tests proving the loop
   sees the changes).
5. Extension wiring: built-in registration, trust gate, dynamic registration,
   `input` first-turn wait, `mcp_servers` section, `/mcp`, shutdown/reload
   lifecycle (+ fake-supervisor tests + fixture integration test).
6. Polish: Windows command resolution, stderr logs, truncation with full
   output file (+ tests).
7. Docs: `website/content/` MCP guide, `dev-notes/` build journal, ratchet
   checks green.

## Deliberately deferred (post-MVP)

OAuth flows, MCP server mode, resources/prompts/sampling, deferred tool
loading (`tool_search`/codemode), `list_changed` handling, tool annotations,
hot config reload, direct `ImageContent` tool results for image-unsupported
models, child-session MCP sharing.
