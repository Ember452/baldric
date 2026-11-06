# baldric_agent - Portable Agent Harness

The reusable agent brain: loop, events, tools, messages, and sessions. Any
frontend can use it; it depends on nothing above it.

## Responsibilities

- `loop.py` with `assistant_stream.py`, `tool_calls.py`, and
  `context_projection.py`: the loop, provider translation, tool lifecycle, and
  derived model context.
- `events.py`: the canonical event stream every frontend consumes.
- `messages.py`: Pi-compatible message models and wire serialization.
- `tool_history.py`: repair of append-only tool-call histories.
- `session/storage.py`: JSONL persistence, torn-tail repair, locking.
- `tools.py`: the tool contract (`AgentTool`, `AgentToolResult`).

## Boundaries

- Do not import `baldric_coding`, `textual`, or `rich`;
  `scripts/check_import_graph.py` and `tests/guards/` enforce it.
- Events are the contract: model-visible behavior needs a new event or
  documented message field, not a frontend callback.
- Durable history is append-only; projections derive from history, never
  mutate it.

## Known Limitations (do not "fix" these)

- `session/storage.py` locks with `fcntl`; its 7 Windows-only mypy errors are
  expected (CI runs mypy on Linux).
- An empty failed assistant turn is persisted for diagnostics, not replayed;
  do not "simplify" that.
- Image recovery is bounded at three consecutive failures and never re-runs
  side-effecting tools; raise the bound only with an outage test.

## Tests

- `tests/agent/` uses fakes; keep tests deterministic and offline.
- A loop-ordering regression is usually a contract change: update the test with
  the behavior and say so in the commit.
