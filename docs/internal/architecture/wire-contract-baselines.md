# Wire contract baselines

**Status:** accepted — 2026-11-06 (branch `chore/p0-contract-baselines`)

This note records the first slice of the reliability programme: before changing
behavior, pin the shapes that other things already depend on. It also records
what that slice deliberately did **not** do, so the next change does not
re-litigate it.

## Why

Three consumers read these shapes:

- the persisted JSONL transcript (user data; older and newer Baldric must read it);
- the JSON event stream (`--print` / JSON mode, and the RPC wire);
- the built-in message/event union that every frontend and extension renders.

Before this change only two message shapes were locked
(`assistant_message.json`, `tool_result_message.json`). The unions themselves,
the provider-stream events, the loop events, and every session entry type were
unpinned: adding a field, renaming an alias, or reordering a union branch could
change the protocol with a green suite.

## What is pinned

| Snapshot (`tests/expected/`) | Covers | Written by |
| --- | --- | --- |
| `agent_message_union.jsonl` | 8 `AgentMessage` branches (text, image, assistant, tool result, bash, custom, branch summary, compaction summary) | `tests/agent/test_wire_contract.py` |
| `provider_events.jsonl` | 12 `AssistantMessageEvent` branches | same |
| `agent_events.jsonl` | 10 `AgentEvent` branches | same |
| `session_entries.jsonl` | 10 `SessionEntry` types in canonical persisted JSONL | `tests/agent/test_session_entry_contract.py` |

Each file is the production serialization output (aliases on, `None` omitted),
one object per line, so a diff points at the branch that changed rather than at
one long line.

Two guards keep the snapshots honest:

- **coverage** — the fixture sets are compared against the union's declared
  branches, so a new message/event/entry type fails the test instead of silently
  missing from the snapshot;
- **round-trip** — every fixture is serialized, parsed back, and compared whole.

The session snapshot also pins the mixed convention that already exists:
entries are snake_case while the messages and usage they embed are camelCase.

## Changing a snapshot

A snapshot change is a protocol change. Update it only with an explicit flag and
review the diff:

```bash
UPDATE_EXPECTED=1 uv run pytest tests/agent/test_wire_contract.py tests/agent/test_session_entry_contract.py
git diff tests/expected/
```

## Provider-layer import surface

`baldric_ai` may import the harness's provider-neutral wire contract and nothing
else:

```
baldric_agent.messages
baldric_agent.provider
baldric_agent.provider_events
baldric_agent.tools
baldric_agent.types
```

`scripts/check_import_graph.py` now reports any other `baldric_agent…` import,
including `from baldric_agent import X` (the package root runs `__init__`, which
pulls session storage and JSONL). The scanner has its own synthetic-violation
tests, and one test proves the allowlist still points at modules that exist.

**What this guard does not claim.** It does not say the two packages have the
direction their documentation describes. `baldric_ai/AGENTS.md` still calls the
provider layer "the lowest layer" and forbids importing `baldric_agent`, while
the code is the reverse: adapters depend on the harness's domain contract. That
is a normal adapter → contract direction; the declaration is what is wrong.
Fixing the declaration, and adding the missing `rendering → tui` direction, is
deferred to the frontend/extension hygiene phase. A blanket
`("baldric_ai", "baldric_agent")` rule is **not** added because it would be
false today.

## Session format evolution (decision now, code later)

When the first real session-format change lands, it follows this policy:

1. every entry carries an integer `v`, defaulting to `1`, omitted from the
   serialized line while it equals the current format version;
2. readers reject a `v` greater than the supported version with a clear
   `SessionJsonlError`, instead of a generic validation error;
3. migration stays confined to `session/jsonl.py` (the existing shape-sniffing
   migration keeps working for v1);
4. the unknown-field policy (reject / preserve) is decided when a v2 actually
   exists, not before.

**Why it is not implemented in this slice:** every file that exists today is v1
by definition, so the field has no behavior to exercise, and `src/` is covered by
the structure ratchet — a field with no consumer would either grow a ratcheted
file or force an unrelated refactor. The first format change (prompt/tool-set
version entries, a compaction checkpoint, usage entries) carries it.

## Deliberately deferred from this slice

| Item | Deferred until | Reason |
| --- | --- | --- |
| Provider record/replay fixtures | a regression needs pinning (reliability phase) | adapter tests already drive fake transports and recorded payloads; a VCR layer without a consumer is speculative |
| Fault-injection harness | the first storage/cancel fix | the harness is only useful once a fix needs it; building it first risks an unused abstraction |
| Generic risk-switch framework | the first risky behavior changes | add a switch per behavior on the existing config path; do not build a flag system up front |

## Verification

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run python scripts/check_import_graph.py
uv run pytest -q tests/agent tests/guards
```
