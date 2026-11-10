# Hook composition contract (v2 extension API)

Status: **contract only** — defines the semantics that every extension hook must obey.
Written before the provider-level and session-structure hooks (plan Tasks A/B) so both
use one rulebook instead of inventing divergent ones. No runtime behaviour changes here.

This is the third multiplier of extension freedom:

```
freedom = handle width (who can mutate what)
        x replayability (every mutation lands in the event-sourced log)
        x composition determinism (what happens when several extensions intercept)
```

Without the third, wide handles are undefined behaviour. This document fixes it.

## The four rules

1. **Order is deterministic.** Handlers run in registration order:
   extension load order first, then within-extension registration order. Order is
   observable and testable. No handler may be reordered, deduplicated, or run
   concurrently with another handler for the same event.

2. **Errors are isolated per handler.** One handler raising does not stop the
   others and does not abort the run; the failure is recorded as a runtime
   diagnostic against that extension. Whether the *operation* fails is decided by
   the hook's **failure mode**, set per hook below — never by "the exception
   silently changed the global result". Two failure modes:
   - `fail-open` (observe/render/notify seams): a raising handler is skipped, the
     operation proceeds with the other handlers' results.
   - `fail-closed` (safety seams: trust, tool-call interception): a raising handler
     is treated as a refusal/gate for that operation (never as "allow").

3. **Aggregation is per-seam and never mixed.** A seam is exactly one of:
   - **chained** (transform): handler *N+1* receives the value returned by handler
     *N*; the last handler's return value is the result. Used for `input`,
     `context`, `context_with_system`, `message_end`, `tool_result`,
     `before_provider_request`, custom summary rewrites.
   - **in-place** (mutate): handlers receive and mutate the same object; the
     object itself is the result. Used for `before_provider_headers.headers`,
     `before_agent_start.system_prompt_options`.
   A chained seam's handler returns a new value; an in-place seam's handler
   returns nothing meaningful. A seam is never both. This is enforced by type:
   chained seams are typed `Callable[[Payload], Payload]`, in-place seams
   `Callable[[MutableView], None]`.

4. **Termination is per-seam and declared.** A "gate" seam (block/cancel/handled)
   is **first-wins short-circuit**: the first handler returning a gate result ends
   the seam; the operation is gated and later handlers for that operation do not
   run. A "last-override" seam (e.g. cache-warming decision) is **last-valid-wins**:
   every handler runs and the final non-null result wins. Each seam declares which
   below; a seam is never both.

## Seam catalog

Every seam that a v2 extension can hook gets exactly one row here. A new seam that
does not add a row is non-conformant. The `capability domain` column maps to
`ExtensionCapabilities` (see the plan, Task G): an extension that has not declared
the domain does not get that seam's handlers registered at all (default deny).

| seam | aggregation | failure mode | termination | capability domain | status |
| --- | --- | --- | --- | --- | --- |
| `input` | chained | fail-open | — (transform) | `hooks` (existing) | shipped |
| `tool_call` (before) | in-place | fail-closed | first-wins (`block`) | `hooks` (existing) | shipped |
| `tool_result` (after) | chained | fail-open | last-override (`replace`) | `hooks` (existing) | shipped |
| `project_trust` | in-place | fail-closed | first-wins (gate) | `hooks` (existing) | shipped |
| `message_end` | chained | fail-open | — (transform) | `hooks` (existing) | shipped |
| `context` (provider) | chained | fail-open | — (transform) | `provider_hooks` | planned (Task A) |
| `context_with_system` (provider) | chained | fail-open | — (transform) | `provider_hooks` | planned (Task A) |
| `before_provider_headers` | in-place | fail-open | last-override (mutation wins) | `provider_hooks` | planned (Task A) |
| `before_provider_request` | chained | fail-open | last-override (payload) | `provider_hooks` | planned (Task A) |
| `after_provider_response` | in-place (read) | fail-open | — (observe) | `provider_hooks` | planned (Task A) |
| `provider_stream_event` | in-place (read) | fail-open | — (observe) | `provider_hooks` | planned (Task A) |
| `cache_warming_decision` | chained | fail-open | last-override (action) | `provider_hooks` | planned (Task A) |
| `session_before_compact` (manual/threshold) | — | fail-closed | first-wins (`block`\|`replace`) | `session_structure_hooks` | planned (Task B) |
| `session_before_compact` (overflow) | — | fail-closed | **`block` forbidden** | `session_structure_hooks` | planned (Task B) |
| `session_before_fork/switch/tree` | — | fail-closed | first-wins (`block`\|`replace`) | `session_structure_hooks` | planned (Task B) |

Overflow compaction note: the overflow path may `observe` or `replace` but **may not
`block`**. A `block` there is a contract violation: the host reports it to the
extension author and enforces the default compaction, rather than silently
honouring it (a silent honour is what produces the model-overflow + extension-veto
infinite retry loop).

## What the current runtime already satisfies

`ExtensionRuntime.emit_event` (runtime.py) already runs handlers in registration
order and isolates a raising handler (records a runtime failure, continues). The
existing seams therefore already obey rules 1 and 2 for their declared failure
modes. Rules 3 (aggregation shape) and 4 (termination) are new **contract
commitments** that the planned seams must implement; the shipped seams above are
documented to the shape they already have, and the guard test below pins the parts
that exist today so a refactor cannot silently regress them.

## How to add a seam (checklist)

1. Add a row to the catalog above with all four columns.
2. Type it as chained or in-place per rule 3.
3. Declare its capability domain; add the domain to `ExtensionCapabilities` if new.
4. Implement it so a raising handler behaves per its failure mode.
5. Add a fake-extension test covering: normal, two-handlers-agree, two-handlers-
   conflict (per termination rule), and one-handler-raises.
6. If it is a gate seam, add a "contract violation" test (e.g. overflow + block).
