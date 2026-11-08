"""MCP server configuration: parsing, merge, expansion, and write-back.

Ports pi's ``mcpServers`` handling
(``pi-main/packages/coding-agent/src/extensions/mcp/config.ts`` and
``pi-main/packages/mcp/src/config.ts``): a user file and a trusted project
file share the ``mcpServers`` shape, project entries replace or override user
entries, and ``/mcp on|off`` writes the decision back into the file that
defines the entry, preserving its formatting.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

ServerType = Literal["stdio", "http"]

# Collects one rejection diagnostic for the entry being validated.
_Reject = Callable[[str], None]

# Server names feed tool names and namespaces, so they stay within the same
# character class (pi: SERVER_NAME in packages/mcp/src/config.ts:107).
_SERVER_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
_ENV_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_INDENT = re.compile(r"^([ \t]+)\S", re.MULTILINE)

# A project entry without transport fields overrides only these keys of the
# user entry (pi: OVERRIDE_KEYS minus the exposure settings Baldric has not).
_OVERRIDE_KEYS = frozenset({"enabled"})

_KNOWN_ENTRY_KEYS = frozenset(
    {"type", "command", "args", "env", "cwd", "url", "headers", "enabled", "description", "timeout"}
)


@dataclass(frozen=True, slots=True)
class McpServerConfig:
    """One effective MCP server entry after merge and expansion."""

    name: str
    server_type: ServerType
    source: Path | None = None
    enabled: bool = True
    description: str | None = None
    timeout: float = 60.0
    command: str | None = None
    args: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    cwd: str | None = None
    url: str | None = None
    headers: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class McpConfigDiagnostic:
    """One configuration problem; ``name`` is empty for file-level problems."""

    path: str
    name: str
    message: str


@dataclass(frozen=True, slots=True)
class McpConfigLoadResult:
    """Parsed servers (including disabled ones) and the problems found."""

    servers: tuple[McpServerConfig, ...]
    diagnostics: tuple[McpConfigDiagnostic, ...]


def load_mcp_config(
    user_path: Path | None,
    project_path: Path | None,
    environment: Mapping[str, str],
) -> McpConfigLoadResult:
    """Load the user file and the (trusted) project file into effective entries.

    Project entries with the same name replace user entries; a project entry
    without ``command``/``url``/``type`` overrides only the user entry's
    ``enabled``. Names that would share a namespace cannot coexist: the first
    entry wins and later ones are rejected with a diagnostic (pi's rule).
    """
    servers: dict[str, McpServerConfig] = {}
    diagnostics: list[McpConfigDiagnostic] = []
    if user_path is not None:
        _read_file(user_path, environment, servers, diagnostics)
    if project_path is not None:
        _read_file(project_path, environment, servers, diagnostics)
    return McpConfigLoadResult(servers=tuple(servers.values()), diagnostics=tuple(diagnostics))


def set_server_enabled(path: Path, name: str, enabled: bool) -> None:
    """Persist ``/mcp on|off`` for one server into the file that defines it.

    The file's indentation and unrelated content are preserved (pi's
    ``editMcpServers``). A full entry gets the key deleted when ``enabled`` is
    the default ``True``; an override entry always carries the explicit value,
    because deleting it would drop the override. Raises ``ValueError`` when the
    file or the entry does not exist, or the file is malformed: writing back
    into a file we cannot parse must not silently rewrite it.
    """
    if not path.exists():
        raise ValueError(f'{path}: does not define MCP server "{name}"')
    text = path.read_text(encoding="utf-8-sig")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: {exc}") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("mcpServers", {}), dict):
        raise ValueError(f'{path}: expected an object with an "mcpServers" object')
    servers = parsed.setdefault("mcpServers", {})
    entry = servers.get(name)
    if not isinstance(entry, dict):
        raise ValueError(f'{path}: does not define MCP server "{name}"')

    if _is_override(entry):
        entry["enabled"] = enabled
    elif enabled:
        entry.pop("enabled", None)
    else:
        entry["enabled"] = False

    indent = _INDENT.search(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    written = json.dumps(parsed, indent=indent.group(1) if indent else "  ", ensure_ascii=False)
    path.write_text(written + "\n", encoding="utf-8")


def _read_file(
    path: Path,
    environment: Mapping[str, str],
    servers: dict[str, McpServerConfig],
    diagnostics: list[McpConfigDiagnostic],
) -> None:
    if not path.exists():
        return
    try:
        parsed = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        diagnostics.append(McpConfigDiagnostic(path=str(path), name="", message=str(exc)))
        return
    if not isinstance(parsed, dict):
        diagnostics.append(McpConfigDiagnostic(path=str(path), name="", message="expected a JSON object"))
        return
    raw_servers = parsed.get("mcpServers")
    if raw_servers is not None and not isinstance(raw_servers, dict):
        diagnostics.append(
            McpConfigDiagnostic(path=str(path), name="", message='expected "mcpServers" to be an object')
        )
        return
    for key in parsed:
        if key != "mcpServers":
            diagnostics.append(
                McpConfigDiagnostic(path=str(path), name="", message=f'unknown top-level key "{key}"')
            )
    for name, raw in (raw_servers or {}).items():
        _read_entry(path, name, raw, environment, servers, diagnostics)


def _read_entry(
    path: Path,
    name: str,
    raw: object,
    environment: Mapping[str, str],
    servers: dict[str, McpServerConfig],
    diagnostics: list[McpConfigDiagnostic],
) -> None:
    def reject(message: str) -> None:
        diagnostics.append(McpConfigDiagnostic(path=str(path), name=name, message=message))

    if not isinstance(raw, dict):
        reject("entry must be an object")
        return

    # A project entry without transport fields overrides the user entry's
    # enabled flag only (pi: isMcpServerOverride). Anything else it carries is
    # a mistake the user must fix in the file that owns the server.
    if _is_override(raw):
        base = servers.get(name)
        if base is None:
            reject('needs "command" or "url", or a user server to override')
            return
        extra = sorted(set(raw) - _OVERRIDE_KEYS)
        if extra:
            reject(f"an override can only set {sorted(_OVERRIDE_KEYS)}; found {extra}")
            return
        enabled = raw.get("enabled", True)
        if not isinstance(enabled, bool):
            reject("enabled must be a boolean")
            return
        servers[name] = replace(base, enabled=enabled, source=path)
        return

    config = _validate_entry(name, raw, path, environment, reject)
    if config is None:
        return
    clash = next(
        (other for other in servers if other != name and _namespace(other) == _namespace(name)), None
    )
    if clash is not None:
        reject(f'conflicts with "{clash}": their namespaces collide')
        return
    servers[name] = config


def _validate_entry(
    name: str,
    raw: dict[str, object],
    path: Path,
    environment: Mapping[str, str],
    reject: _Reject,
) -> McpServerConfig | None:
    """Validate one full entry and expand its values; ``None`` means rejected."""
    if not _SERVER_NAME.fullmatch(name):
        reject(f'invalid server name "{name}" (use letters, digits, "_" and "-")')
        return None

    unknown = sorted(set(raw) - _KNOWN_ENTRY_KEYS)
    if unknown:
        # Forward compatibility with other MCP clients' extra fields.
        reject(f"unknown field(s) {unknown} (ignored)")

    enabled = raw.get("enabled", True)
    description = raw.get("description")
    timeout = raw.get("timeout", 60.0)
    if not isinstance(enabled, bool):
        reject("enabled must be a boolean")
        return None
    if description is not None and not isinstance(description, str):
        reject("description must be a string")
        return None
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        reject("timeout must be a positive number of seconds")
        return None

    command = raw.get("command")
    url = raw.get("url")
    server_type = raw.get("type")
    if server_type is not None and server_type not in ("stdio", "http", "streamable-http"):
        reject('type must be "stdio" or "http"')
        return None
    if server_type == "stdio" and not isinstance(command, str):
        reject('type "stdio" requires "command"')
        return None
    if server_type in ("http", "streamable-http") and not isinstance(url, str):
        reject('type "http" requires "url"')
        return None
    if isinstance(command, str) and isinstance(url, str):
        reject('define either "command" (stdio) or "url" (http), not both')
        return None

    if isinstance(url, str):
        return _http_config(name, raw, url, path, enabled, description, float(timeout), environment, reject)
    if isinstance(command, str):
        return _stdio_config(
            name, raw, command, path, enabled, description, float(timeout), environment, reject
        )
    reject('needs either "command" (stdio) or "url" (http)')
    return None


def _http_config(
    name: str,
    raw: dict[str, object],
    url: str,
    path: Path,
    enabled: bool,
    description: str | None,
    timeout: float,
    environment: Mapping[str, str],
    reject: _Reject,
) -> McpServerConfig | None:
    headers = raw.get("headers", {})
    if not _is_string_record(headers):
        reject("headers must map names to strings")
        return None
    header_map = dict(headers) if isinstance(headers, dict) else {}
    expanded, unresolvable = _expand_env(url, environment)
    expanded_headers: dict[str, str] = {}
    for key, value in header_map.items():
        value_headers, missing = _expand_env(value, environment)
        expanded_headers[key] = value_headers
        unresolvable |= missing
    if unresolvable:
        reject(f"unresolvable ${{VAR}}: {sorted(unresolvable)} (entry disabled)")
    return McpServerConfig(
        name=name,
        server_type="http",
        source=path,
        enabled=False if unresolvable else enabled,
        description=description,
        timeout=timeout,
        url=expanded,
        headers=expanded_headers,
    )


def _stdio_config(
    name: str,
    raw: dict[str, object],
    command: str,
    path: Path,
    enabled: bool,
    description: str | None,
    timeout: float,
    environment: Mapping[str, str],
    reject: _Reject,
) -> McpServerConfig | None:
    args = raw.get("args")
    env = raw.get("env")
    cwd = raw.get("cwd")
    if args is not None and (not isinstance(args, list) or not all(isinstance(arg, str) for arg in args)):
        reject("args must be an array of strings")
        return None
    if env is not None and not _is_string_record(env):
        reject("env must map names to strings")
        return None
    if cwd is not None and not isinstance(cwd, str):
        reject("cwd must be a string")
        return None

    expanded_command, unresolvable = _expand_env(command, environment)
    expanded_env: dict[str, str] = {}
    for key, value in (dict(env) if isinstance(env, dict) else {}).items():
        value_env, missing = _expand_env(value, environment)
        expanded_env[key] = value_env
        unresolvable |= missing
    expanded_cwd = None
    if cwd is not None:
        expanded_cwd, missing = _expand_env(cwd, environment)
        unresolvable |= missing
    if unresolvable:
        reject(f"unresolvable ${{VAR}}: {sorted(unresolvable)} (entry disabled)")
    return McpServerConfig(
        name=name,
        server_type="stdio",
        source=path,
        enabled=False if unresolvable else enabled,
        description=description,
        timeout=timeout,
        command=_expand_home(expanded_command),
        args=tuple(_expand_home(arg) for arg in args) if args is not None else (),
        env=expanded_env,
        cwd=None if expanded_cwd is None else _expand_home(expanded_cwd),
    )


def _is_override(entry: dict[str, object]) -> bool:
    """A project entry without transport fields (pi: packages/mcp/src/config.ts:241)."""
    return "command" not in entry and "url" not in entry and "type" not in entry


def _namespace(server: str) -> str:
    """Namespace of a server's tools (pi: packages/mcp/src/naming.ts:33)."""
    return f"mcp__{server.replace('-', '_')}"


def _is_string_record(value: object) -> bool:
    return isinstance(value, dict) and all(isinstance(item, str) for item in value.values())


def _expand_env(value: str, environment: Mapping[str, str]) -> tuple[str, set[str]]:
    """Expand ``${VAR}`` against ``environment``; return the text and misses."""
    missing: set[str] = set()

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in environment:
            return environment[name]
        missing.add(name)
        return match.group(0)

    return _ENV_VAR.sub(substitute, value), missing


def _expand_home(value: str) -> str:
    """Expand ``~`` and ``~/…`` (and ``~\\…``) against the user home."""
    if value == "~":
        return str(Path.home())
    if value.startswith("~/") or value.startswith("~\\"):
        return str(Path.home() / value[2:])
    return value
