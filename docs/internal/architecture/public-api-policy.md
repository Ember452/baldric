# Public API policy (`baldric_ai` / `baldric_agent`)

**Status:** accepted — 2026-11-05
**Scope:** the three distributed packages, with concrete enforcement for
`baldric_ai` and `baldric_agent`. `baldric_coding` already has an explicit
`__all__` list and the same policy applies to it.

## Context

`baldric_coding/__init__.py` has always listed its public facade explicitly
(139 names at the end of phase 1). `baldric_ai` and `baldric_agent` instead used:

```python
__all__ = [name for name in globals() if not name.startswith("_")]
```

Measured before this decision on `main`:

| package | `__all__` names | of which submodule objects |
|---|---:|---:|
| `baldric_ai` | 55 | 18 |
| `baldric_agent` | 67 | 11 |

The dynamic comprehension has three problems:

1. It turns internal module layout into an accidental public surface.
2. It is import-order dependent: a module enters `__all__` only if some import
   path happened to bind it before the comprehension ran.
3. It exports a `types` module object from `baldric_agent`, which shadows the
   standard-library `types` module for any caller doing `from baldric_agent import *`.

The blueprint's phase 2 will rearrange exactly these modules — for example
`baldric_agent.messages` → `baldric_agent/contracts/messages.py` and
`baldric_ai.providers/*` into named subpackages. A dynamic `__all__` would turn
every such move into an unannounced public API change.

## Decision

1. **The supported public API of each package is exactly the names in its static
   package-root `__all__` list.** Only symbols (classes, functions, constants) are
   public. Module objects are not public API.
2. **`__all__` is a static list literal.** It must not be derived from `globals()`,
   `dir()`, a comprehension, or any other runtime computation.
3. **Submodule imports are implementation details.** `import baldric_agent.messages`
   and `from baldric_agent import messages` may continue to work today, but they are
   not contractual. Internal module moves may change or remove those paths without
   an API deprecation cycle; public renames/removals of *symbols* still follow
   normal deprecation policy.
4. **Internal reorganisation is therefore allowed without changing `__all__`.**
   Update internal imports and keep package-root symbol names stable.
5. **Documented examples must import from the package root**, not from submodules.

## Concrete effects of this decision

- `baldric_ai.__all__`: 55 → **37 symbols** (18 module objects removed).
- `baldric_agent.__all__`: 67 → **56 symbols** (11 module objects removed).
- `from baldric_ai import *` / `from baldric_agent import *` no longer bind module
  objects. The repository has zero star-import sites, so no internal code changes
  are required; external star-import users should switch to explicit imports.
- Direct imports of existing submodules continue to work until that module moves.
  Their paths were never part of the supported API, so moving them is not an API
  break. This is what unblocks the phase-2 blueprint moves.
- The `types` stdlib shadowing footgun disappears from `from baldric_agent import *`.

## Enforcement

`tests/test_public_api_contract.py` enforces both halves:

- exact symbol sets for `baldric_ai` and `baldric_agent`;
- `__all__` must be an `ast.List` of string constants, rejecting a regression back
  to `globals()`.

`baldric_coding` remains covered by its explicit 139-name facade and the existing
phase-1 ledger checks.

## Rejected alternatives

- **Keep module objects in `__all__` forever.** Blocks the planned `providers/`,
  `contracts/`, `tools/` reorganisation and keeps the `types` footgun.
- **Keep the dynamic comprehension and add a snapshot test only.** The test would
  be green while the API silently depends on import order; a future internal import
  can drop a module from `__all__` without touching the API declaration.
- **Add forwarding modules at every old submodule path.** Not needed at this stage:
  the project is pre-1.0 (`0.2.1`), submodule paths were never documented as
  supported API, and shims would permanently freeze the internal layout.

## Versioning note

This change lands while the distribution is `0.2.x` (pre-1.0). Removing accidental
module objects from `__all__` is treated as a minor-release cleanup, not a breaking
change to the documented symbol API. If the project reaches 1.0, this policy
continues: module paths remain implementation detail; symbol removals follow
semantic versioning and deprecation.
