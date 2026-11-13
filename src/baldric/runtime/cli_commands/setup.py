"""`baldric setup` — create or update an OpenAI-compatible provider entry."""

from __future__ import annotations

import contextlib
import faulthandler
from os import environ

import typer

from baldric.ai.env import (
    DEFAULT_OPENAI_COMPATIBLE_BASE_URL,
    DEFAULT_OPENAI_COMPATIBLE_MAX_RETRIES,
    DEFAULT_OPENAI_COMPATIBLE_MAX_RETRY_DELAY_SECONDS,
    DEFAULT_OPENAI_COMPATIBLE_TIMEOUT_SECONDS,
)
from baldric.runtime.observability.doctor import render_doctor_report
from baldric.runtime.providers.config import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER_NAME,
    OpenAICompatibleProviderConfig,
    load_provider_settings,
    save_provider_settings,
    upsert_openai_compatible_provider,
)
from baldric.runtime.providers.loader import user_catalog_path


def setup_command(
    *,
    provider_name: str = DEFAULT_PROVIDER_NAME,
    base_url: str = DEFAULT_OPENAI_COMPATIBLE_BASE_URL,
    api_key_env: str = "OPENAI_API_KEY",
    model: str = DEFAULT_MODEL,
    timeout_seconds: float = DEFAULT_OPENAI_COMPATIBLE_TIMEOUT_SECONDS,
    max_retries: int = DEFAULT_OPENAI_COMPATIBLE_MAX_RETRIES,
    max_retry_delay_seconds: float = DEFAULT_OPENAI_COMPATIBLE_MAX_RETRY_DELAY_SECONDS,
    set_default: bool = True,
) -> None:
    """Create or update an OpenAI-compatible provider entry."""
    settings = load_provider_settings()
    provider = OpenAICompatibleProviderConfig(
        name=provider_name,
        base_url=base_url.rstrip("/"),
        api_key_env=api_key_env,
        models=(model,),
        default_model=model,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        max_retry_delay_seconds=max_retry_delay_seconds,
    )
    updated = upsert_openai_compatible_provider(settings, provider, set_default=set_default)
    path = save_provider_settings(updated)
    typer.echo(f"Saved provider '{provider.name}' to {user_catalog_path()} and preferences to {path}")
    if provider.api_key_env not in environ:
        typer.echo(f"Set {provider.api_key_env} before running Baldric with this provider.", err=True)


def _cli_preflight(*, doctor: bool) -> None:
    """Start best-effort crash diagnostics, then honor the `--doctor` early exit."""
    # CliRunner and other embedded hosts use fileno-less streams where
    # faulthandler cannot attach; diagnostics stay best-effort there.
    with contextlib.suppress(ValueError, OSError):
        faulthandler.enable()
    if doctor:
        render_doctor_report()
        raise typer.Exit()


__all__ = ["setup_command"]
