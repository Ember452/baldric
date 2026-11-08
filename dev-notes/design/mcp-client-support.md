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
  `asyncio.get_running_loop().create_task`). `session_start` is **idempotent
  per runtime generation**: new/resume/branch rebuild the session on the SAME
  runtime (`lifecycle.py:740`) and fire `session_shutdown(reason)` then
  `session_start(reason)` — an existing live supervisor is kept and only
  re-synced (no second supervisor, no duplicate registrations; the registry
  survives rebind and `compose_tools` already re-merges its tools into the
  fresh list, so no re-seed mechanism exists or is needed). Only
  `startup`/`reload` build a new supervisor. `session_shutdown(quit|reload)`
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

## Implementation preflight findings

Recorded 2026-11-08, executing Task 0 of `plans/mcp-client-implementation.md`
on `feat/mcp-client`. Every planned MUST-HOLD was re-verified against the
working tree (line numbers below are today's, not the plan's).

### Tool-materialization chain (MUST-HOLD — holds)

1. `session.py:818` materializes once:
   `tools = _filter_tools(extension_runtime.compose_tools(base_tools), config.allowed_tool_names)`;
   `base_tools` is `config.tools` or fresh coding tools (`session.py:808-817`).
2. The same local `tools` goes to `build_system_prompt(tools=tools)`
   (`session.py:825`) and `AgentHarnessConfig(tools=tools)` (`session.py:852`).
3. `AgentHarnessConfig` is `@dataclass(slots=True)`, **not frozen**:
   `tools: list[AgentTool] = field(default_factory=list)` (`harness.py:66-71`).
   Field assignment is an established pattern — the subagents isolated-child
   narrowing writes `session._harness.config.tools = [...]`
   (`extensions/builtins/subagents/extension.py:761-763`).
4. `_run` reads `tools=self._config.tools` (`harness.py:356`) and
   `system=self._config.system` (`harness.py:352`) per run.

### Child sessions (MUST-HOLD for the gate — flag required)

Subagent children construct via `CodingSession.load(CodingSessionConfig(...))`
without passing `extension_runtime` (`extensions/builtins/subagents/extension.py:695-743`)
— each child gets a **fresh** runtime, and built-ins load natively ("Children
load extensions natively (pi parity)", `extension.py:731-737`;
`extensions_enabled=not run.requested_isolated`, `:737`). Therefore the gate is
a real flag: `CodingSessionConfig.mcp_enabled: bool = True`, and the child
construction passes `mcp_enabled=False`. Isolated children additionally narrow
`config.tools` to core names post-load (`extension.py:753-763`).

### Rebind lifecycle matrix (MUST-HOLD for the guard — CORRECTED during Task 6)

Initial verification read `lifecycle.py` correctly but missed what `load`
does with the runtime it is handed. `session.py:643-670` settles it: a
runtime is cwd-bound and may hold project registrations, so **`load` always
stages a fresh runtime** for the destination snapshot
("never reuse source-project code across replacement trust boundaries");
`config.extension_runtime` (`lifecycle.py:740`, `:899`) only carries
credentials/environment into the new generation.

| reason | runtime instance | evidence |
| --- | --- | --- |
| startup | fresh | session construction |
| reload | fresh staged runtime | shutdown old → bind staged → start staged (`lifecycle.py:446-451`); resources re-stored (`:459-474`) |
| new/resume/branch | **fresh runtime for the replacement** | old runtime `emit_session_shutdown` (`lifecycle.py:935`) → replacement's fresh runtime `emit_session_start` (`:937`) → `old_runtime.retire()` (`:946`); the fresh runtime re-binds to the surviving session facade (`:998`) |
| quit | same runtime | shutdown only |

Consequences for the extension: each extension **instance** (one per runtime
generation) receives `setup` fresh and boots its supervisor at most once per
generation; the outgoing generation's `session_shutdown` shuts its supervisor
down. The idempotent `session_start` guard stays as defense-in-depth, and the
registry re-populates naturally in the fresh generation (no re-seed).
Pre-existing issue recorded for a future issue, **not** fixed on this branch:
a rebind whose `config.tools` is non-empty re-wraps already-wrapped tools
(`lifecycle.py:716` passes the old list; `runtime.py:1046` wraps
unconditionally). Related caveat for the live-tool seam: the subagents
isolated-child narrowing REPLACES `session._harness.config.tools`
(`subagents/extension.py:761-763`), which detaches the list the runtime bound
during load; MCP children are gated off (`mcp_enabled=False`), so the MCP
extension never registers into a narrowed list, but a future live-list user
must re-bind after narrowing.

### Tool executor signature and input path (MUST-HOLD — holds)

`ToolExecutor` is `(tool_call_id, arguments, signal, on_update) ->
Awaitable[AgentToolResult]` (`baldric_protocol/tools.py:64-73`); `AgentTool.execute`
forwards all four (`:103-111`). Task 5's `on_update` → progress mapping stands.

Every turn enters through `CodingSession` `prompt()` — the single
`run_input_hooks` await is `session/runtime.py:335`, before expansion and run
(`:338-353`). Callers: print/JSON (`cli.py:1505`), RPC server
(`modes/rpc/server.py:124`), TUI (`tui/app.py:2509`, `:2530`), subagent child
runs (`subagents/extension.py:414`, `:772`), and the extension
`send_user_message` wrapper (`session.py:1839`). The first-turn MCP admission
wait therefore applies in every mode; no bypass exists and no known-limitation
note is needed.

### Prompt-builder closure (MUST-HOLD — holds)

`BuildSystemPromptOptions` (`context/system_prompt.py:54-68`) and
`build_system_prompt(options)` are pure (`:71-73`). Every input used at
`session.py:819-846` is either a `config` field, a session-stored resource
field (`session.py:865-872`), an `extension_runtime` property, or the local
`tools` list. Reload re-stores all of them (`lifecycle.py:459-474`).
`current_date` stays defaulted (`date.today()`), same as the reload rebuild. A
zero-arg closure built in the `load` scope can capture the session and local
`tools` — no unstable input, nothing extra to store before Task 6.

### Input-hook seam (MUST-HOLD — holds)

`run_input_hooks` is awaited before the run starts
(`session/runtime.py:335`); `handled` short-circuits the turn, otherwise
`content = input_outcome.text` (`:338-342`). The `input` hook payload is
`InputEvent(text, source, streaming_behavior)` with
`source: Literal["interactive", "extension"]`
(`extensions/api.py:484-502`).

### Resume repair and unknown tools (holds)

`_run` repairs dangling tool calls before the loop
(`harness.py:346-348` → `_append_interrupted_tool_results`, `:466-467`) by
appending `ToolResultMessage(text="Tool call interrupted by user",
is_error=True)` for every unanswered call id (`tool_history.py:17-44`). An
unknown tool name resolves via `tools.get(call.name)` and yields a synthesized
`error_result("Tool <name> not found")` that reaches the model as an error
tool result — it does not raise (`baldric_agent/tool_calls.py:64-67`). Task 9
pins this; the adapter-layer "tool unavailable" promise stays as specified.

### BoundSession protocol (verified)

`BoundSession` spans `extensions/runtime.py:115-189` (properties, then
mutators ending at `set_inference_provider`, `:189`); `bind` at `:803`;
`_session: BoundSession | None` at `:312`. `refresh_system_prompt() -> None`
does not exist yet and will be added to the protocol and to `CodingSession`.

### Corrections to the plan

- The lifecycle matrix's `branch` row describes behavior that does not exist
  yet (accepted by the adopt literal, never called). No design change: the
  idempotent guard covers the future implementation regardless.
- The plan's "if a mode bypasses the hook, record as known limitation"
  contingency resolved to "no mode bypasses it" — nothing to document.

### SDK API pin-down (installed `mcp` 1.30.0, Task 1 Step 4)

Recorded so Tasks 3-5 argue from facts, not the plan's assumptions. The HTTP
transport difference triggered the plan's STOP RULE; the plan was amended and
committed before any Task 3 code.

1. **stdio** (`mcp/client/stdio/__init__.py`): `StdioServerParameters(command,
   args=[], env=None, cwd=None, encoding="utf-8", encoding_error_handler="strict")`
   — `cwd` EXISTS (`:86`). `stdio_client(server, errlog: TextIO = sys.stderr)`
   yields `(read_stream, write_stream)` (`:189`). Env semantics (`:127`):
   `{**get_default_environment(), **server.env}` when env is passed — merged
   over the SDK's safe-inherited defaults, passed env wins. Windows command
   resolution is built in (`get_windows_executable_command`,
   `mcp/os/win32/utilities.py:36-65`, `shutil.which` + `.cmd/.bat/.exe/.ps1`
   probing) and runs automatically inside `stdio_client` (`:229-230`) — the
   plan's own `_resolve_windows_command` was redundant and is dropped.
   Shutdown is built into the context manager (close stdin → wait 2s →
   terminate process tree; Windows uses a kill-on-close Job Object).
2. **HTTP** (`mcp/client/streamable_http.py`): `streamablehttp_client` is
   DEPRECATED (`:709-711`). Use
   `streamable_http_client(url, *, http_client=None, terminate_on_close=True)`;
   headers/timeouts/auth go on the httpx client via
   `create_mcp_http_client(headers=..., timeout=...)` passed as `http_client`.
   Yields `(read_stream, write_stream, get_session_id)` (`:695-699`).
3. **ClientSession** (`mcp/client/session.py`): `ClientSession(read_stream,
   write_stream, read_timeout_seconds: timedelta | None = None,
   sampling_callback, elicitation_callback, list_roots_callback,
   logging_callback, message_handler, client_info, ...)` (`:122-136`).
   `initialize() -> InitializeResult` raises `RuntimeError` on unsupported
   protocol version (`:202-203`); `InitializeResult.instructions: str | None`
   exists (`types.py:698`). `list_tools() -> ListToolsResult` (`.tools`).
   `call_tool(name, arguments=None, read_timeout_seconds=None,
   progress_callback=None, *, meta=None) -> CallToolResult` (`:386-394`);
   `CallToolResult(content, isError, structuredContent)` (`types.py:1363-1367`).
   NOTE: `call_tool` may raise — output-schema validation on success results
   (`:412-413`, `RuntimeError` at `:435/:443/:448`) and an internal
   `list_tools` refresh (`:419-421`). The adapter catches exceptions per call.
4. **Progress**: `progress_callback` is invoked as
   `await callback(progress, total, message)` (positional triple), matched by
   the request's progress token (`mcp/shared/session.py:409-420`).
5. **HTTP 401**: the POST handler calls `response.raise_for_status()`
   (`streamable_http.py:381`), so a 401 during `initialize()` surfaces as
   `httpx.HTTPStatusError` (`.response.status_code == 401`), possibly wrapped
   in an anyio `ExceptionGroup` by the transport task group. `connect()`
   unwraps the group and maps 401 → `needs-auth`.
6. **Test helpers**: `mcp/shared/memory.py` provides
   `create_client_server_memory_streams()` (yields `(client_streams,
   server_streams)`) and `create_connected_server_and_client_session(server:
   Server | FastMCP, read_timeout_seconds=..., ...) -> AsyncGenerator[ClientSession]`
   (yields an initialized session; FastMCP unwrapped via `_mcp_server`).
   **FastMCP** (`mcp/server/fastmcp/server.py`): `FastMCP(name)` (`:157`),
   `@mcp.tool()` (`:462`), `mcp.run(transport="stdio")` is synchronous and
   defaults to stdio (`:295-312`).
