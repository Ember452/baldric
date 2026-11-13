"""TUI frontend: launch the Textual app for one interactive session.

Owns the mode entry for the TUI surface (mirroring ``frontends/print/mode.py``
and ``frontends/rpc/mode.py``), including its startup banners: the release-notes
notice and the deferred PyPI check the app runs once it is up. Those are UI
policy, so they belong to the frontend; the CLI only dispatches.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from baldric.runtime.context.thinking import ThinkingLevel
from baldric.runtime.frontends.tui.app import run_tui_app
from baldric.runtime.trust.policy import TrustOverride
from baldric.runtime.update.check import (
    UpdateNotice,
    cached_update_notice,
    startup_release_notes_notice,
    startup_update_notice,
)
from baldric.runtime.version import current_version


def _deferred_startup_update_notice() -> Callable[[], str | None] | None:
    """Return a blocking PyPI check for the TUI to run when the cache is stale."""
    _notice, check_due = cached_update_notice(current_version())
    if not check_due:
        return None

    def check() -> str | None:
        notice = startup_update_notice(current_version())
        return notice.message if notice is not None else None

    return check


async def run_openai_tui(
    model: str | None,
    cwd: Path,
    session_id: str | None = None,
    new_session: bool = False,
    provider_name: str | None = None,
    auto_compact_token_threshold: int | None = None,
    initial_prompt: str | None = None,
    update_notice: UpdateNotice | None = None,
    extension_paths: tuple[Path, ...] = (),
    extensions_enabled: bool = True,
    project_extensions_enabled: bool = False,
    custom_system_prompt: str | None = None,
    append_system_prompt: str | None = None,
    trust_override: TrustOverride | None = None,
    *,
    thinking_level_override: ThinkingLevel | None = None,
    show_full_output: bool = False,
) -> str | None:
    """Run the Textual TUI and return its resumable session id, if any."""
    release_notes_notice = startup_release_notes_notice(current_version())
    startup_notices = (release_notes_notice.message,) if release_notes_notice is not None else ()
    deferred_update_notice = _deferred_startup_update_notice() if update_notice is None else None
    return await run_tui_app(
        model=model,
        cwd=cwd,
        session_id=session_id,
        new_session=new_session,
        provider_name=provider_name,
        auto_compact_token_threshold=auto_compact_token_threshold,
        initial_prompt=initial_prompt,
        startup_update_notice=update_notice.message if update_notice is not None else None,
        deferred_startup_update_notice=deferred_update_notice,
        startup_notices=startup_notices,
        extension_paths=extension_paths,
        extensions_enabled=extensions_enabled,
        project_extensions_enabled=project_extensions_enabled,
        custom_system_prompt=custom_system_prompt,
        append_system_prompt=append_system_prompt,
        trust_override=trust_override,
        thinking_level_override=thinking_level_override,
        show_full_output=show_full_output,
    )


__all__ = ["run_openai_tui"]
