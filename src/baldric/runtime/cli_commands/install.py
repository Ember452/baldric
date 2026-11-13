"""`baldric install` — install a trusted local or Git extension."""

from __future__ import annotations

import typer

from baldric.runtime.platform.installer import ExtensionInstallError, install_extension


def install_command(args: list[str]) -> None:
    """Install an extension into Baldric's user extension directory."""
    source: str | None = None
    force = False
    for arg in args:
        if arg == "--force":
            force = True
        elif arg.startswith("-"):
            raise typer.BadParameter(f"Unknown option for `baldric install`: {arg}")
        elif source is None:
            source = arg
        else:
            raise typer.BadParameter("Usage: baldric install <source> [--force]")
    if source is None:
        raise typer.BadParameter("Usage: baldric install <source> [--force]")

    typer.echo(
        "Warning: extensions execute arbitrary Python with your user permissions. "
        "Only install sources you trust.",
        err=True,
    )
    try:
        destination = install_extension(source, force=force)
    except ExtensionInstallError as exc:
        typer.echo(f"Could not install extension: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Installed {source} to {destination}")


__all__ = ["install_command"]
