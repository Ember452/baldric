# MCP Client Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to
> implement this plan task-by-task (inline execution; the project owner has
> asked not to use subagents). Steps use checkbox (`- [ ]`) syntax for tracking.
> This plan encodes verified hypotheses, not guarantees — the **Execution
> Rules** section below is binding on every task and outranks convenience.

**Goal:** Give Baldric an MCP client — configured servers' tools become ordinary
agent tools — as `baldric_mcp` (new top-level package) plus a thin built-in
extension, protocol delegated to the official `mcp` Python SDK.

**Architecture:** `baldric_coding/extensions/builtins/mcp → baldric_mcp →
baldric_protocol`. The agent core never learns MCP exists; MCP tools enter
through the extension API. Connection supervision follows pi's state machine
(`connecting/connected/disconnected/needs-auth/failed/closed`, lazy reconnect on
drop). Dynamic tool visibility rides two small verified seams: the harness reads
`config.tools` per run, and the system prompt is rebuilt via
`refresh_system_prompt()`.

**Tech Stack:** Python 3.12, anyio, pydantic, official `mcp` SDK (stable 1.x),
pytest + anyio plugin, ruff + mypy strict.

**Spec:** `dev-notes/design/mcp-client-support.md` (v2). This plan argues from
the spec; executors read both. Where the spec and this plan disagree, stop and
reconcile before coding.

## Global Constraints

- Repo root for all commands: `D:\DEVELOP\Solis\baldric`. Run everything through
  `uv run` (house rule).
- Python `>=3.12`; mypy `strict`; ruff `line-length=110`, quotes double, rules
  `E,F,I,UP,B,SIM`; coverage floor 80%.
- Import direction: `baldric_coding → baldric_mcp → baldric_protocol`.
  `baldric_mcp` must not import `baldric_agent`, `baldric_ai`,
  `baldric_coding`, `textual`, or `rich`; `baldric_agent`/`baldric_ai` must not
  import `baldric_mcp`. Enforced by `scripts/check_import_graph.py` and
  `tests/guards/test_import_boundaries.py`.
- No Textual/Rich imports anywhere under `src/baldric_mcp/`.
- Tool names are frozen at 1.0: `mcp__<server>__<tool>`, sanitized to
  `[A-Za-z0-9_]`, ≤ 64 chars, sha256-8 suffix on overflow/collision.
- Config: top-level `mcpServers` key (pi/Claude Desktop compatible); project
  file `.baldric/mcp.json` loads only when the project is trusted.
- Truncation: model-facing text cap 20 KiB, keep start+end, full text saved to
  a file whose path the note carries (pi's rule).
- Known Windows limitations are not yours to fix: 14 mypy errors on
  POSIX-only modules, ~121 skipped tests, flaky TUI tests. Do not add platform
  shims elsewhere to "fix" them.
- Ratchets: `# type: ignore`/`# noqa` counts may only shrink; structure-gate
  growth is recorded with `--init`, never by weakening baselines.
- Every task below starts with a **Verify** step. The Verify step is mandatory:
  read the named code before writing anything. If a fact marked
  **MUST-HOLD** does not hold, STOP, update the spec/plan, and re-review — do
  not improvise (project owner's hard rule: 严禁没有想清楚就动手). This is the
  floor, not the ceiling: the **Execution Rules** section below extends it to
  every action.
- Editing rule (house rule): use editor tools only; never bulk-rewrite files
  with scripts/sed.
- Quality gate per task: `uv run ruff check . && uv run ruff format --check .`
  on touched files, `uv run mypy`, and the fast suite
  `uv run pytest -q --ignore=tests/coding/tui` before each commit.
- Async tests use the house pattern: module-level
  `pytestmark = pytest.mark.anyio` plus an `anyio_backend()` fixture returning
  `"asyncio"` (see `tests/coding/extensions/test_extensions.py:55-59`).
- Commits are atomic per task with explicit paths (`git add <path>...`), no
  `git add -A`.

## Execution Rules (owner mandate, binding)

The project owner set these rules on 2026-11-08. They apply to every task,
step, fix, and deviation in this plan and outrank convenience.

### R1 — The plan is a hypothesis; re-verify before every action

Every path, line number, signature, and behavior claim in this plan was
verified once, when the plan was written. It is not guaranteed to still hold:
the working tree moves, and the plan itself can simply be wrong.

- Before starting each task — and again before any step that touches code —
  re-open the named files and confirm the facts that step depends on. Grep the
  surrounding area for drift (new callers, renamed symbols, changed
  signatures) instead of navigating from the plan's line numbers or memory.
- If reality disagrees with the plan, the plan loses. STOP, reconcile the
  plan/spec first, then continue. 严禁没有想清楚就动手.

### R2 — Full impact surface before touching anything (看全面)

Before modifying any existing file — even one line — enumerate its impact
surface and record it in the task notes or commit message:

- Both directions: who calls/imports the symbol, and what it calls/imports —
  grep across `src/`, `tests/`, `scripts/`, `website/`.
- Which tests and guards (`tests/guards/`, ratchet baselines) pin the current
  behavior and would catch a change.
- Downstream consumers of the behavior: TUI, print mode, RPC, commands,
  session files/resume, docs.
- What the pi reference tree does at the same seam (see R3).

A change without an enumerated surface does not get made. If the surface turns
out bigger than the plan assumed, that is a plan defect: go back to R1.

### R3 — Consult pi for important problems, bugs, and designs

Whenever an important problem, a bug, or a design decision comes up — not only
the ones this plan anticipates — check how pi solves the same thing before
inventing a solution. The pi tree lives at `D:\DEVELOP\Solis\pi-main`; the MCP
code is under `pi-main/packages/mcp/` and
`pi-main/packages/coding-agent/src/extensions/mcp/`. Record what pi does and
why, then adapt it to Baldric's architecture — port the judgment, not
necessarily the code. If pi has no equivalent, say so in the notes and reason
from first principles.

### R4 — Deviations are allowed, but never silent

Genuinely necessary work beyond this plan — including changes to existing code
outside the spec's touchpoint table — is permitted. Every deviation must:

1. State why the plan as written is wrong or insufficient — one concrete fact
   from R1/R2, not a preference.
2. Carry the full impact-surface analysis from R2.
3. Meet the quality bar in R5; a deviation never licenses a looser design.
4. Be appended to **Execution deviations log** at the end of this file and
   flagged in the commit message with a `deviation:` note.
5. If it changes the *design* (not just the implementation route), surface it
   to the owner before continuing.

### R5 — Quality bar: high cohesion, low coupling, maintainable

- `baldric_mcp` stays self-contained: config, connection, supervision, and
  adaptation each live in their own module; the extension layer in
  `baldric_coding` remains thin glue over them.
- Every seam added to the agent core (`bind_live_tools`,
  `refresh_system_prompt`, `unregister_tool`) must be a generic capability
  with a generic name — no MCP-specific semantics leak into core. If a seam
  cannot be stated generically, the design is wrong: back to R1.
- Match the house style of each file touched; new modules follow existing
  package conventions (pydantic models, explicit async boundaries, typed
  dataclasses).
- A senior engineer reading the final diff should find nothing overcomplicated
  and nothing clever for its own sake.

---

### Task 0: Preflight impact-surface verification (read-only, no code)

**Files:** none created. Findings are recorded as a short appended section in
`dev-notes/design/mcp-client-support.md` ("Implementation preflight findings"),
committed separately.

**Interfaces:**
- Produces: confirmed facts (or spec corrections) every later task depends on.

- [x] **Step 1: Verify the tool-materialization chain (MUST-HOLD)**

Read `src/baldric_coding/session/session.py:805-870` and
`src/baldric_agent/harness.py:55-90, 336-370`. Confirm:

1. `tools = _filter_tools(extension_runtime.compose_tools(base_tools), config.allowed_tool_names)`
   materializes one list at session construction (`session.py:818`).
2. The same list object is handed to `AgentHarnessConfig(tools=tools)` and to
   `build_system_prompt(tools=tools)`.
3. `AgentHarnessConfig` is `@dataclass(slots=True)` with
   `tools: list[AgentTool]` (`harness.py:66-71`) — not frozen, so fields are
   assignable.
4. `run_agent_loop(..., tools=self._config.tools, ...)` reads the field per run
   (`harness.py:356`), and `system=self._config.system` likewise (`:352`).

If any point fails, STOP: the live-seam design is wrong and the spec must be
revised before any code.

- [x] **Step 2: Verify child sessions and the extension runtime (MUST-HOLD for Task 7's gate)**

Read `src/baldric_coding/extensions/runtime.py:1034-1080` (`compose_tools`),
`src/baldric_coding/session/provider_helpers.py:252` (`_filter_tools`), and
grep `src/baldric_coding/extensions/builtins/subagents/` for child-session
construction (`CodingSession` / `CodingSessionConfig(` usage). Determine:

- Do subagent child sessions run the same `CodingSession.load` path and load
  built-in extensions?
- If YES: Task 7's gate must be a real flag. Record the exact construction
  site; Task 6 adds `CodingSessionConfig.mcp_enabled: bool = True` and the
  subagents child construction passes `mcp_enabled=False`.
- If NO: the gate is a documented function returning `True` (no flag — YAGNI),
  and Task 6's config-field change is dropped.

Record the outcome and the exact file:line evidence.

- [x] **Step 2b: Verify the rebind lifecycle matrix (MUST-HOLD for Task 7's guard)**

Read `src/baldric_coding/session/lifecycle.py:440-455` (reload: old runtime
shuts down, a NEW staged runtime starts) and `lifecycle.py:700-764` +
`lifecycle.py:925-940` (new/resume/branch: `type(session).load(...)` with
`extension_runtime=session._extension_runtime` at `:740`, then
`emit_session_shutdown(reason)` then `emit_session_start(reason)` on that SAME
runtime). Record the matrix:

| reason | runtime instance | shutdown fires | start fires |
| --- | --- | --- | --- |
| startup | fresh | no | yes |
| reload | fresh (staged) | yes (old) | yes (staged) |
| new/resume/branch | SAME as before | yes | yes |
| quit | same | yes | no |

**MUST-HOLD**: new/resume/branch reuse the runtime, so a naive
`session_start` handler would build a second supervisor. Task 7's handler must
be idempotent (existing live supervisor → re-sync only). Also verify and
record (read `runtime.py:1034-1060`) that `compose_tools` re-merges registry
tools into the rebuilt list on rebind — so the plan must NOT add any re-seed
mechanism. Separately record the pre-existing observation that rebind with
non-empty `config.tools` re-wraps already-wrapped tools (`lifecycle.py:716` +
`runtime.py:1046`) — this affects all extensions, is NOT fixed on this
branch; note it for a future issue.

- [x] **Step 2c: Verify the tool executor signature and the print/RPC input path**

1. Read `src/baldric_protocol/tools.py:64-111`: confirm `ToolExecutor` is
   `(tool_call_id, arguments, signal, on_update) -> Awaitable[AgentToolResult]`
   and `AgentTool.execute` forwards all four (Task 5's `on_update` mapping
   depends on this). **MUST-HOLD.**
2. Read how print mode (`-p`) and RPC mode reach their first prompt (grep
   `run_input_hooks` callers in `src/baldric_coding/`). Record whether the
   first-turn admission wait applies in every mode. If a mode bypasses the
   hook, record it as a known limitation in the docs task (the live seam
   still delivers tools on subsequent turns).

- [x] **Step 3: Verify the prompt-builder inputs (MUST-HOLD for `refresh_system_prompt`)**

Read `src/baldric_coding/context/system_prompt.py:55-90`
(`BuildSystemPromptOptions`, `build_system_prompt`) and
`src/baldric_coding/session/lifecycle.py:420-480` (the reload path that
re-stores `resources.*` fields). Confirm every `BuildSystemPromptOptions` input
used at `session.py:819-846` is capturable in a zero-arg closure built in the
same scope (`config.*`, `resources.*`, `extension_runtime.*`, local `tools`).
List any input that is NOT stable in that scope; such an input must be stored
on the session before Task 6 relies on the closure.

- [x] **Step 4: Verify the input-hook seam (MUST-HOLD for first-turn admission)**

Read `src/baldric_coding/session/runtime.py:320-345`. Confirm
`run_input_hooks` is awaited before the run starts and that returning `None`
continues unchanged. Confirm the `input` hook receives
`InputEvent(source=...)` (`extensions/api.py:484-502`).

- [x] **Step 5: Verify the resume/repair and unknown-tool behavior**

Read `src/baldric_agent/harness.py:336-356` (prelude
`_append_interrupted_tool_results`) and `src/baldric_agent/tool_history.py`.
Then read the tool resolution in `src/baldric_agent/loop.py` (grep
`tool_calls`/lookup by name): record what happens when the model calls a name
that is not in `tools` (expected: a synthesized error result reaches the model;
note the exact mechanism). If unknown tools raise instead, record that — Task 9
pins whichever behavior exists, and the spec's "tool unavailable" promise is
implemented at the adapter layer (a withdrawn MCP tool stays registered with an
error executor) rather than relying on loop behavior.

- [x] **Step 6: Verify BoundSession protocol surface**

Read `src/baldric_coding/extensions/runtime.py` for `class BoundSession` and
`bind`. Confirm where to add `refresh_system_prompt() -> None` to the protocol
and that `runtime._session` is the bound session (used by
`request_system_prompt_refresh` in Task 6).

- [x] **Step 7: Commit the findings**

Append a "## Implementation preflight findings" section to
`dev-notes/design/mcp-client-support.md` with each fact and file:line. Commit:

```bash
git add dev-notes/design/mcp-client-support.md
git commit -m "docs: record MCP implementation preflight findings"
```

---

### Task 1: Dependency, package scaffold, import guards, SDK pin-down

**Files:**
- Modify: `pyproject.toml` (dependencies, wheel packages, mypy packages)
- Modify: `scripts/check_import_graph.py` (RULES)
- Modify: `tests/guards/test_import_boundaries.py` (same rules)
- Create: `src/baldric_mcp/__init__.py`
- Create: `tests/mcp/__init__.py`, `tests/mcp/test_import_direction.py`

**Interfaces:**
- Produces: importable empty package `baldric_mcp`; CI guards that lock its
  layer position; the pinned SDK API contract used by Tasks 3-5.

- [x] **Step 1: Add the dependency and package registrations**

In `pyproject.toml`: add `"mcp>=1.0,<2"` to `dependencies` (the aliyun index
serves it); extend
`[tool.hatch.build.targets.wheel] packages = [..., "src/baldric_mcp"]` and
`[tool.mypy] packages = [..., "baldric_mcp"]`. Then `uv sync` and record the
installed version:

```bash
uv sync
uv run python -c "import importlib.metadata as m; print(m.version('mcp'))"
```

- [x] **Step 2: Lock the layer in the import graph**

In `scripts/check_import_graph.py` RULES add:
`("baldric_mcp", "baldric_agent")`, `("baldric_mcp", "baldric_ai")`,
`("baldric_mcp", "baldric_coding")`, `("baldric_mcp", "textual")`,
`("baldric_mcp", "rich")`, `("baldric_agent", "baldric_mcp")`,
`("baldric_ai", "baldric_mcp")`. Mirror exactly the same seven entries in
`tests/guards/test_import_boundaries.py` wherever it mirrors RULES (read the
file first; it imports `scan_violations` and restates rules — keep the two in
sync).

- [x] **Step 3: Create the package shell**

`src/baldric_mcp/__init__.py`:

```python
"""MCP client core: configuration, connection supervision, tool adaptation.

Protocol work is delegated to the official `mcp` SDK; this package holds only
Baldric's product layer. It must not import `baldric_agent`, `baldric_ai`, or
`baldric_coding` (see scripts/check_import_graph.py).
"""

__all__: list[str] = []
```

`tests/mcp/test_import_direction.py`: a test asserting
`importlib.import_module("baldric_mcp")` succeeds. The import-graph guard
(Task 1 Step 2) is the enforcement layer; no `__dict__` introspection here —
it would be unreliable.

- [x] **Step 4: SDK API pin-down (MUST-HOLD before Tasks 3-5)**

Read the INSTALLED SDK source under
`.venv/Lib/site-packages/mcp/` (read, don't guess) and record:

1. `mcp/client/stdio/__init__.py`: `stdio_client(server)` context-manager yield
   shape; `StdioServerParameters` fields (`command`, `args`, `env`, `cwd` —
   confirm whether `cwd` exists in the pinned version); env semantics — when
   `env` is passed, is it used verbatim or merged with
   `get_default_environment()`? Record the exact behavior; Tasks 3 passes the
   merged snapshot+config env explicitly either way.
2. `mcp/client/streamable_http/__init__.py`: `streamablehttp_client(url,
   headers=...)` yield shape.
3. `mcp/client/session/__init__.py`: `ClientSession` constructor params
   (`message_handler`? `read_timeout_seconds`?), `initialize()` result fields
   (`instructions`), `list_tools()`, `call_tool(name, arguments, ...)` signature
   and `CallToolResult` fields (`content`, `isError`, `structuredContent`),
   and how progress notifications surface (ServerNotification /
   ProgressNotification fields `progress`, `total`, `message`).
4. How an HTTP 401 surfaces during `initialize()` (exception type/attribute) —
   Task 3 maps it to `needs-auth`.
5. `mcp/shared/memory.py`: the in-memory connected client/server helper for
   tests (name and yield shape).
6. `mcp/server/fastmcp`: confirm `FastMCP(name)` + `@mcp.tool()` + `mcp.run()`
   runs a stdio server (used by Task 9's fixture).

**STOP RULE:** if any of 1-6 differs materially from the signatures used in
Tasks 3-5, adjust those tasks' code in this plan file first, commit the plan
change, then continue. Never adapt silently while coding.

- [x] **Step 5: Run gates and commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest -q tests/mcp tests/guards
git add pyproject.toml uv.lock scripts/check_import_graph.py tests/guards/test_import_boundaries.py src/baldric_mcp/__init__.py tests/mcp/__init__.py tests/mcp/test_import_direction.py
git commit -m "feat: add baldric_mcp package scaffold with mcp SDK dependency"
```

---

### Task 2: `baldric_mcp.config` — parsing, merge, expansion, write-back

**Files:**
- Create: `src/baldric_mcp/config.py`
- Modify: `src/baldric_coding/config/paths.py` (two properties)
- Create: `tests/mcp/test_config.py`
- Modify: `tests/mcp/test_import_direction.py` only if needed

**Interfaces:**
- Produces (consumed by Tasks 3/4/7/8):

```python
ServerType = Literal["stdio", "http"]

@dataclass(frozen=True, slots=True)
class McpServerConfig:
    name: str
    server_type: ServerType
    source: Path | None = None      # file that defined the effective entry
    enabled: bool = True
    description: str | None = None
    timeout: float = 60.0           # seconds, per call
    command: str | None = None      # stdio
    args: tuple[str, ...] = ()      # stdio
    env: Mapping[str, str] = field(default_factory=dict)   # stdio, expanded
    cwd: str | None = None          # stdio, ~-expanded
    url: str | None = None          # http
    headers: Mapping[str, str] = field(default_factory=dict)  # http, expanded

@dataclass(frozen=True, slots=True)
class McpConfigDiagnostic:
    path: str
    name: str            # server name, or "" for file-level problems
    message: str

@dataclass(frozen=True, slots=True)
class McpConfigLoadResult:
    servers: tuple[McpServerConfig, ...]
    diagnostics: tuple[McpConfigDiagnostic, ...]

def load_mcp_config(
    user_path: Path | None,
    project_path: Path | None,
    environment: Mapping[str, str],
) -> McpConfigLoadResult: ...

def set_server_enabled(path: Path, name: str, enabled: bool) -> None: ...
```

`paths.py` additions (follow the existing property style):

```python
@property
def user_mcp_config_path(self) -> Path:
    """Return the user-level MCP server config path."""
    return self.home / "mcp.json"

def project_mcp_config_path(self, cwd: Path) -> Path:
    """Return the project-local MCP server config path."""
    return self.project_baldric_dir(cwd) / "mcp.json"
```

- [x] **Step 1: Write failing tests (see test list below)**

Test cases in `tests/mcp/test_config.py` (each a small function; build JSON
files under `tmp_path`):

1. stdio entry parses: `command`/`args`/`env`/`cwd` → `server_type="stdio"`,
   defaults `enabled=True`, `timeout=60.0`.
2. http entry parses: `url`/`headers` → `server_type="http"`.
3. explicit `type` must match fields: `{"type": "http", "command": "x"}` →
   diagnostic, entry rejected; `{"type": "stdio", "command": "x"}` ok.
4. both `command` and `url` → diagnostic; neither (and not an override) →
   diagnostic.
5. unknown fields produce a warning diagnostic and the entry still loads.
6. `${VAR}` expansion in `env`/`headers`/`command` uses ONLY the injected
   environment; unresolvable `${MISSING}` → diagnostic and the entry loads with
   `enabled=False`.
7. `~` and `~/x` (and `~\x` semantics via the same helper) expand in
   `command`/`cwd`; plain paths untouched.
8. project entry with the same name replaces the user entry; `source` points at
   the project file.
9. project override entry (`{"enabled": false}` only, no command/url/type)
   merges onto the user entry, keeping its command/args; an override with any
   other key → diagnostic; an override with no user base → diagnostic.
10. namespace clash: user config defines `a-b` and `a_b` → both rejected with a
    diagnostic (`_namespace` collision).
11. malformed JSON / non-object file → file-level diagnostic, no raise.
12. `set_server_enabled(path, "x", False)` writes `"enabled": false` preserving
    existing indentation and unrelated top-level keys;
    `set_server_enabled(path, "x", True)` removes the key when the entry is a
    full entry, and writes `enabled: true` when the entry is an override.
    Round-trip: after write, `load_mcp_config` reflects the change.
13. disabled-in-file servers appear in `result.servers` with `enabled=False`
    (so `/mcp on` can find them).

- [x] **Step 2: Run and see them fail**

Run: `uv run pytest -q tests/mcp/test_config.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'baldric_mcp.config'`
(or import error of the names).

- [x] **Step 3: Implement `config.py`**

Implement to the interface above. Rules ported from pi
(`pi-main/packages/coding-agent/src/extensions/mcp/config.ts`,
`pi-main/packages/mcp/src/naming.ts`):

- Read with `Path.read_text(encoding="utf-8-sig")` (BOM-safe, pi's `stripBom`).
- Top level must be an object; `mcpServers` optional object; a top-level
  unknown key → warning diagnostic (forward compatibility).
- Namespace check: `f"mcp__{name.replace('-', '_')}"` — two servers sharing a
  namespace are both rejected.
- `${VAR}` expansion via regex `\$\{([A-Za-z_][A-Za-z0-9_]*)\}` against the
  injected `environment`; unresolvable → diagnostic + `enabled=False`.
- `~` expansion helper handles `~`, `~/…`, `~\…`.
- Project override = entry with no `command`/`url`/`type`; only `enabled` may
  appear; it merges via `dataclasses.replace(base, enabled=..., source=project_path)`.
- `set_server_enabled`: read → parse → locate entry → mutate → write back with
  the file's detected indent (`re.search(r"^([ \t]+)\S", text, re.M)` fallback
  `"  "`), preserving unrelated content and trailing newline (port pi's
  `editMcpServers`). `enabled=True` deletes the key for full entries, writes it
  for override entries.

- [x] **Step 4: Add the two `paths.py` properties (code in Interfaces above)**

- [x] **Step 5: Run tests, static gates, commit**

```bash
uv run pytest -q tests/mcp/test_config.py
uv run ruff check src/baldric_mcp src/baldric_coding/config/paths.py tests/mcp && uv run ruff format --check src/baldric_mcp src/baldric_coding/config/paths.py tests/mcp
uv run mypy
git add src/baldric_mcp/config.py src/baldric_coding/config/paths.py tests/mcp/test_config.py
git commit -m "feat: MCP server config parsing, merge, expansion, and write-back"
```

---

### Task 3: `baldric_mcp.client` — one supervised connection per server

**Files:**
- Create: `src/baldric_mcp/client.py`
- Create: `tests/mcp/test_client.py`

**Interfaces:**
- Consumes: `McpServerConfig` (Task 2); the SDK API pinned in Task 1 Step 4.
- Produces (consumed by Task 4/5/9):

```python
McpConnectionState = Literal[
    "connecting", "connected", "disconnected", "needs-auth", "failed", "closed"
]

@dataclass(frozen=True, slots=True)
class McpToolInfo:
    name: str
    description: str
    title: str | None
    input_schema: Mapping[str, JSONValue]

@dataclass(frozen=True, slots=True)
class McpContentBlock:
    text: str | None = None
    image_data: str | None = None    # base64 as sent by the server
    image_mime: str | None = None

@dataclass(frozen=True, slots=True)
class McpToolResultData:
    blocks: tuple[McpContentBlock, ...]
    is_error: bool

class McpTransport(Protocol):
    """Async context manager yielding (read_stream, write_stream)."""

class TransportFactory = Callable[[McpServerConfig, Mapping[str, str]], McpTransport]

def default_transport(config: McpServerConfig, environment: Mapping[str, str]) -> McpTransport: ...

class McpToolUnavailable(RuntimeError): ...

class McpServerConnection:
    def __init__(
        self,
        config: McpServerConfig,
        *,
        environment: Mapping[str, str],
        transport_factory: TransportFactory = default_transport,
        clock: Callable[[], float] = time.monotonic,
        retry_delays: Sequence[float] = (1.0, 3.0),
    ) -> None: ...
    @property
    def name(self) -> str: ...
    @property
    def state(self) -> McpConnectionState: ...
    @property
    def error(self) -> str | None: ...
    tools: tuple[McpToolInfo, ...]          # () until connected
    instructions: str | None                # from initialize()
    async def connect(self) -> bool         # True on connected; False on failed
    async def call_tool(
        self, tool: str, arguments: Mapping[str, JSONValue], *,
        on_progress: Callable[[str], None] | None = None,
    ) -> McpToolResultData                  # lazy reconnect when disconnected
    async def close(self) -> None
```

- [x] **Step 1: Write failing tests**

`tests/mcp/test_client.py` (house anyio pattern). Use a scripted fake
transport factory — an object with `__aenter__`/`__aexit__` yielding
`(fake_read, fake_write)` where a fake `ClientSession` is additionally
injectable: make the constructor accept
`session_factory: Callable[[Any, Any], Any] = _sdk_session_factory` so tests
inject a fake session with scripted `initialize()`, `list_tools()`,
`call_tool()` outcomes without the SDK at all. Cases:

1. successful connect: state `connected`, `tools` populated from
   `list_tools()`, `instructions` captured from `initialize()` result.
2. transient failure then success: first `initialize()` raises
   `TimeoutError`-ish → after retry delay the second attempt succeeds
   (inject `clock` advancing instantly and tiny `retry_delays=(0.0, 0.0)`);
   state `connected`; exactly 2 attempts made.
3. budget exhausted: all attempts raise transient → state `failed`,
   `connect()` returns False, `error` carries the last message.
4. non-transient failure (e.g. `ValueError`) → `failed` immediately, 1 attempt.
5. HTTP 401 → state `needs-auth`, no retry (fake raises the exception type
   pinned in Task 1 Step 4 item 4; if the SDK carries no status, the fake
   raises `McpNeedsAuthError` — define that sentinel in `client.py` and let
   `default_transport`'s error path raise it; Task 1 findings decide).
6. lazy reconnect: connected → drop (fake session's `call_tool` raises a
   connection-type error once) → state `disconnected`; next `call_tool`
   reconnects (session_factory records a second connect) and returns the
   result.
7. call while `failed`/`needs-auth`/`closed` → `McpToolUnavailable`.
8. call timeout: fake `call_tool` sleeps; config `timeout=0.05`; watchdog
   cancels; result is `McpToolUnavailable` with a timeout message; state stays
   `connected` (timeout is per-call, not a connection fault).
9. progress: fake session emits progress via the pinned mechanism →
   `on_progress` receives text and the deadline resets (fake clock: first
   progress moves the deadline; watchdog uses injected `clock`).
10. result mapping: text block → `McpContentBlock(text=...)`; image block →
    `image_data`/`image_mime`; empty content + `structuredContent` → one text
    block of JSON; `isError=True` → `is_error=True`.
11. `close()` → state `closed`; exits transport context (fake records exit).
12. (dropped — the pinned SDK resolves Windows `.cmd`/`.bat`/`.exe` shims
    itself via `get_windows_executable_command` inside `stdio_client`; the
    planned `_resolve_windows_command` helper was redundant and is removed.
    The stdio factory test instead asserts `config.command` reaches
    `StdioServerParameters` verbatim.)

- [x] **Step 2: Run and see them fail**

Run: `uv run pytest -q tests/mcp/test_client.py`
Expected: FAIL (module missing).

- [x] **Step 3: Implement `client.py`**

Key implementation decisions (port from pi's
`packages/coding-agent/src/extensions/mcp/runtime.ts` where noted):

- Transport lifetime via `contextlib.AsyncExitStack`: on connect,
  `stack.enter_async_context(transport_factory(...))` then
  `stack.enter_async_context(ClientSession(read, write, ...))`, then
  `await session.initialize()`. On `close()`/failure teardown:
  `await stack.aclose()` (never raises into the caller).
- Initial connect retries: attempts = `1 + len(retry_delays)`; retry ONLY
  transient errors (pi's `isTransientError`: HTTP 408/429/5xx-except-501 and
  connection-type exceptions — map to the SDK's actual exception types from
  Task 1 findings; 401 → `needs-auth` with no retry). Between attempts
  `await anyio.sleep(delay)`.
- Per-call deadline watchdog (progress resets it):

```python
async def _call_with_deadline(self, coro_factory, on_progress):
    box: dict[str, object] = {}
    deadline = self._clock() + self._config.timeout
    with anyio.CancelScope() as scope:
        async def watchdog() -> None:
            while True:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    scope.cancel()
                    return
                await anyio.sleep(min(remaining, 0.25))
        async def run() -> None:
            box["result"] = await coro_factory()
        async with anyio.create_task_group() as tg:
            tg.start_soon(watchdog)
            tg.start_soon(run)
    if "result" not in box:
        raise McpToolUnavailable(f"MCP tool call timed out after {self._config.timeout:g}s")
    return box["result"]
```

Progress notifications arrive through `call_tool`'s `progress_callback`
(SDK 1.30.0: `await callback(progress, total, message)`, matched by the
request's progress token — `mcp/shared/session.py:409-420`): map it to
`on_update` and push the deadline out — share the deadline via a small
mutable holder both the callback and watchdog close over. Hardening notes:
`box["result"]` needs an explicit `cast(object, ...)`-style narrowing under
mypy strict; after a timeout the SDK may still deliver the late response — it
is dropped by the request id and is benign; leave a one-line comment saying
so at the cancel site so a future reader does not "fix" it. `call_tool` can
also raise (output-schema validation, internal `list_tools` refresh): the
executor catches exceptions per call and converts them to the error result
(Task 5's fallback text).

- Lazy reconnect (pi's `disconnected` semantics): `call_tool` when
  `self._state == "disconnected"` performs one `connect()`; on failure raises
  `McpToolUnavailable(self._error or ...)`.
- `default_transport`: http →
  `streamable_http_client(config.url, http_client=create_mcp_http_client(headers=dict(config.headers)))`
  (SDK 1.30.0 renamed `streamablehttp_client` → `streamable_http_client` and
  moved headers/timeouts onto the httpx client; the old name is deprecated —
  use the new one; the yield is `(read_stream, write_stream, get_session_id)`);
  stdio → pass `config.command` verbatim (the SDK resolves Windows shims
  itself — see test 12), then
  `stdio_client(StdioServerParameters(command=..., args=list(config.args),
  env={**environment, **config.env}, cwd=config.cwd))` (`cwd` exists in the
  pinned SDK; the SDK merges the passed env over `get_default_environment()`,
  and the full snapshot supersedes those defaults; yield is
  `(read_stream, write_stream)`).
- Stderr capture: the SDK seam is `stdio_client(server, errlog=<TextIO>)` —
  the constructor kwarg is `stderr_sink: TextIO | None = None` (Task 10 opens
  the log file and passes it). HTTP transports have no stderr.
- HTTP 401 during `initialize()` surfaces as `httpx.HTTPStatusError`
  (`response.raise_for_status()` in the POST handler, `streamable_http.py:381`),
  possibly wrapped in an anyio `ExceptionGroup`; `connect()` unwraps the group
  and maps status 401 to `needs-auth`.

- [x] **Step 4: Run tests, gates, commit**

```bash
uv run pytest -q tests/mcp/test_client.py
uv run ruff check src/baldric_mcp && uv run ruff format --check src/baldric_mcp && uv run mypy
git add src/baldric_mcp/client.py tests/mcp/test_client.py
git commit -m "feat: supervised MCP server connection with lazy reconnect"
```

---

### Task 4: `baldric_mcp.supervisor` — ownership of all connections

**Files:**
- Create: `src/baldric_mcp/supervisor.py`
- Create: `tests/mcp/test_supervisor.py`

**Interfaces:**
- Consumes: `McpServerConnection` (Task 3), `McpServerConfig` (Task 2).
- Produces (consumed by Task 7/8):

```python
@dataclass(frozen=True, slots=True)
class McpServerStatus:
    name: str
    state: McpConnectionState
    tool_count: int
    error: str | None

class McpSupervisor:
    def __init__(
        self,
        configs: Sequence[McpServerConfig],
        *,
        environment: Mapping[str, str],
        connection_factory: Callable[[McpServerConfig], McpServerConnection] | None = None,
        wait_ready_cap: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None: ...
    def statuses(self) -> tuple[McpServerStatus, ...]
    def any_connecting(self) -> bool
    def tool_names(self, server: str) -> tuple[McpToolInfo, ...]   # () when absent
    def instructions(self, server: str) -> str | None
    def on_change(self, callback: Callable[[], None]) -> None      # last wins
    async def start(self) -> None        # connect all enabled servers concurrently
    async def wait_ready(self, timeout: float = 10.0) -> None   # capped by wait_ready_cap
    async def call_tool(self, server: str, tool: str, arguments: Mapping[str, JSONValue], *, on_progress: Callable[[str], None] | None = None) -> McpToolResultData
    async def restart(self, name: str, config: McpServerConfig) -> None   # close old, connect new
    async def set_enabled(self, name: str, enabled: bool, config: McpServerConfig | None) -> None
    async def shutdown(self) -> None
```

The supervisor never reads config files or paths (low coupling): `restart` and
`set_enabled(..., config)` receive re-read configs from the extension layer.

- [ ] **Step 1: Write failing tests** (`tests/mcp/test_supervisor.py`, fake
  connections only — no SDK): start connects all enabled concurrently and
  ignores disabled; `wait_ready` returns promptly when nothing is connecting
  and caps at `wait_ready_cap` when a connection stays `connecting` (injected
  clock); `on_change` fires on connect success/failure/set_enabled/restart;
  `call_tool` routes to the right connection and raises `McpToolUnavailable`
  for unknown server/tool or disabled server; `set_enabled(False)` closes the
  connection and its tools vanish from `statuses()`; `set_enabled(True,
  config)` connects with the provided config; `restart` replaces the
  connection; `shutdown` closes all and further `call_tool` raises.
- [ ] **Step 2: Run and see them fail.**
- [ ] **Step 3: Implement.** Connections created through `connection_factory`
  (default builds real `McpServerConnection` with the constructor's
  environment). `start` uses `anyio.create_task_group` connecting each enabled
  server concurrently; per-connection failures are recorded in the connection
  itself (`failed`/`needs-auth` state), never raised out of `start`.
  `wait_ready`: `deadline = min(timeout, self._wait_ready_cap)`; poll
  `anyio.sleep(0.05)` until `not any_connecting()` or deadline passes — never
  raises. `on_change` fires (synchronously) after any state-affecting
  operation.
- [ ] **Step 4: Run tests, gates, commit**

```bash
uv run pytest -q tests/mcp/test_supervisor.py
uv run ruff check src/baldric_mcp && uv run ruff format --check src/baldric_mcp && uv run mypy
git add src/baldric_mcp/supervisor.py tests/mcp/test_supervisor.py
git commit -m "feat: MCP connection supervisor with bounded first-turn wait"
```

---

### Task 5: `baldric_mcp.adapter` — naming, schema, result conversion

**Files:**
- Create: `src/baldric_mcp/adapter.py`
- Create: `tests/mcp/test_adapter.py`

**Interfaces:**
- Consumes: `McpToolInfo`, `McpToolResultData` (Task 3), `AgentTool`/
  `AgentToolResult`/`TextContent`/`ImageContent` (`baldric_protocol.tools`,
  `baldric_protocol.messages`).
- Produces (consumed by Task 7):

```python
TOOL_NAME_MAX = 64
TEXT_LIMIT = 20 * 1024

def create_mcp_tool_name(
    server: str, tool: str, is_taken: Callable[[str], bool] = lambda _name: False
) -> str: ...

def normalize_input_schema(schema: Mapping[str, JSONValue] | None) -> dict[str, JSONValue]: ...

OutputSaver = Callable[[str, str], str]   # (full_text, suffix) -> saved file path

McpToolCaller = Callable[..., Awaitable[McpToolResultData]]
# call signature: await call(arguments, on_progress=...) -> McpToolResultData

def mcp_tool_to_agent_tool(
    server: str,
    info: McpToolInfo,
    call: McpToolCaller,
    *,
    output_saver: OutputSaver | None = None,
) -> AgentTool: ...

def convert_result(
    server: str, tool: str, data: McpToolResultData, *, output_saver: OutputSaver | None = None
) -> AgentToolResult: ...
```

- [ ] **Step 1: Write failing tests.** Naming table tests (port pi's
  `naming.ts` exactly — `tests` assert: plain case `mcp__docs__search`;
  sanitization `mcp__my_server__do_thing` for `my-server`/`do.thing`; 64-char
  cap with `_` + 8-hex sha256 suffix over `server\0tool`; collision of
  `a-b`/`a_b` tools within one server). Schema tests (missing/`{}`/non-object
  schema → `{"type": "object", "properties": {}}`; object with properties kept;
  non-dict schema → same empty-object fallback). Conversion tests: text join;
  image → placeholder text `[image: image/png, N bytes]` (MVP — the loop's
  provider serialization of tool-result images is unverified); `isError` →
  `is_error=True`; empty error content gains `"MCP tool <server>/<tool>
  returned an error"`; >20 KiB text with a fake saver → full text saved (path
  in the note), kept start+end; >20 KiB without saver → cut with note, no
  crash. `AgentTool` shape: `name` via `create_mcp_tool_name`, `label =
  f"{server}/{info.name}"`, description fallback chain
  `description.strip() or title or f"MCP tool {info.name} from server
  {server}"`, `parameters=normalize_input_schema(...)`, executor maps
  `on_progress` → `on_update(AgentToolResult(content=[TextContent(text=...)]))`
  and accepts `signal` without using it (docstring: per-call timeout lives in
  the connection).
- [ ] **Step 2: Run and see them fail.**
- [ ] **Step 3: Implement** — `create_mcp_tool_name` is a line-by-line port of
  `pi-main/packages/mcp/src/naming.ts` (`str.replace` → `re.sub(r"[^A-Za-z0-9_]",
  "_", name)`, `hashlib.sha256(f"{server}\0{tool}".encode()).hexdigest()[:8]`).
  `convert_result` joins text blocks, replaces image blocks with placeholders,
  applies the 20 KiB cut (keep start and end halves) and calls `output_saver`
  when provided.
- [ ] **Step 4: Run tests, gates, commit**

```bash
uv run pytest -q tests/mcp/test_adapter.py
uv run ruff check src/baldric_mcp && uv run ruff format --check src/baldric_mcp && uv run mypy
git add src/baldric_mcp/adapter.py tests/mcp/test_adapter.py
git commit -m "feat: MCP tool adapter with ecosystem tool naming and result conversion"
```

---

### Task 6: Agent seams — live tool list, unregister, prompt refresh

**Files:**
- Modify: `src/baldric_agent/harness.py` (`update_system_prompt`)
- Modify: `src/baldric_coding/extensions/runtime.py` (`bind_live_tools`,
  `unregister_tool`, `request_system_prompt_refresh`)
- Modify: `src/baldric_coding/extensions/api.py` (`unregister_tool`,
  `refresh_system_prompt`)
- Modify: `src/baldric_coding/session/session.py` (bind + builder closure +
  `refresh_system_prompt`)
- Modify: `src/baldric_coding/session/lifecycle.py` only if Task 0 Step 3 found
  a prompt input not retained across reload
- Create: `tests/agent/test_harness_system_prompt.py`
- Create: `tests/coding/extensions/test_live_tools.py`
- Create: `tests/coding/session/test_refresh_system_prompt.py` (place beside
  existing session tests — verify the directory first, adjust the path)

**Interfaces:**
- Consumes: verified chain from Task 0 Steps 1/3/6.
- Produces (consumed by Task 7/8):

```python
# harness.py
class AgentHarness:
    def update_system_prompt(self, system: str) -> None:
        """Replace the system prompt for subsequent runs (per-run read contract)."""

# runtime.py
class ExtensionRuntime:
    def bind_live_tools(self, tools: list[AgentTool], allowed: frozenset[str] | None) -> None: ...
    def request_system_prompt_refresh(self) -> None: ...
    # register_tool/unregister_tool now also mutate the bound live list

# api.py
class ExtensionAPI:
    def unregister_tool(self, name: str) -> None: ...       # source-owned removal
    def refresh_system_prompt(self) -> None: ...            # delegates to bound session

# session.py
class CodingSession:
    def refresh_system_prompt(self) -> None: ...
```

- [ ] **Step 1: Verify (from Task 0 findings) and restate the touchpoints**

Read the exact regions again with the editor open: `session.py:805-870`,
`runtime.py:1034-1080` + `register_tool` (`:544-563`) + `BoundSession`,
`api.py:1172-1180` (`register_tool`). Confirm the Task 0 preflight findings
still hold on this branch (they were verified on `main`; a merge may have
moved lines). **MUST-HOLD**: same list object flows to harness and
`build_system_prompt`.

- [ ] **Step 2: Write failing tests**

1. `tests/agent/test_harness_system_prompt.py`: with the existing fake
   provider helpers in `tests/agent/` (read them first), assert that a run
   after `harness.update_system_prompt("NEW")` sends `NEW` as the system
   prompt, and the previous prompt before.
2. `tests/coding/extensions/test_live_tools.py`: build a runtime (pattern from
   `tests/coding/extensions/test_extensions.py`), bind a list, register a tool
   via `ExtensionAPI.register_tool` → the bound list grows by that object;
   `unregister_tool` removes it; registering a name outside `allowed`
   (when `allowed` is not None) is ignored with a diagnostic; registering a
   duplicate name does not double-add.
3. `tests/coding/session/test_refresh_system_prompt.py`: construct a session
   (pattern from existing session tests — fake provider), capture the system
   prompt the fake provider received; register a prompt section via the
   extension API, call `session.refresh_system_prompt()`; next run's system
   prompt contains the section. Also: a session built with an explicit
   `config.system` has `refresh_system_prompt()` as a no-op.

- [ ] **Step 3: Run and see them fail.**

- [ ] **Step 4: Implement.**

`harness.py`:

```python
def update_system_prompt(self, system: str) -> None:
    """Replace the system prompt used by subsequent runs.

    The run path reads ``config.system`` per run, so the next prompt picks
    this up without touching the durable history.
    """
    if not system:
        raise ValueError("system prompt must be a non-empty string")
    self._config.system = system
```

`runtime.py` — fields `self._live_tools: list[AgentTool] | None = None` and
`self._live_allowed: frozenset[str] | None = None`:

```python
def bind_live_tools(self, tools: list[AgentTool], allowed: frozenset[str] | None) -> None:
    """Bind the session's materialized tool list for live registration.

    The bound object is the same list handed to the agent harness, which
    reads it per run; register/unregister keep registry and list in step.
    Re-binding on session rebind (resume/new/branch) replaces the previous
    list, mirroring set_ui_bridge.
    """
    self._live_tools = tools
    self._live_allowed = allowed
```

`register_tool` gains, after the duplicate check and before insertion:

```python
if self._live_tools is not None and self._live_allowed is not None and tool.name not in self._live_allowed:
    self._load_diagnostics.append(ResourceDiagnostic(
        kind="extension", name=extension_name,
        message=f"tool `{tool.name}` is not in allowed_tool_names; ignoring",
    ))
    return
...
if self._live_tools is not None:
    self._live_tools.append(tool)
```

`unregister_tool(source_id, extension_name, name)`: remove the registry entry
only when `registered.source_id == source_id` (silent no-op otherwise) and
remove the same object from the live list by identity. `bind` (session rebind)
keeps the live binding coherent: on `retire`/`_remove_registrations` also drop
removed tools from the live list. Extend the `BoundSession` protocol with
`refresh_system_prompt() -> None`; `request_system_prompt_refresh()` calls it
on the bound session when present.

`api.py`: `unregister_tool(name)` asserts generation then delegates
`self._runtime.unregister_tool(self._source_id, self._extension_name, name)`;
`refresh_system_prompt()` asserts generation then
`self._runtime.request_system_prompt_refresh()`.

`session.py`: after `tools = _filter_tools(...)` (line ~818) insert
`extension_runtime.bind_live_tools(tools, config.allowed_tool_names)`. Wrap the
existing `build_system_prompt(...)` call into a zero-arg closure
`def _build_system_prompt() -> str: return build_system_prompt(BuildSystemPromptOptions(...))`
with the IDENTICAL arguments (Task 0 Step 3's list), call it once for
`system`, and store the builder on the session:
`system_builder=None if config.system is not None else _build_system_prompt`
passed into `cls(...)` and kept as `self._system_prompt_builder`. Add:

```python
def refresh_system_prompt(self) -> None:
    """Rebuild the system prompt from current registries (extension seam)."""
    if self._system_prompt_builder is None:
        return
    self._harness.update_system_prompt(self._system_prompt_builder())
```

- [ ] **Step 5: Run the full fast suite (cross-cutting change), gates, commit**

```bash
uv run pytest -q --ignore=tests/coding/tui
uv run ruff check . && uv run ruff format --check . && uv run mypy
git add src/baldric_agent/harness.py src/baldric_coding/extensions/runtime.py src/baldric_coding/extensions/api.py src/baldric_coding/session/session.py tests/agent/test_harness_system_prompt.py tests/coding/extensions/test_live_tools.py tests/coding/session/test_refresh_system_prompt.py
git commit -m "feat: live tool registration and system-prompt refresh seams"
```

---

### Task 7: Built-in extension A — boot, trust gate, dynamic registration

**Files:**
- Create: `src/baldric_coding/extensions/builtins/mcp/__init__.py`
- Create: `src/baldric_coding/extensions/builtins/mcp/extension.py`
- Modify: `src/baldric_coding/extensions/builtin_registry.py`
- Modify: `src/baldric_coding/session/session.py` ONLY if Task 0 Step 2
  decided the `mcp_enabled` flag is needed (children load built-ins): add the
  field and pass `mcp_enabled=False` at the subagents child construction site
- Create: `tests/coding/extensions/test_mcp_extension.py`

**Interfaces:**
- Consumes: Tasks 2/4/5 outputs; `BuiltInExtensionContext` (paths,
  environment); `ExtensionAPI`.
- Produces: registered built-in `mcp`; module-level factory hooks for tests:

```python
# extension.py
API_VERSION = EXTENSION_API_VERSION
CAPABILITIES = ExtensionCapabilities(tools=True, hooks=True)

def setup(baldric: ExtensionAPI, context: BuiltInExtensionContext | None = None) -> None: ...

def _session_wants_mcp(api: ExtensionAPI) -> bool:
    """MVP gate: top-level sessions only (see spec 'Child sessions')."""

_supervisor_factory: Callable[[Sequence[McpServerConfig], Mapping[str, str]], McpSupervisor]
# module-level, monkeypatched by tests; default builds McpSupervisor
```

- [ ] **Step 1: Verify (MUST-HOLD)** — re-read `builtin_registry.py` (sync
  setup contract, `setup_with_context`), confirm Task 0 Step 2's child
  session decision, and confirm Task 0 Step 2b's lifecycle matrix still holds
  on this branch (rebind shares the runtime; the guard below is required, not
  optional). If the flag branch was chosen, also verify
  `CodingSessionConfig` field placement and the child construction site from
  Task 0's recorded file:line.

- [ ] **Step 2: Write failing tests** (`tests/coding/extensions/test_mcp_extension.py`,
  house anyio pattern, fake supervisor injected via `monkeypatch.setattr` on
  the module-level factory):

1. no config files → no supervisor built, no tools, no diagnostics.
2. user config with one stdio server, project untrusted + project file
   present → project servers ignored, exactly one diagnostic mentioning
   "not trusted"; user server boots (fake supervisor started).
3. trusted project → both servers boot; after the fake supervisor reports a
   connected server with two `McpToolInfo`s, the extension has registered two
   tools whose names follow `mcp__<server>__<tool>`; the live list (bound via
   Task 6, asserted through a real runtime + session built with a fake
   provider) contains them.
4. server transitions to `failed` → its tools are withdrawn from the live
   list (via `unregister_tool`).
5. `session_shutdown(quit)` → fake supervisor's `shutdown` awaited;
   `session_shutdown(branch)` → not shut down.
6. `_session_wants_mcp` gate: with the flag branch, a child config
   (`mcp_enabled=False`) boots nothing.
7. **Rebind idempotence (MUST-HOLD)**: fire `session_shutdown("resume")` then
   `session_start("resume")` on the same runtime (the Task 0 Step 2b matrix)
   → the fake supervisor's `start` was called exactly once (no second
   supervisor), the supervisor identity is unchanged, tools registered before
   the rebind are still present, and no duplicate-registration diagnostics
   were emitted.
8. **No `tools/list_changed` handling**: a server that adds tools after
   connect keeps its connect-time tool set (spec non-goal) — the extension
   registers no handler for the notification and the behavior is asserted as
   "tool count unchanged".

- [ ] **Step 3: Run and see them fail.**

- [ ] **Step 4: Implement `extension.py`.** Sync `setup` stores context, then:

```python
baldric.on("session_start")(self._on_session_start)     # async handler
baldric.on("session_shutdown")(self._on_session_shutdown)
baldric.on("input")(self._on_input)                     # Task 8 wires the body
baldric.register_command("mcp", self._mcp_command, ...) # Task 8 wires the body
```

`_on_session_start`: **idempotent boot guard first** (Task 0 Step 2b): if
`self._supervisor is not None` and it is not shut down → call `self._sync()`
and return (rebind path: new/resume/branch reuse the runtime; the registry
already holds the tools and `compose_tools` re-merges them — do NOT re-seed
and do NOT re-register blindly; the `_registered` map dedupes). Otherwise:
gate → `load_mcp_config(user_path=context.paths.user_mcp_config_path, project_path=context.paths.project_mcp_config_path(api.context.cwd) if api.context.project_trusted else None, environment=context.environment)` → diagnostics via `api.notify(..., "warning")` → build enabled list → if any, `_supervisor = _supervisor_factory(enabled, context.environment)`, `on_change(self._sync)`, then
`asyncio.get_running_loop().create_task(self._supervisor.start())` (house
pattern, `subagents/extension.py:387`). `_sync` registers connected servers'
tools: for each connected connection, skip names already in
`self._registered`; build the caller closure
`async def call(arguments, *, on_progress=None): return await self._supervisor.call_tool(server, info.name, arguments, on_progress=on_progress)`
and register `api.register_tool(mcp_tool_to_agent_tool(server, info, call))`;
withdraw on `failed`/`needs-auth` via `api.unregister_tool(name)`. If nothing
visible changed (same tool-name set and same section body), `_sync` is a
no-op — every real change rebuilds the system prompt and invalidates the
provider prefix cache, so churn must be avoided by design.
`_on_session_shutdown`:
`reason in ("quit", "reload")` → `await supervisor.shutdown()`, else return.
Register `builtin_registry.py` entry: `BuiltInExtension(name="mcp",
setup=_mcp_setup, hidden=True, setup_with_context=_mcp_setup_with_context)`
with lazy imports mirroring the llama.cpp pattern.

- [ ] **Step 5: Run tests, gates, commit**

```bash
uv run pytest -q tests/coding/extensions/test_mcp_extension.py
uv run ruff check . && uv run ruff format --check . && uv run mypy
git add src/baldric_coding/extensions/builtins/mcp src/baldric_coding/extensions/builtin_registry.py tests/coding/extensions/test_mcp_extension.py
git commit -m "feat: MCP built-in extension with trust gating and live registration"
```

---

### Task 8: Built-in extension B — first-turn wait, prompt section, `/mcp`

**Files:**
- Modify: `src/baldric_coding/extensions/builtins/mcp/extension.py`
- Modify: `tests/coding/extensions/test_mcp_extension.py`

**Interfaces:**
- Consumes: `supervisor.wait_ready/any_connecting/statuses/restart/set_enabled`
  (Task 4), `set_server_enabled`/`load_mcp_config` (Task 2),
  `api.refresh_system_prompt`/`add_prompt_section` (Task 6).

- [ ] **Step 1: Write failing tests** (fake supervisor + real runtime):

1. first `input` while a server is `connecting` → handler awaits
   `wait_ready(timeout=10.0)` exactly once (fake records); second input does
   not wait again; no wait when nothing is connecting.
2. after tools settle, exactly one prompt section titled "MCP servers" is
   registered (`add_prompt_section`) and `refresh_system_prompt` was called;
   the section body lists `- name (stdio, 2 tools): first line of
   description-or-instructions`, per-server cap 200 chars, total 1200; servers
   without description/instructions render `name (stdio, N tools)` only.
3. `/mcp` no args returns a listing line per server
   `name  state  transport  N tools` (plus `: first error line` when failed).
4. `/mcp off <name>`: calls `set_server_enabled(source_path, name, False)`
   (tmp_path config asserted) and `supervisor.set_enabled(name, False, None)`;
   unknown name → message; `/mcp on <name>` re-reads config and calls
   `set_enabled(name, True, fresh_config)`; `/mcp restart <name>` calls
   `supervisor.restart(name, fresh_config)`.
5. async work from the sync command handler is scheduled onto the running
   loop (assert via recorded fake calls after `await`-ing a tick).

- [ ] **Step 2: Run and see them fail.**

- [ ] **Step 3: Implement.** `_on_input` (async): if `self._admitted` or
  supervisor is None or `not any_connecting()` → return `None`; set
  `self._admitted = True`; `await wait_ready(timeout=10.0)`; return `None`.
  `_sync` (already invoked by `on_change`): recompute the section body and call
  `add_prompt_section` + `api.refresh_system_prompt()` (only when at least one
  enabled server is configured). `_mcp_command` (sync): parse args; for
  restart/on/off schedule
  `asyncio.get_running_loop().create_task(self._apply_toggle(...))`; the
  toggle re-reads config with the same trust rule as boot and persists via
  `set_server_enabled` (port of pi's `/mcp` persistence semantics).

- [ ] **Step 4: Run tests, gates, commit**

```bash
uv run pytest -q tests/coding/extensions/test_mcp_extension.py
uv run ruff check . && uv run ruff format --check . && uv run mypy
git add src/baldric_coding/extensions/builtins/mcp/extension.py tests/coding/extensions/test_mcp_extension.py
git commit -m "feat: MCP first-turn admission, servers prompt section, /mcp command"
```

---

### Task 9: Real-process integration test + resume regression

**Files:**
- Create: `tests/helpers/mcp_stdio_fixture.py`
- Create: `tests/mcp/test_integration_stdio.py`
- Create: `tests/coding/session/test_mcp_resume_repair.py` (path verified in
  Task 6 Step 2)

**Interfaces:**
- Consumes: everything above; existing fake-provider session test helpers.

- [ ] **Step 1: Write the fixture server**

`tests/helpers/mcp_stdio_fixture.py`:

```python
"""A tiny stdio MCP server used by integration tests: one `echo` tool."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("fixture")

@mcp.tool()
def echo(text: str) -> str:
    """Echo the text back."""
    return text

if __name__ == "__main__":
    mcp.run()
```

(Confirm against Task 1 Step 4 item 6; adjust import path to the pinned SDK.)

- [ ] **Step 2: Write the integration test** (`tests/mcp/test_integration_stdio.py`,
  anyio, generous margins — the suite-wide `--timeout=120` is the backstop):

Build a `McpServerConfig(name="fixture", server_type="stdio",
command=sys.executable, args=(str(HELPER_PATH),), timeout=30.0)`; construct a
real `McpSupervisor` with `environment=os.environ` snapshot; `await
supervisor.start()`; assert one `connected` status with exactly one tool;
`call_tool("fixture", "echo", {"text": "hi"})` returns text `"hi"`;
`await supervisor.shutdown()` leaves no lingering subprocess (assert via
`statuses()` state `closed`). Mark it so it can be excluded on POSIX CI if
process-spawning is flaky there? No — subprocess spawning is cross-platform;
do NOT add skips (house rule against weakening).

- [ ] **Step 3: Write the resume regression test**

Using the session test helpers (fake provider): craft initial messages
containing an assistant `ToolCall` named `mcp__gone__server__tool` with no
result, run one prompt, and assert the provider's request contains a synthetic
tool result for that call (mechanism: harness prelude
`_append_interrupted_tool_results` — Task 0 Step 5's recorded behavior; if the
loop path handles unknown-name calls differently, pin THAT observed
behavior with a comment naming the mechanism — never assert something the code
does not do).

- [ ] **Step 4: Run, gates, commit**

```bash
uv run pytest -q tests/mcp/test_integration_stdio.py tests/coding/session/test_mcp_resume_repair.py
uv run ruff check . && uv run ruff format --check . && uv run mypy
git add tests/helpers/mcp_stdio_fixture.py tests/mcp/test_integration_stdio.py tests/coding/session/test_mcp_resume_repair.py
git commit -m "test: MCP stdio integration and resume repair regression"
```

---

### Task 10: Polish — stderr logs, output saver, watchdog clock tests

**Files:**
- Modify: `src/baldric_coding/extensions/builtins/mcp/extension.py`
- Modify: `src/baldric_mcp/client.py` only if Task 1's stderr findings allow
  wiring
- Modify: `tests/coding/extensions/test_mcp_extension.py`

- [ ] **Step 1: Verify** — read `src/baldric_coding/tools/truncate.py` and
  `src/baldric_coding/tools/output_accumulator.py` (and the bash tool's
  output-file path convention) to find the house helper for saving full tool
  output and its destination directory convention. Reuse it; do not invent a
  parallel convention.

- [ ] **Step 2: Write failing tests**: the extension passes an
  `output_saver` into `mcp_tool_to_agent_tool` that writes under the house
  output location and returns the path (tmp_path-based, asserting the file
  content); truncated notes carry that path. If Task 1's SDK findings exposed
  a stderr pipe: client test asserts the tail lands in the sink.

- [ ] **Step 3: Implement** — wire `output_saver` in the extension's
  `mcp_tool_to_agent_tool(...)` call; wire `stderr_sink` by opening
  `paths.logs_dir / "mcp" / f"{server}.log"` (append mode, create parents) and
  passing it as `stdio_client(server, errlog=...)`; http servers get `None`
  (no stderr); document the seam inline.

- [ ] **Step 4: Run, gates, commit**

```bash
uv run pytest -q tests/coding/extensions/test_mcp_extension.py tests/mcp
uv run ruff check . && uv run ruff format --check . && uv run mypy
git add -u
git commit -m "feat: MCP output saving and stdio stderr logging"
```

(`git add -u` only if the file set is exactly the four above — otherwise list
paths explicitly.)

---

### Task 11: Docs and full gates

**Files:**
- Create: `website/content/guides/mcp.md` (verify the guides directory and
  frontmatter conventions from an existing guide, e.g. the providers guide)
- Modify: the docs nav/index file that registers guides (find it via
  `website/` config; verify before editing)
- Create: `dev-notes/journal/` entry if that is the house journal location —
  verify where existing build journals live (`dev-notes/`) and follow it

- [ ] **Step 1: Write the user guide**: what MCP is, `mcp.json` (user +
  project, trust gating), `/mcp` usage, `enabled`/`timeout`/`description`/`type`
  fields, `${ENV}` expansion, tool naming `mcp__<server>__<tool>`, states and
  lazy reconnect, and the known costs/limits: tool churn rebuilds the system
  prompt (provider prefix-cache invalidation — accepted, minimized by the
  `_sync` no-op rule), no OAuth, no resources/prompts, no `list_changed`,
  modes that bypass the `input` hook get tools from turn two (mirror the
  spec's non-goals and Task 0 Step 2c findings).
- [ ] **Step 2: Write the dev-notes journal entry** (what was added, why, how
  it maps to pi's design, how to test) per the repo's documentation
  expectations.
- [ ] **Step 3: Run every gate (cross-package change ⇒ full suite):**

```bash
uv run pytest -q
uv run pytest --cov
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run python scripts/check_import_graph.py
uv run python scripts/check_structure.py
uv run python scripts/check_suppressions.py
uv run python scripts/check_agent_guidance.py
```

If `check_structure.py` flags `session.py` growth, record it with `--init`
(house rule) in a separate commit `chore: record structure growth for mcp seams`.
Coverage must stay ≥ 80%.

- [ ] **Step 4: Commit docs**

```bash
git add website/content/guides/mcp.md <nav-file> <journal-entry>
git commit -m "docs: MCP servers guide and build journal"
```

---

## Final verification checklist (before declaring done)

- [ ] All tasks' checkboxes ticked; every MUST-HOLD verification recorded in
  the preflight findings section.
- [ ] `uv run pytest -q` fully green locally (Windows skips are expected and
  documented).
- [ ] All nine gates green (Task 11 Step 3).
- [ ] Manual smoke (optional but recommended): configure a real stdio server
  (e.g. `npx -y @modelcontextprotocol/server-filesystem .` in a scratch dir),
  run `uv run baldric`, `/mcp` shows connected, a tool call works, `/mcp off`
  persists.
- [ ] The branch diff contains nothing outside the touchpoint table in the
  spec (plus preflight findings and docs) — every exception is logged in
  **Execution deviations log** with its impact analysis and a `deviation:`
  commit note.
- [ ] Spec and plan still describe what was actually built (any drift found
  via Execution Rules R1 was reconciled, not worked around).

## Execution deviations log

Appended during execution per Execution Rules R4. One entry per deviation;
an empty section means the plan was followed as written. Entry format:

- **D\<n\> — \<short title\>** (Task \<n\>, \<date\>): why the plan was wrong or
  insufficient; impact surface checked (callers / tests / guards / consumers);
  design change? (yes → owner consulted); commits.
