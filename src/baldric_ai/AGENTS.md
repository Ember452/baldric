# baldric_ai - Provider Layer

Provider and model streaming layer. Everything here talks to a model endpoint
and emits `AssistantMessageEvent` streams; nothing here knows about agents,
sessions, files, or UI.

## Responsibilities

- Wire request serialization for each provider adapter (`openai.py`,
  `anthropic.py`, `google.py`, `mistral.py`, `openai_codex.py`).
- Streaming event translation into `AssistantStartEvent` /
  `TextDeltaEvent` / `ThinkingDeltaEvent` / `ToolCallStartEvent` /
  `ToolCallEndEvent` / `AssistantDoneEvent` / `AssistantErrorEvent`.
- Network retry and timeout semantics (`stream.py`), auth headers, and
  provider-specific request quirks.
- `FakeProvider` for deterministic agent-loop tests.

## Boundaries

- Do not import `baldric_agent` or `baldric_coding`; this is the lowest layer.
- No UI, terminal, Rich, or Textual imports.
- No session or file-location knowledge (that belongs to `baldric_agent` and
  `baldric_coding`).
- Provider-specific assumptions stay in adapters; shared code in `stream.py`
  and `messages` must remain provider-neutral.

## Known Limitations (do not "fix" these)

- Each adapter documents its own quirks in module docstrings; a "cleanup" that
  makes adapters uniform usually breaks a provider. Read the adapter first.
- Retries here are transport-level only. Higher-level recovery (image
  rejections, overflow compaction) belongs to `baldric_agent` / `baldric_coding`.

## Tests

- `tests/ai/` covers adapters with fake HTTP responses and `FakeProvider`.
- Do not add live-network tests; use recorded payloads or fakes.
