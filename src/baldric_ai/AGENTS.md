# baldric_ai - Provider Adapters

Provider adapters: they talk to a model endpoint and emit
`AssistantMessageEvent` streams, and know nothing about sessions, files, or UI.

This is an **adapter layer over the protocol contract**: `baldric_protocol`
owns the wire types and the `ModelProvider` port. The arrow is
`baldric_ai -> baldric_protocol`, restricted by CI to the contract modules.

## Responsibilities

- Request serialization and streaming translation per adapter
  (`openai_compatible.py`, `anthropic.py`, `google.py`, `mistral.py`,
  `openai_codex.py`).
- Retry policy (`retry.py`), timeouts, auth headers, provider quirks.
- `FakeProvider` for deterministic agent-loop tests.

## Boundaries

- Import `baldric_protocol` only through `messages`, `provider`,
  `provider_events`, `tools`, and `types`; never `baldric_agent` or
  `baldric_coding`.
- No `baldric_coding`, UI, terminal, Rich, or Textual imports.
- Provider quirks stay in adapters; `stream.py` and `retry.py` stay neutral.

## Known Limitations (do not "fix" these)

- Making adapters uniform usually breaks a provider; read the adapter first.
- Retries are transport-level only; image rejection and overflow recovery
  belong to `baldric_agent` / `baldric_coding`.

## Tests

- `tests/ai/` uses fake HTTP responses and `FakeProvider`; no live-network tests.
