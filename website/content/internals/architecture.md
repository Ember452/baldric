---
title: Architecture overview
description: How Baldric is split into four packages — and why that boundary is the whole point.
---

Baldric is deliberately small and layered. The most important design idea is a
**boundary**: the reusable agent "brain" knows nothing about terminals, file
paths, or rendering. Everything app-specific wraps around it.

## Four packages

```text
baldric.runtime  →  { baldric.agent, baldric.ai }  →  baldric.protocol
```

### `baldric.protocol` — the shared wire contract

Owns the provider-neutral shapes every other layer speaks: message and content
models, the tool contract, provider-stream events, and the persisted session
wire (entry shape, tree traversal, JSONL format). Its only dependency is
pydantic — no I/O, no platform code, nothing above it. Third parties (provider
adapters, frontends, session tooling) can build against this package alone.

### `baldric.ai` — talking to models

Owns provider-specific model streaming. It translates each provider's API
(OpenAI, Anthropic, …) into Baldric's **provider-neutral event stream**, so nothing
above it has to care which model vendor is in use.

### `baldric.agent` — the portable brain

Owns the reusable agent core: the [agent loop](/internals/agent-loop/), the
harness, event emission, and tool-call orchestration, all built on the
`baldric.protocol` contract. This package
must **not** import CLI, Rich, Textual, or resource-loading code. That's what
keeps it portable.

### `baldric.runtime` — the coding application

Owns everything that makes Baldric a *coding agent you run*: the CLI, the built-in
[tools](/reference/tools/), [project instructions](/guides/project-instructions/),
[skills and prompts](/guides/skills-and-prompts/),
[sessions on disk](/guides/sessions/), provider configuration, and the
Textual TUI.

### Local-backend boundary

Local inference belongs to `baldric.runtime`, not the portable agent core. A staged
extension runtime owns a source- and generation-aware local-backend registry
beside its provider registry. Backends return typed configuration, status,
progress, diagnostics, and capability values; the Textual adapter renders them
and owns cancellation, confirmation, and idle checks. Pairing each backend with
its exact source-owned provider layer prevents a shadowing extension from using
or resetting another source's integration. See the [local backends
guide](/guides/local-inference/).

Phase 6 validates the boundary with a permanent second fake backend and a
test-only Ollama adapter. Provider discovery and backend status may use
separate endpoints, installed/running state fits generic model state, and
`NoAuth` needs no special-case backend API. Refresh cancellation is bounded and
generation-safe; late work cannot publish after retirement. Router mutations
remain a later phase.

TUI and print startup share the same trust-aware preparation boundary: load the
trusted built-ins and eligible extensions, restore safe dynamic snapshots,
resolve an explicit provider/model, then construct the candidate runtime. A
saved llama.cpp snapshot can therefore support explicit startup during server
downtime without making the local backend an implicit fallback.

## Dependency direction

Dependencies only point one way: `baldric.runtime → {baldric.agent, baldric.ai} → baldric.protocol`,
and `baldric.protocol` depends on nothing but pydantic. UI code
*consumes* events; the core never reaches up to render anything. In one line:

```text
AgentHarness = reusable brain
CodingSession = coding-agent environment
TUI = one possible frontend
```

## Why the boundary matters

Because the core is UI-free, the same agent can drive print mode, the Textual
TUI, or a frontend you build yourself — all by consuming the same event stream.
That's also what makes Baldric readable: each layer answers one question, and you can
study it without untangling the others.

→ Next: [The agent loop & events](/internals/agent-loop/) ·
[Design principles](/internals/design-principles/) ·
[Build your own frontend](/internals/custom-frontend/)

> [!NOTE] Going deeper
> The phase-by-phase build journals, design docs, and ADRs live in the repo under
> `dev-notes/` (not on this site). See [Contributing](/contributing/).
