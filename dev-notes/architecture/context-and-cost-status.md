# Context and cost: current state

**Status:** verification note — 2026-11-06 (branch `reliability/p3-and-followups`)

The roadmap's "context and cost" phase was researched as four items. Reading the
code shows all four are already implemented, mostly because the harness was
built Pi-aligned from the start. This note records where each lives so the work
is not redone and so a future change has a reference.

| Item | Where | What it does |
| --- | --- | --- |
| Single context projection | `src/baldric_agent/context_projection.py` (`provider_context`) | The loop replays `provider_context(messages)`, a pure derivation from durable history: it drops empty failed/aborted turns and rewrites rejected image results to text errors. History is never mutated. |
| Compaction cut points | `src/baldric_coding/session/runtime.py` (`_recent_preserving_compaction_plan`, `_auto_compaction_plan`), `compaction/context_window.py` | Cut points are token-budgeted (`DEFAULT_COMPACTION_KEEP_RECENT_TOKENS`), keeping a recent tail and summarizing the replaced prefix as one `CompactionEntry`; overflow and threshold triggers share the plan. |
| Incremental context state | `src/baldric_coding/session/session.py` (`_context_usage_cache`, `_invalidate_context_usage_cache`) | `context_usage` is computed once and invalidated only when a message/tool/compaction/model change lands, instead of recomputing every render. Provider-reported usage wins over the estimate when present. |
| Cache affinity | `src/baldric_ai/openai_cache.py`, `openai_compatible.py` (`prompt_cache_key`, `_apply_session_affinity_headers`), `anthropic.py` (`cache_control` breakpoints), `openai_codex.py` (`session-id`) | OpenAI-compatible sends a prompt cache key and the provider's session-affinity header; Anthropic marks `cache_control` on system/messages/tools; Codex sends `session-id`. |

## Genuine remaining gaps

- Google and Mistral expose no cache-affinity mechanism, so adapters already send
  nothing there; there is nothing to add.
- The estimate is a heuristic; it is advisory (the UI shows `?` until the
  provider reports usage). Improving the heuristic is not required for
  correctness.

No code change is warranted for this phase; the four items are present and
tested by the existing session/compaction/usage suites.
