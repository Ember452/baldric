---
title: CLI reference
description: Every Baldric command-line command and flag.
---

The `baldric` command launches the interactive TUI by default; subcommands and flags
cover everything else.

```text
baldric [OPTIONS] [PROMPT] [COMMAND] [ARGS]
```

- With no arguments, `baldric` opens the interactive [TUI](/how-to/tui/).
- A positional `PROMPT` opens the TUI and submits it as the first turn.
- `/local` is available in the TUI for registered local backends; print mode reports that setup is interactive-only.
- `-p/--print` (or `--mode`) runs that same positional prompt in [print mode](/how-to/print-mode/) instead of the TUI.
- Put flags before the prompt — Baldric treats everything after the last recognized flag as prompt text, including tokens that look like flags.

On TUI and text print-mode startup, Baldric may show a non-blocking notice when a
newer `baldric` release is available on PyPI. In the TUI, a cached result is the
first transcript item and appears in bright yellow; when the daily check is due,
it runs in the background after the TUI opens and the notice is added once PyPI
answers. Run `baldric update` to upgrade. Disable
the check with `BALDRIC_NO_UPDATE_CHECK=1`; utility commands such as `baldric --version`,
`baldric update`, `baldric sessions`, and `baldric export` do not run it. After an upgrade,
the TUI also adds a one-time release-notes message to the transcript with the new
features and fixes.

## Commands

| Command | What it does |
| --- | --- |
| `baldric` | Open the interactive TUI |
| `baldric "<prompt>"` | Open the TUI with an initial prompt |
| `baldric update` | Upgrade Baldric with the installer that owns its environment. Windows uv-tool updates are handed off and begin after Baldric exits; follow the printed log path for the final result. |
| `baldric update --models` | Force-refresh models.dev catalogs and cache them in `~/.baldric/models-store.json` without upgrading Baldric. |
| `baldric install <source> [--force]` | Install a trusted local or Git extension under `~/.baldric/extensions/`; `--force` replaces an existing install. |
| `baldric sessions` | List indexed sessions (id, title, model, cwd) |
| `baldric export <ref> [dest] [--format html\|jsonl]` | Export a session id or JSONL path (HTML default) |
| `baldric --export <ref> [dest]` | Same as `baldric export`, as a top-level flag |
| `baldric providers` | List configured providers and how each authenticates |
| `baldric [setup options] setup` | Create/update an OpenAI-compatible provider |

## Options

| Flag | Description |
| --- | --- |
| `-p, --print` | Run the positional prompt in non-interactive print mode |
| `-m, --model TEXT` | Model to request from the provider |
| `--provider TEXT` | Configured provider name to use |
| `-t, --thinking LEVEL` | Initial [thinking level](/how-to/context/#thinking-modes) for this run (`off`…`max`); overrides remembered defaults without persisting, errors if the model doesn't support it |
| `--cwd PATH` | Working directory for the built-in tools |
| `--mode [text\|json\|transcript\|rpc]` | Select headless output; `rpc` starts the JSONL subprocess protocol |
| `--session TEXT` | Resume a session id in the TUI or print mode |
| `--new-session` | Start a new session instead of resuming the default |
| `--session-id TEXT` | Set the exact id for a newly created print-mode session; errors if it already exists |
| `--system-prompt TEXT_OR_PATH` | Replace Baldric's default system-prompt base with literal text or an existing UTF-8 file |
| `--append-system-prompt TEXT_OR_PATH` | Append literal text or an existing UTF-8 file (repeatable) |
| `--auto-compact-threshold INT` | Auto-compact above this rough token estimate |
| `-e, --extension PATH` | Load an [extension](/how-to/extensions/) file or directory (repeatable) |
| `--no-extensions` | Disable extension directory discovery (explicit `-e` paths still load) |
| `--project-extensions` | Also load trusted `<project>/.baldric/extensions`; project trust and this code opt-in are both required |
| `--show-full-output` | Start the TUI with untruncated tool and `!`-command output instead of previews; **Ctrl+O** toggles the same at runtime |
| `-a, --approve` | Trust protected project inputs for this invocation only |
| `-na, --no-approve` | Decline protected project inputs for this invocation only |
| `-v, --version` | Print the version and exit |

`baldric install` accepts local Python files, local package directories, Pi-style
`git:github.com/owner/repository[@ref]` sources, and normal HTTP/SSH Git URLs.
See [Extensions](/how-to/extensions/#install-an-extension)
for package-layout, dependency, and security details.

`--approve` and `--no-approve` are mutually exclusive and never write the
trust store. See [Project trust](/how-to/project-trust/)
for interactive scopes, headless defaults, protected resources, and the
non-sandbox boundary.

### System prompt input

`--system-prompt` replaces Baldric's default base prompt. Repeat
`--append-system-prompt` to add sections in command-line order; Baldric separates each
resolved value with exactly one blank line. Put these flags before the positional
prompt, like other recognized options:

```bash
baldric --system-prompt "You are a focused reviewer." \
  --append-system-prompt ./team-rules.md \
  --append-system-prompt "Report risky changes first." \
  -p "review this repository"
```

For either option, Baldric reads the value as a UTF-8 file when that path exists.
Otherwise it uses the value verbatim, so a nonexistent path is literal prompt
text. Existing directories, unreadable files, and invalid UTF-8 files stop
startup with an error naming the option and path. `~` is expanded when checking
for a file.

A custom base still receives appended text, discovered project instructions,
eligible skills when the `read` tool is enabled, the current date, and the
working directory. The options apply to print mode and interactive startup;
when used with `--session`, they configure the resumed session's next provider
request. They are startup controls and are not stored in session history, so
pass them again on a later resume when needed.

Baldric also discovers `SYSTEM.md` and `APPEND_SYSTEM.md` under the project or user
`.baldric` directory. A CLI replacement wins over trusted project and user
`SYSTEM.md` files. Append content is cumulative: user `APPEND_SYSTEM.md`, then
trusted project `APPEND_SYSTEM.md`, then repeated CLI values. Use `/reload` after
changing a file. These are Baldric-specific configuration files, not `.agents`
resources. See
[Configuration & files](/reference/configuration/#system-prompt-files)
for paths, precedence, diagnostics, and the project-resource security warning.

### Resume in print mode

Use `--print` and `--session` together to append a non-interactive follow-up to
an existing conversation. Baldric loads the session's saved working directory,
provider, model, and conversation history:

```bash
baldric --print --session <session-id> "Follow-up message"
```

Explicit `--provider`, `--model`, and system-prompt options override the saved
startup choices for this invocation. After configuring a local backend in the
TUI, pass its provider and exact discovered model explicitly in print mode:

```bash
baldric --provider llama.cpp --model <model-id> --print "summarize this project"
```

Baldric does not run `/local` setup or select a model implicitly headlessly. An
endpoint-keyed safe snapshot can let an explicit local startup continue while
llama.cpp is temporarily down; a first-time explicit model still needs discovery.
`--session` cannot be combined with
`--new-session` or `--session-id`. An unknown session id exits with an error.

`--resume`, `--prompt`, `-o/--output`, and `-x` are removed; each now exits
with an error naming its replacement (`--session`, `--print`, `--mode`, and
`-e/--extension`, respectively).

### Provider setup options

Baldric's setup mode registers an OpenAI-compatible provider. Put these flags before the final `setup` argument:

| Flag | Default | Description |
| --- | --- | --- |
| `--provider TEXT` | `openai` | Provider name to create/update |
| `--model TEXT` | default model | Default model for the provider |
| `--base-url TEXT` | OpenAI URL | OpenAI-compatible base URL |
| `--api-key-env TEXT` | `OPENAI_API_KEY` | Env var holding the API key |
| `--timeout-seconds FLOAT` | `60.0` | HTTP timeout |
| `--max-retries INT` | `2` | Retry count for transient failures |
| `--max-retry-delay-seconds FLOAT` | `1.0` | Delay between retries |
| `--set-default / --no-set-default` | set-default | Make this the default provider |

Example:

```bash
baldric --provider local \
  --base-url http://localhost:11434/v1 \
  --api-key-env LOCAL_API_KEY \
  --model qwen \
  setup
```

See also: [RPC protocol](/reference/rpc/), [Slash commands](/reference/slash-commands/) (in-session), and
[Keyboard shortcuts](/reference/keybindings/).
