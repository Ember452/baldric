# baldric_agent - Portable Agent Harness

The reusable agent brain: loop, events, tools, messages, and JSONL session
storage. This package must stay usable by any frontend, so it depends on
nothing above it.

## Responsibilities

- `loop.py`: the provider/tool loop, including bounded image-tool recovery and
  `_provider_context` projection.
- `events.py`: the canonical event stream every frontend consumes.
- `messages.py`: Pi-compatible message models and wire serialization.
- `tool_history.py`: repair of append-only tool-call histories.
- `session/storage.py`: JSONL persistence.
- `tools.py`: the tool contract (`AgentTool`, `AgentToolResult`).

## Boundaries

- Do not import `baldric_coding`, `textual`, or `rich`. CI enforces this
  through `scripts/check_import_graph.py` and `tests/guards/`.
- Events are the contract: new model-visible behavior needs a new event or a
  documented message field, not a frontend callback.
- Durable history is append-only; any context projection must derive from
  history rather than mutate it.

## Known Limitations (do not "fix" these)

- `session/storage.py` uses `fcntl` for POSIX locking; the 7 Windows-only mypy
  errors there are expected. CI runs mypy on Linux.
- A failed assistant turn with no content is persisted for diagnostics but
  excluded from provider context. Do not "simplify" that projection.
- Image recovery is bounded at three consecutive failures and never re-runs
  side-effecting tools. Do not raise the bound without a test for the outage
  case.

## Tests

- `tests/agent/` uses fake providers and fake tools; tests must stay
  deterministic and offline.
- A regression in loop ordering is usually a behavior contract change: update
  the test only together with the intended behavior and say so in the commit.
