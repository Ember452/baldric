---
title: MCP servers
description: Connect MCP servers so their tools appear alongside Baldric's built-in tools.
---

**MCP** (Model Context Protocol) is an open standard for exposing tools to AI
agents. Baldric is an MCP **client**: servers you configure contribute tools
that appear next to the built-in ones, with no special prompting.

## Configuring servers

Baldric reads an `mcp.json` from two places:

- **User level**: `~/.baldric/mcp.json` — your servers, available everywhere.
- **Project level**: `<project>/.baldric/mcp.json` — loaded only when the
  project is [trusted](/how-to/project-trust/). A project entry with the same
  name replaces the user entry; an entry with only `"enabled"` overrides just
  that switch (handy for turning a global server off in one repository).

Both use the same shape as Claude Desktop and other MCP clients, so existing
configurations can be copied over:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
      "cwd": "~"
    },
    "docs": {
      "url": "https://docs.example.com/mcp",
      "headers": { "Authorization": "Bearer ${DOCS_TOKEN}" }
    }
  }
}
```

| Field | Applies to | Meaning |
| --- | --- | --- |
| `command`, `args`, `env`, `cwd` | stdio servers | Spawn a local program that speaks MCP over stdin/stdout |
| `url`, `headers` | Streamable HTTP servers | Connect to a remote endpoint |
| `type` | both | Optional (`"stdio"` or `"http"`); inferred from `command`/`url` when absent, and validated when it disagrees |
| `timeout` | both | Per-call timeout in seconds (default 60); progress notifications reset it |
| `description` | both | One line describing the server, shown in the system prompt |
| `enabled` | both | `false` keeps the entry without connecting |

Values in `env`, `headers`, `command`, and `cwd` may reference environment
variables as `${NAME}` — expanded against the environment Baldric runs in.
Unresolvable variables produce a warning and the entry starts disabled. `~`
expands to your home directory in `command` and `cwd`.

## Managing servers: `/mcp`

```text
/mcp                    # list servers: name, state, transport, tool count
/mcp restart <name>     # re-read the config and reconnect one server
/mcp off <name>         # disable a server for this project/user
/mcp on <name>          # enable it again
```

`on` and `off` write the decision back into the `mcp.json` that defines the
server (your choice is remembered across sessions), then connect or close it
immediately.

## Tool naming

MCP tools appear as ordinary tools named `mcp__<server>__<tool>` — for
example `mcp__filesystem__read_file`. Names are sanitized to letters, digits,
and underscores; if that would overflow the 64-character limit or collide with
another tool, a short hash suffix keeps names unique. The same naming rules
other MCP clients use, so tools rank and group consistently.

## States and reconnection

Each server moves through `connecting`, `connected`, `disconnected`,
`needs-auth`, `failed`, or `closed`:

- Your first message waits briefly (up to 10 seconds) for connecting servers,
  so their tools are actually callable; startup itself is never delayed.
- A dropped connection (say, the server process exited) is marked
  `disconnected`; the next tool call reconnects automatically.
- A server that fails to start is marked `failed` and its tools are withdrawn
  until it connects again — the rest of the session keeps working.
- An HTTP server that answers 401 is marked `needs-auth`. Baldric's MVP does
  not include MCP OAuth; use a header with a credential instead.

## Known limits

- No MCP OAuth, resources, prompts, or sampling — tools only.
- Only text and images are surfaced from tool results: images become
  `[image: mime, N bytes]` placeholders and other content blocks (embedded
  resources, audio) become `[unsupported content block: …]`.
- `${NAME}` expansion is supported; pi's `!command` shell substitution is
  deliberately not (running shells while parsing config is out of scope).
- Servers that add tools after connecting keep their connect-time tool set
  until you run `/mcp restart <name>`.
- Subagent child sessions do not get MCP: each child spawning its own server
  processes would be waste. Parent sessions share MCP tools with children
  through delegation instead.
