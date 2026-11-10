# Baldric documentation

This directory is the single source of truth for Baldric documentation.

## Start here

- New to Baldric: [tutorials/quickstart.md](user/tutorials/quickstart.md)
- What Baldric is and why: [explanation/what-is-baldric.md](user/explanation/what-is-baldric.md)
- Task recipes: [user/how-to/](user/how-to/_index.md)
- Lookup: [user/reference/](user/reference/_index.md)
- How Baldric works: [user/explanation/](user/explanation/_index.md)

## Map

| Directory | Audience | Contents |
| --- | --- | --- |
| `user/` | people using Baldric | published guides, reference, and explanations |
| `internal/` | contributors | ADRs, architecture journals, designs, notes, plans, specs |
| `assets/` | repository README and docs | images and diagrams |
| `templates/` | contributors | ADR, design, and plan starting points |

## For contributors

- Documentation standard: [AGENTS.md](AGENTS.md)
- Decisions: [internal/adr/](internal/adr/)
- Architecture journals: [internal/architecture/](internal/architecture/)
- Designs: [internal/design/](internal/design/)
- Feature notes: [internal/notes/](internal/notes/)
- Plans and specs: [internal/plans/](internal/plans/), [internal/specs/](internal/specs/)

## Published site

`docs/user/` is the Astro content base configured in `website/src/content.config.ts`.
`docs/internal/`, `docs/templates/`, and `docs/assets/` are never published.

Packaged self-knowledge in `src/baldric/runtime/data/docs/` ships inside the wheel
and is read by the agent at runtime; it is intentionally separate from this tree.
