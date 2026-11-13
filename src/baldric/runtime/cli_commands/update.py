"""`baldric update` / `baldric update-models` — upgrade and refresh catalogs."""

from __future__ import annotations

import anyio
import typer

from baldric.runtime.providers.stores.models_dev_store import (
    ModelsDevRefreshError,
    ModelsDevRefreshResult,
    refresh_models_dev_catalog,
)
from baldric.runtime.update.updater import update_baldric


def update_models_command() -> None:
    """Force-refresh and persist the runtime model catalog."""

    async def refresh() -> ModelsDevRefreshResult:
        return await refresh_models_dev_catalog(force=True)

    try:
        result = anyio.run(refresh)
    except ModelsDevRefreshError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    status = "refreshed" if result.refreshed else "unchanged"
    typer.echo(f"Model catalogs {status}: {result.model_count} models cached at {result.cache_path}")


def update_command() -> None:
    """Upgrade Baldric using the installer that manages the current environment."""
    result = update_baldric()
    if not result.succeeded:
        typer.echo("Could not safely update Baldric:", err=True)
        for failure in result.failures:
            typer.echo(f"- {failure}", err=True)
        raise typer.Exit(1)
    if result.stdout:
        typer.echo(result.stdout)
    if result.stderr:
        typer.echo(result.stderr, err=True)
    if result.deferred:
        typer.echo(f"Baldric update handed off with: {' '.join(result.command or ())}")
    else:
        typer.echo(f"Baldric update completed with: {' '.join(result.command or ())}")


__all__ = ["update_command", "update_models_command"]
