# Baldric documentation

Baldric is a minimalist Python coding-agent harness inspired by Pi. Use these installed references when a user asks how to configure, extend, or contribute to Baldric.

Baldric's user-data home defaults to `~/.baldric`. Set `BALDRIC_HOME` to a non-empty
absolute path (after `~` expansion) to select another home. All `~/.baldric` paths
in these references follow that override; `~/.agents` and project `.baldric`
resources remain separate.

- [Extensions](extensions.md): build Python extensions, custom tools, commands, hooks, dialogs, and renderers.
- [Skills](skills.md): install reusable task knowledge and prompt templates.
- [Models](models.md): configure providers and models, including local inference.
- [Local inference](local-inference.md): configure the built-in llama.cpp backend through `/local`.
- [CLI](cli.md): command-line and slash-command entry points.
- [Security](security.md): project-input trust behavior and local-backend boundaries.
- [TUI](tui.md): interactive interface behavior, including `/local`.
- [Architecture](architecture.md): package boundaries and contributor design rules.

Read only the references relevant to the task, then follow their links and the active project's instructions.
