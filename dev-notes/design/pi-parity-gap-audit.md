# Pi-parity gap audit: orphan commands and RPC framing

A review flagged three suspected gaps against Pi. Each was verified against the
code before changing anything; two were real and one needed a scoping
correction.

## 1. Orphaned command handlers

`_thinking_command` (`commands/config.py`), `_context_command`
(`commands/resources.py`), and `_help_command` (`commands/core.py`) were
implemented and unit-covered but never imported or registered, so
`/thinking`, `/context`, and `/help` behaved as unknown commands.

Resolution:

- **`/thinking` is registered.** Pi has it (`/thinking [level]`), the handler
  handles status, set, unavailable-model, and invalid-level cases, and the TUI
  already consumes `CommandResult.thinking_level`.
- **`/context` and `/help` stay unregistered.** `test_non_pi_commands_are_not_registered`
  deliberately asserts that `/provider`, `/resources`, `/context`, and `/help`
  are not part of the Pi-aligned command set. Registering them would be a
  product decision to diverge from Pi, not a bug fix. Their handlers remain
  unused code; removing them is a separate cleanup that should come with that
  decision.

## 2. Configuration surface

`settings.json` (`config/shell_config.py`) only carries `defaultProjectTrust`
and `shellCommandPrefix`; `tui.json` carries keybindings, theme, sidebar
position, notification mode, auto-copy, and the editor command. Compared with
Pi's settings/keybindings/models/auth files, the coverage is comparable once
`providers.json` and the credential store are counted. The real gap is **MCP**:
Baldric has no MCP client at all, so there is no `mcp.json` because there is no
MCP support. That is a feature, not a configuration-schema difference, and is
out of scope for parity fixes.

## 3. RPC framing on Windows

Suspicion: Windows CRLF could break Pi's byte-level LF framing, and tests only
used in-memory streams. Verified against the code and then against a real
text stream:

- **Read side was already safe.** `RpcServer.run` strips a trailing `\n` and
  then a trailing `\r`, so CRLF peers parse correctly.
- **Write side was not.** `stdout` is a text stream with `newline=None`, so on
  Windows `payload + "\n"` is written as `\r\n`. A byte-level peer sees a
  carriage return that the protocol does not define.
- **A second, unreported problem existed:** `_force_utf8_streams` reconfigures
  only stdout/stderr, so Windows `stdin` keeps the system code page and
  non-ASCII JSON could fail to decode.

Fix: `_configure_rpc_stream` forces UTF-8 on both streams and `newline="\n"` on
output, called at the start of `run()`. Streams without `reconfigure` (test
doubles) are untouched.

New coverage in `tests/coding/cli/test_rpc_streams.py` wraps `BytesIO` in
`TextIOWrapper` with platform defaults (`newline=None`, `cp1252`) to reproduce
both behaviours. The LF test was proven to fail when the fix is removed, so it
guards the behavior rather than merely exercising it.
