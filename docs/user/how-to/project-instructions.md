---
title: Project instructions (AGENTS.md)
description: Give Baldric standing instructions about your project with AGENTS.md files.
---

An **`AGENTS.md`** file is how you give the agent durable, project-specific
context: conventions to follow, commands to run, things to avoid. Baldric discovers
these files automatically and includes them in the system prompt for every turn,
wrapped in `<project_context>` tags.

## What to put in it

Anything you'd otherwise repeat to the agent every session:

- how to run tests, lint, build, and format
- project conventions (style, commit message format, branch naming)
- architectural notes and gotchas
- "always do X / never do Y" rules

Keep it focused — it's part of the prompt budget for every turn.

## Where Baldric looks

Baldric discovers instruction files in this order. User files are always eligible;
project files are included only after the active cwd's [project-trust decision]
(/how-to/project-trust/):

```text
~/.baldric/AGENTS.md
~/.agents/AGENTS.md
<project root>/AGENTS.md
<project root>/.../<cwd>/AGENTS.md   # ancestor dirs between root and cwd
<cwd>/.baldric/AGENTS.md
<cwd>/.agents/AGENTS.md
```

The **project root** is the nearest ancestor directory containing a marker such
as `.git`, `pyproject.toml`, `uv.lock`, `setup.py`, or `package.json`.

This layering lets you keep personal global instructions in `~/.baldric/` or
`~/.agents/`, project-wide rules in the repo's `AGENTS.md`, and narrower rules in
a subdirectory closer to where you're working.

## Reloading after edits

If you change an `AGENTS.md` while the TUI is open, run **`/reload`** to refresh
project context for future turns. Adding the first protected file to an empty
project triggers trust resolution rather than silently inheriting the old empty
snapshot.

> [!NOTE]
> Baldric itself uses an `AGENTS.md` at the repo root — a real example of the format
> in practice.
