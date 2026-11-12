"""Tests for ``baldric.mcp.config``: parsing, merge, expansion, write-back."""

from __future__ import annotations

import json
from pathlib import Path

from baldric.mcp.config import load_mcp_config, set_server_enabled

ENV = {"CMD": "run", "TOKEN": "secret", "DIR": "/tmp/d"}


def _write(path: Path, payload: object, *, indent: int | None = 2) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=indent), encoding="utf-8")
    return path


def _write_raw(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _server(result: object, name: str) -> object:
    servers = result.servers  # type: ignore[attr-defined]
    return next(server for server in servers if server.name == name)


def test_load_without_files_returns_empty(tmp_path: Path) -> None:
    result = load_mcp_config(None, None, ENV)

    assert result.servers == ()
    assert result.diagnostics == ()


def test_stdio_entry_parses(tmp_path: Path) -> None:
    user = _write(
        tmp_path / "user.json",
        {"mcpServers": {"fs": {"command": "npx", "args": ["-y", "srv"], "env": {"K": "v"}, "cwd": "/w"}}},
    )

    result = load_mcp_config(user, None, ENV)
    server = _server(result, "fs")

    assert server.server_type == "stdio"
    assert server.command == "npx"
    assert server.args == ("-y", "srv")
    assert dict(server.env) == {"K": "v"}
    assert server.cwd == "/w"
    assert server.enabled is True
    assert server.timeout == 60.0
    assert server.source == user
    assert result.diagnostics == ()


def test_http_entry_parses(tmp_path: Path) -> None:
    user = _write(
        tmp_path / "user.json",
        {
            "mcpServers": {
                "docs": {"url": "https://example.com/mcp", "headers": {"Authorization": "Bearer t"}}
            }
        },
    )

    result = load_mcp_config(user, None, ENV)
    server = _server(result, "docs")

    assert server.server_type == "http"
    assert server.url == "https://example.com/mcp"
    assert dict(server.headers) == {"Authorization": "Bearer t"}
    assert result.diagnostics == ()


def test_explicit_type_must_match_fields(tmp_path: Path) -> None:
    user = _write(
        tmp_path / "user.json",
        {
            "mcpServers": {
                "bad": {"type": "http", "command": "x"},
                "good": {"type": "stdio", "command": "x"},
            }
        },
    )

    result = load_mcp_config(user, None, ENV)

    assert [server.name for server in result.servers] == ["good"]
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].name == "bad"


def test_both_and_neither_fields_are_rejected(tmp_path: Path) -> None:
    user = _write(
        tmp_path / "user.json",
        {"mcpServers": {"both": {"command": "x", "url": "https://a/mcp"}, "empty": {"description": "d"}}},
    )

    result = load_mcp_config(user, None, ENV)

    assert result.servers == ()
    assert {diagnostic.name for diagnostic in result.diagnostics} == {"both", "empty"}


def test_unknown_field_warns_but_loads(tmp_path: Path) -> None:
    user = _write(tmp_path / "user.json", {"mcpServers": {"x": {"command": "x", "bogus": 1}}})

    result = load_mcp_config(user, None, ENV)

    assert len(result.servers) == 1
    assert len(result.diagnostics) == 1
    assert "bogus" in result.diagnostics[0].message


def test_env_var_expansion(tmp_path: Path) -> None:
    user = _write(
        tmp_path / "user.json",
        {
            "mcpServers": {
                "s": {
                    "command": "${CMD}",
                    "env": {"K": "${TOKEN}"},
                    "cwd": "${DIR}",
                },
                "h": {"url": "https://a/mcp", "headers": {"Authorization": "Bearer ${TOKEN}"}},
            }
        },
    )

    result = load_mcp_config(user, None, ENV)

    stdio = _server(result, "s")
    http = _server(result, "h")
    assert stdio.command == "run"
    assert dict(stdio.env) == {"K": "secret"}
    assert stdio.cwd == "/tmp/d"
    assert dict(http.headers) == {"Authorization": "Bearer secret"}


def test_unresolvable_env_var_disables_entry(tmp_path: Path) -> None:
    user = _write(tmp_path / "user.json", {"mcpServers": {"x": {"command": "${MISSING}"}}})

    result = load_mcp_config(user, None, ENV)

    server = _server(result, "x")
    assert server.enabled is False
    assert any("MISSING" in diagnostic.message for diagnostic in result.diagnostics)


def test_home_expansion(tmp_path: Path) -> None:
    home = Path.home()
    user = _write(
        tmp_path / "user.json",
        {
            "mcpServers": {
                "a": {"command": "~/tool", "args": ["~/arg", "--plain"]},
                "b": {"command": "run", "cwd": "~"},
            }
        },
    )

    result = load_mcp_config(user, None, ENV)

    assert _server(result, "a").command == str(home / "tool")
    assert _server(result, "a").args == (str(home / "arg"), "--plain")
    assert _server(result, "b").cwd == str(home)


def test_project_entry_replaces_user(tmp_path: Path) -> None:
    user = _write(tmp_path / "user.json", {"mcpServers": {"x": {"command": "user-cmd"}}})
    project = _write(tmp_path / "project.json", {"mcpServers": {"x": {"command": "project-cmd"}}})

    result = load_mcp_config(user, project, ENV)

    assert len(result.servers) == 1
    server = _server(result, "x")
    assert server.command == "project-cmd"
    assert server.source == project


def test_project_override_merges(tmp_path: Path) -> None:
    user = _write(tmp_path / "user.json", {"mcpServers": {"x": {"command": "keep", "args": ["a"]}}})
    project = _write(tmp_path / "project.json", {"mcpServers": {"x": {"enabled": False}}})

    result = load_mcp_config(user, project, ENV)

    server = _server(result, "x")
    assert server.enabled is False
    assert server.command == "keep"
    assert server.args == ("a",)
    assert server.source == project


def test_override_rejections(tmp_path: Path) -> None:
    user = _write(tmp_path / "user.json", {"mcpServers": {"x": {"command": "keep"}}})
    project = _write(
        tmp_path / "project.json",
        {"mcpServers": {"x": {"enabled": False, "args": ["extra"]}, "orphan": {"enabled": False}}},
    )

    result = load_mcp_config(user, project, ENV)

    server = _server(result, "x")
    assert server.enabled is True  # the bad override did not apply
    assert {diagnostic.name for diagnostic in result.diagnostics} == {"x", "orphan"}


def test_namespace_clash_first_entry_wins(tmp_path: Path) -> None:
    user = _write(tmp_path / "user.json", {"mcpServers": {"a-b": {"command": "x"}, "a_b": {"command": "y"}}})

    result = load_mcp_config(user, None, ENV)

    assert [server.name for server in result.servers] == ["a-b"]
    clash = [diagnostic for diagnostic in result.diagnostics if diagnostic.name == "a_b"]
    assert len(clash) == 1
    assert "a-b" in clash[0].message


def test_malformed_files(tmp_path: Path) -> None:
    user = _write_raw(tmp_path / "user.json", "{not json")
    project = _write_raw(tmp_path / "project.json", "[1, 2]")

    result = load_mcp_config(user, project, ENV)

    assert result.servers == ()
    assert len(result.diagnostics) == 2
    assert all(diagnostic.name == "" for diagnostic in result.diagnostics)


def test_disabled_servers_are_listed(tmp_path: Path) -> None:
    user = _write(tmp_path / "user.json", {"mcpServers": {"x": {"command": "x", "enabled": False}}})

    result = load_mcp_config(user, None, ENV)

    assert _server(result, "x").enabled is False


def test_set_server_enabled_round_trip(tmp_path: Path) -> None:
    user = _write_raw(
        tmp_path / "user.json",
        json.dumps(
            {"other": {"kept": True}, "mcpServers": {"x": {"command": "x", "enabled": False}}},
            indent=4,
        )
        + "\n",
    )

    set_server_enabled(user, "x", True)
    text = user.read_text(encoding="utf-8")

    assert '"enabled"' not in text  # full entry: the default deletes the key
    assert '"kept": true' in text  # unrelated content survives
    assert '\n            "command"' in text  # indentation preserved
    result = load_mcp_config(user, None, ENV)
    assert _server(result, "x").enabled is True

    set_server_enabled(user, "x", False)
    result = load_mcp_config(user, None, ENV)
    assert _server(result, "x").enabled is False


def test_set_server_enabled_override_writes_true(tmp_path: Path) -> None:
    project = _write(tmp_path / "project.json", {"mcpServers": {"x": {"enabled": False}}})

    set_server_enabled(project, "x", True)
    text = project.read_text(encoding="utf-8")

    # The entry stays an override, so the explicit value is written, not deleted.
    assert json.loads(text) == {"mcpServers": {"x": {"enabled": True}}}


def test_set_server_enabled_unknown_name_raises(tmp_path: Path) -> None:
    user = _write(tmp_path / "user.json", {"mcpServers": {"x": {"command": "x"}}})

    try:
        set_server_enabled(user, "nope", False)
    except ValueError as exc:
        assert "nope" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_set_server_enabled_fsyncs_before_replace(tmp_path: Path, monkeypatch) -> None:
    from pathlib import Path as _Path

    import baldric.mcp.config as mcp_config_module

    order: list[str] = []
    real_fsync = mcp_config_module.fsync
    monkeypatch.setattr(mcp_config_module, "fsync", lambda fd: (order.append("fsync"), real_fsync(fd))[1])
    original_replace = _Path.replace

    def recording_replace(self, target):
        order.append("replace")
        return original_replace(self, target)

    monkeypatch.setattr(_Path, "replace", recording_replace)
    user = _write(tmp_path / "user.json", {"mcpServers": {"x": {"command": "x", "enabled": False}}})

    set_server_enabled(user, "x", True)

    result = load_mcp_config(user, None, ENV)
    assert _server(result, "x").enabled is True
    assert not list(tmp_path.glob(".user.json.*"))
    assert order == ["fsync", "replace"]
