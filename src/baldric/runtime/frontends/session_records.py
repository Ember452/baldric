"""Resolve the session record a non-interactive frontend drives.

Both the print and RPC frontends need the same decision: a resumed transcript by
id, or an exclusively-created new record (refusing title collisions). This lives
in the frontend layer because it is a surface concern (which session does this
one non-interactive run attach to), not session orchestration.
"""

from __future__ import annotations

from pathlib import Path

from baldric.runtime.providers.config import (
    OpenAICompatibleProviderConfig,
    ProviderConfigError,
    ProviderSettings,
    resolve_provider_selection,
)
from baldric.runtime.session.manager import CodingSessionRecord, SessionManager


def resolve_mode_session_record(
    manager: SessionManager,
    *,
    resume_session_id: str | None,
    cwd: Path,
    settings: ProviderSettings,
    provider_name: str | None,
    model: str | None,
    session_id: str | None,
) -> CodingSessionRecord:
    """Resolve a resumed transcript or exclusively create a new one."""
    if resume_session_id is not None:
        record = manager.get_session(resume_session_id)
        if record is None:
            raise ValueError(f"Unknown session: {resume_session_id}")
        return record

    try:
        selection = resolve_provider_selection(settings, provider_name=provider_name, model=model)
    except ProviderConfigError:
        if provider_name is None or model is None:
            raise
        return create_mode_session(
            manager,
            cwd=cwd,
            model=model,
            provider_name=provider_name,
            session_id=session_id,
        )
    inference_provider = (
        selection.provider.inference_providers.get(selection.model)
        or selection.provider.default_inference_provider
        if isinstance(selection.provider, OpenAICompatibleProviderConfig)
        and selection.provider.name == "huggingface"
        else None
    )
    return create_mode_session(
        manager,
        cwd=cwd,
        model=selection.model,
        provider_name=selection.provider.name,
        inference_provider=inference_provider,
        session_id=session_id,
    )


def create_mode_session(
    manager: SessionManager,
    *,
    cwd: Path,
    model: str,
    provider_name: str | None = None,
    inference_provider: str | None = None,
    session_id: str | None = None,
) -> CodingSessionRecord:
    """Create an isolated non-interactive session, refusing transcript collisions."""
    return manager.create_session_exclusive(
        cwd=cwd,
        model=model,
        provider_name=provider_name,
        inference_provider=inference_provider,
        session_id=session_id,
    )


__all__ = [
    "create_mode_session",
    "resolve_mode_session_record",
]
