# Audit follow-ups: what the 2026-11 review changed

**Status:** first pass complete on `fix/audit-followups-2026-11`.

This note records, for each finding in the review, whether the branch fixed it,
deleted the dead thing, or deliberately left it. The rule from
`contract-debt.md` applies: an entry is either wired with a test, removed, or
listed here with the trigger that would bring it back.

## Fixed

| Finding | Change |
| --- | --- |
| Session entries could not gain a field (P0) | `schema_version` on every entry (omitted at v1, so files stay byte-identical), tolerant read that strips undeclared fields at any depth, and `SessionVersionError` naming both versions for a newer file or an unknown type |
| `prompt()`-then-`cancel()` did nothing; an abandoned run wedged the harness (P0) | The run and its cancel token are registered before the generator body runs; `_RunIterator` owns the lifecycle and `aclose()` releases it |
| TUI never observed `x-inference-provider` (P0) | `load()` rebuilds an owned Hugging Face provider through the observer path the print and RPC frontends already used |
| `resume()` dropped `tools=` and `runtime_model_catalogs` (P1) | Both copied; a parity test drives a real `resume()` |
| `/model` and `/thinking` were silent no-ops in print mode (P1) | Print mode applies the intents; commands that only need a screen say `interactive-only` |
| Print renderers disagreed about failure (P1) | One predicate: `error`, `aborted` and truncated (`length`) all fail the run |
| Persisting a message was O(n) in session length (P1) | A tip append extends the derived state; full replay stays for retries, non-tip parents and other entry kinds. Index writes are throttled when only the timestamp changes |
| Google and Mistral never reported usage (P0) | Both parse it into the same normalised `Usage` shape as the other adapters |
| Four partial SSE parsers (P1) | `_sse.iter_sse_events` is the only one; each adapter asserts a split frame yields the same events as a single-line frame |
| Codex encoded `item_id` into `ToolCall.id` (P1) | Only the portable `call_id` is stored; the adapter keeps its own map |
| Retry data dropped, one-second retry default (P1) | Retry data lands on the message diagnostics (truncated, never model-visible); default delay is 15s |
| Extension API had no version (P0) | `EXTENSION_API_VERSION` + `ExtensionCapabilities`, checked at load |
| Extensions could read every credential and shadow a built-in provider id (P0) | Scoped credential reader and environment allow-list at the single auth choke point; id collisions are refused |
| `/reload` never unloaded modules; `reset_for_reload` was dead and its docstring lied (P1) | Deleted the dead method; `retire()` unloads the module names that generation loaded, behind a prefix guard |
| A failed `setup()` never received `session_shutdown` (P1) | Kept on a shutdown-only queue and drained by the next awaited shutdown |
| Installer registry write was not atomic (P2) | `atomic_write_text`, and a corrupt registry is preserved as `<name>.corrupt` |

## Still open (with the trigger that brings them back)

| Finding | Why it is still open |
| --- | --- |
| `Usage.cost` has a reader and no producer | Removing it changes the wire shape; wiring it needs pricing in the provider layer, where it does not exist today. Decision pending on `deferred-decisions.md` terms. Trigger: the first consumer that needs cost to survive an export. |
| `execution_mode="parallel"` | **Fixed as a rejection**: `AgentHarness` refuses a tool that declares `parallel`, because this loop runs tools sequentially. Pi implements the parallel batch through `toolExecution`; that remains a feature. |
| `EntryAppendedEvent` | **Deleted** with its whitelist entry; a guard test now rejects any whitelisted type that no event module declares. |
| `BashExecutionMessage` is never constructed | Wire-parity placeholder for Pi's `!!` path, which Baldric implements differently. Trigger: implementing `!!` as a message. |
| `/help` and `/context` command functions were unregistered | **Fixed by registering them.** They were implemented and tested but unreachable. The old `test_non_pi_commands_are_not_registered` guard forbade them for pi-parity reasons; that policy is now reversed on purpose (`/provider` and `/resources` still stay unregistered), and both tests pin the new contract. |
| Tool-level authorization does not exist (`before_tool_call` has no call sites) | The trust model is project-level by design; tool gating is a new feature. Trigger: the first request to restrict a specific tool. |
| Windows `os.kill(pid, 0)` "kills processes" | **Not a defect.** Verified on this platform: the child kept writing heartbeats (4 → 19) and stayed alive. Recorded so it is not re-investigated. |
| Extension credential scope is declared by the extension | A hostile extension can still name another provider's credential. Closing it needs a host-owned provider-to-credential map and a `resolve_provider_auth` signature change. |
| `CodingSession` owns ~33 mutable fields that other modules write | **Ratcheted, not eliminated.** The four hottest fields now have semantic writers on the class and every call site uses them (154 external write sites -> 119). `tests/guards/test_session_state_write_ratchet.py` fails on any new write and fails again when a cleanup is not recorded, so the number can only fall. The remaining bulk is `_adopt_replacement`, which copies a whole state in one operation. |
| `SessionInfoChangedEvent` / `ThinkingLevelChangedEvent` did not reach a frontend | **Fixed.** Both are queued when they happen and handed to the next `prompt()` stream before its own events (pi publishes session-level events to session subscribers; queueing is the smaller equivalent here). A frontend therefore sees a rename or a thinking change even when an extension made it. The idle-time case still waits for the next run. |
| `Usage.cost` had no producer | **Fixed.** `_persist_message` prices the response from the catalog before the entry is written (a provider-reported cost wins, an unpriced model stays zero). Pi prices in the adapter because its model objects carry rates; ours come from the provider catalog. |
| `BashExecutionMessage` was never constructed | **Fixed.** Terminal commands persist as `bashExecution` messages; context projection renders the same text the model saw before, honours `exclude_from_context`, and the transcript loader shows them on resume. |
| `before_tool_call` has no app call site | **Not a defect.** The loop honours and tests the hook (`tests/agent/test_agent_loop.py`), and the app layer deliberately uses the extension `tool_call` hook instead, because that hook also rewrites arguments - which `before_tool_call` cannot express. Keeping the harness hook is pi parity for embedders; recorded so it is not re-investigated. |
| Extension credential scope was declared by the extension | **Fixed.** The host passes the provider id into `resolve_provider_auth` and keeps only declared names belonging to it (`<id>` or `<id>:<suffix>`). Environment names stay as declared, because any in-process extension can read `os.environ` directly; the credential store is the real boundary. |

## Verification

- `ruff check`, `ruff format --check`, `mypy` (Windows: only the known `fcntl` errors), four ratchets.
- `pytest -q` (full suite, TUI included).
- Every fix above landed with a test that fails against the previous
  implementation; the ones where that was checked by reverting the source file
  say so in their commit message.
