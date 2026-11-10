---
title: Quickstart
description: Install Baldric, connect a model, and run your first coding session.
type: doc
---

This page takes you from nothing to your first Baldric session. It should take a few
minutes.

## 1. Install Baldric

Baldric is a Python tool requiring Python 3.12 or newer. Its installer uses
[`uv`](https://docs.astral.sh/uv/) to create an isolated environment and installs
`uv` first when it is not already available.

On macOS or Linux, run:

```bash
curl -LsSf https://ember452.github.io/baldric/install.sh | sh
```

On Windows, run in PowerShell:

```powershell
irm https://ember452.github.io/baldric/install.ps1 | iex
```

The installer announces before installing `uv`, never uses `sudo`, verifies the
installed `baldric` command, and tells you if you need to restart your shell for a
`PATH` update. To review code before executing it, download and inspect
[`install.sh`](/install.sh) or [`install.ps1`](/install.ps1) first.

Check it worked:

```bash
baldric --version
```

> [!TIP] Already have a package manager?
> Install Baldric directly with `uv tool install baldric`, `pipx install baldric`, or
> `python -m pip install baldric`.

### Upgrade Baldric

For a normal install, let Baldric detect and reuse the installer that owns its environment:

```bash
baldric update
```

Baldric reuses uv or pipx when their environment receipt is present. For uv tools,
it installs the latest stable version explicitly so an older version pin cannot
block the update. For ordinary Python installs, standard package metadata tells
Baldric whether to use uv or pip, and Baldric targets the exact Python environment
running it. It stops instead of
switching installers for editable, direct-URL, Conda/Pixi, or unrecognized
installations.

If you installed a local checkout with `uv tool install --editable .`, run the
install command again after pulling changes:

```bash
uv tool install --editable --force .
```

Editable installs expose source changes immediately, but installed package
metadata (including the version), dependencies, and entry points are refreshed
only when uv reinstalls the tool.

## 2. Connect a model

Baldric needs an AI model to talk to. A **provider** is the service that hosts the
model (OpenAI, Anthropic, …). Start Baldric and use `/login` to connect one:

```bash
baldric
```

Then run one of these inside Baldric:

```text
/login              # choose a provider
/login openai       # save an OpenAI API key
/login openai-codex # authenticate a Codex/ChatGPT subscription
```

Baldric ships with built-in entries for OpenAI, Anthropic, OpenAI Codex,
OpenRouter, and Hugging Face. See [Providers & models](/how-to/providers-and-models/)
for switching models or adding a custom/local OpenAI-compatible endpoint.

## 3. Start a session

Run Baldric from inside the project you want to work on:

```bash
cd my-project
baldric
```

This opens the interactive terminal UI. Type a request and press **Enter**:

```text
explain what this project does
```

Baldric streams its response, and when it needs to, it reads files and runs commands
to answer you. Try something that changes code:

```text
add a docstring to every function in src/utils.py
```

You'll see each tool call (read, edit, bash) as it happens.

> [!TIP] Useful first keys
> **Enter** submits · **Esc** cancels the current run · **Ctrl+K** opens the
> command palette · **Ctrl+D** quits. Full list in
> [Keyboard shortcuts](/reference/keybindings/).

## 4. Come back later

Baldric saves every session. List them:

```bash
baldric sessions
```

Resume the most recent one for this directory, or pick from a list:

```bash
baldric --session <session-id>
```

…or open the picker inside the TUI with `/resume`. See
[Sessions](/how-to/sessions/) for resuming, branching, and exporting.

## One-shot mode

Don't need the UI? Run a single prompt and get the result on stdout — handy for
scripts and pipes:

```bash
baldric -p "summarize the changes in the last commit"
```

More in [Print mode & scripting](/how-to/print-mode/).

## Where to go next

- **[Core concepts](/explanation/concepts/)** — understand what's actually happening.
- **[The interactive session](/how-to/tui/)** — get fluent in the TUI.
- **[Providers & models](/how-to/providers-and-models/)** — switch models,
  add providers, use local models.
