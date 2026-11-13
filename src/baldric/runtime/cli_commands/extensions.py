"""`baldric extensions` — list, update, or remove managed extensions."""

from __future__ import annotations

import typer

from baldric.runtime.config.paths import BaldricPaths
from baldric.runtime.platform.installer import (
    ExtensionInstallError,
    read_extension_registry,
    remove_extension,
    update_extension,
)


def extensions_command(args: list[str]) -> None:
    """List, update, or remove Baldric-managed extensions."""
    subcommand = args[0] if args else None
    if subcommand == "list" or subcommand is None:
        _extensions_list_command()
        return
    name: str | None = None
    force = False
    for arg in args[1:]:
        if arg == "--force":
            force = True
        elif arg.startswith("-"):
            raise typer.BadParameter(f"Unknown option for `baldric extensions {subcommand}`: {arg}")
        elif name is None:
            name = arg
        else:
            raise typer.BadParameter(f"Usage: baldric extensions {subcommand} <name> [--force]")
    if name is None:
        raise typer.BadParameter(f"Usage: baldric extensions {subcommand} <name> [--force]")
    if subcommand == "update":
        try:
            destination = update_extension(name, force=force)
        except ExtensionInstallError as exc:
            typer.echo(f"Could not update extension: {exc}", err=True)
            raise typer.Exit(1) from exc
        typer.echo(f"Updated {name} at {destination}")
        return
    if subcommand == "remove":
        try:
            destination = remove_extension(name)
        except ExtensionInstallError as exc:
            typer.echo(f"Could not remove extension: {exc}", err=True)
            raise typer.Exit(1) from exc
        typer.echo(f"Removed {name} from {destination}")
        return
    raise typer.BadParameter("Usage: baldric extensions [list] | update <name> [--force] | remove <name>")


def _extensions_list_command() -> None:
    extensions_dir = BaldricPaths().user_extensions_dir
    records = read_extension_registry(extensions_dir)
    installed = sorted(path for path in extensions_dir.glob("*") if path.is_dir() or path.is_file())
    if not installed:
        typer.echo("No extensions installed.")
        return
    for path in installed:
        record = records.get(path.name)
        if record is None:
            typer.echo(f"{path.name}  unmanaged (manual, project, or explicit-path install)")
        elif record.kind == "git":
            ref = f" @ {record.ref}" if record.ref else ""
            commit = f" ({record.commit[:12]})" if record.commit else ""
            typer.echo(f"{path.name}  managed  git {record.source}{ref}{commit}")
        else:
            typer.echo(f"{path.name}  managed  local {record.source}")


__all__ = ["extensions_command"]
