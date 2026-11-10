"""Session, tree, skill, login and logout picker orchestration.

Part of the ``BaldricTuiApp`` picker extraction, split from ``tui/pickers.py`` to
keep each module cohesive and under the structure ratchet's growth limit.
``PickerMixin`` composes this as a base, so ``BaldricTuiApp`` still inherits one
picker entry point. ``self`` is the app; methods are moved verbatim.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from baldric.runtime.auth.credentials import FileCredentialStore, OAuthCredential
from baldric.runtime.auth.oauth import login_openai_codex
from baldric.runtime.auth.registry import get_oauth_provider
from baldric.runtime.providers.catalog import (
    BUILTIN_PROVIDER_CATALOG,
    ProviderCatalogEntry,
    builtin_provider_entry,
)
from baldric.runtime.providers.config import (
    provider_config_from_catalog_entry,
    upsert_saved_provider,
)
from baldric.runtime.session.session import TREE_RUNNING_MESSAGE
from baldric.runtime.tui.login_providers import (
    NO_STORED_CREDENTIALS_MESSAGE,
    api_key_login_providers,
    stored_credential_providers,
    subscription_login_providers,
)
from baldric.runtime.tui.screens.login import (
    LoginMethodPickerScreen,
    LoginProviderPickerScreen,
    LoginScreen,
    OAuthLoginScreen,
    _LoginFlowAction,
)
from baldric.runtime.tui.screens.session_picker import SessionPickerScreen
from baldric.runtime.tui.screens.skill_picker import SkillPickerResult, SkillPickerScreen
from baldric.runtime.tui.screens.tree_picker import TreePickerResult, TreePickerScreen
from baldric.runtime.tui.session_records import (
    archived_session_records,
    local_session_records,
    session_records,
)
from baldric.runtime.tui.text_utils import text_end_location
from baldric.runtime.tui.widgets.prompt_input import PromptInput

if TYPE_CHECKING:
    pass

__all__ = ["SessionPickerMixin"]

_PICKER_MOUNT_POLL_SECONDS = 0.02
_PICKER_MOUNT_WAIT_SECONDS = 5.0


class SessionPickerMixin:
    """Session / tree / skill / login / logout pickers; ``self`` is the app."""

    def action_open_session_picker(self: Any) -> None:
        """Open local sessions immediately, then load other projects."""
        if self.state.running:
            self._notify("Baldric is already working. Press Escape to cancel.")
            return
        if getattr(self.session, "session_manager", None) is None:
            self._notify("No sessions found.")
            return
        picker = SessionPickerScreen(
            (),
            local_cwd=Path(self.session.cwd),
            theme=self.tui_settings.resolved_theme,
            loading_other_projects=True,
            current_project_loaded=False,
        )
        self.push_screen(picker, callback=self._handle_session_picker_result)
        self.run_worker(self._refresh_open_session_picker(picker), exclusive=False)

    async def _refresh_open_session_picker(self: Any, picker: SessionPickerScreen) -> None:
        """Load session indexes without blocking Textual's event loop."""
        try:
            local_records = await asyncio.to_thread(local_session_records, self.session)
        except Exception as exc:
            if self.screen is picker:
                self._notify(f"Could not load current project sessions: {exc}", severity="warning")
        else:
            if not await self._wait_for_open_session_picker(picker):
                return
            picker.update_records(local_records, loading_other_projects=True)

        try:
            records = await asyncio.to_thread(session_records, self.session)
            archived_records = await asyncio.to_thread(archived_session_records, self.session)
        except Exception as exc:
            if self.screen is picker:
                picker.finish_loading()
                self._notify(f"Could not load other projects: {exc}", severity="warning")
            return
        if await self._wait_for_open_session_picker(picker):
            picker.update_records(records, archived_records=archived_records)

    async def _wait_for_open_session_picker(self: Any, picker: SessionPickerScreen) -> bool:
        """Wait until this picker is mounted, or report that it was closed.

        Polling with a real sleep instead of ``asyncio.sleep(0)`` keeps this
        wait from spinning the event loop, and the deadline keeps a picker
        that never mounts (observed as Windows test hangs) from holding the
        refresh worker forever.
        """
        deadline = asyncio.get_running_loop().time() + _PICKER_MOUNT_WAIT_SECONDS
        while self.screen is picker and not picker.is_mounted:
            if asyncio.get_running_loop().time() >= deadline:
                return False
            await asyncio.sleep(_PICKER_MOUNT_POLL_SECONDS)
        return self.screen is picker and bool(picker.is_mounted)

    def _handle_session_picker_result(self: Any, session_id: str | None) -> None:
        if session_id is None:
            return
        if self._is_agent_or_queue_active():
            # Browsing the picker stays allowed while busy; resuming would
            # race the in-flight agent turn or compaction, so refuse here.
            self._notify("Baldric is already working. Press Escape to cancel.", severity="warning")
            return
        self.run_worker(self._resume_session(session_id), exclusive=False)

    def _open_skills_picker(self: Any) -> None:
        """Open loaded-skill discovery."""
        self.push_screen(
            SkillPickerScreen(self.session.skills, theme=self.tui_settings.resolved_theme),
            callback=self._handle_skill_picker_result,
        )

    def _handle_skill_picker_result(self: Any, result: SkillPickerResult | None) -> None:
        prompt = self.query_one("#prompt", PromptInput)
        if result is None:
            prompt.text = ""
        elif result.action == "insert":
            prompt.text = f"/skill:{result.skill.name}"
        else:
            prompt.text = ""
            self.state.add_item(
                "status",
                f"Skill: {result.skill.name} (not added to context)\n{result.skill.content}",
            )
            self._refresh()
        prompt.move_cursor(text_end_location(prompt.text))
        prompt.focus()

    async def _open_tree_picker(self: Any) -> None:
        if self._is_agent_or_queue_active():
            self._notify(TREE_RUNNING_MESSAGE, severity="warning")
            return
        tree_choices = getattr(self.session, "tree_choices", None)
        if tree_choices is None:
            self._notify("Session tree is not available.", severity="warning")
            return
        try:
            choices = tuple(await tree_choices())
        except Exception as exc:
            self._notify(f"Error: {exc}", severity="error")
            return
        if not choices:
            self._notify("No session entries are available for branching.", severity="warning")
            return
        self.push_screen(
            TreePickerScreen(
                choices,
                theme=self.tui_settings.resolved_theme,
                on_label_change=self._set_tree_label,
            ),
            callback=self._handle_tree_picker_result,
        )

    def _handle_tree_picker_result(self: Any, result: TreePickerResult | None) -> None:
        if result is None:
            return
        self.run_worker(
            self._branch_to_tree_entry(
                result.entry_id,
                summarize=result.summarize,
                custom_instructions=result.custom_instructions,
            ),
            exclusive=False,
        )

    def _open_login_picker(self: Any) -> None:
        self.push_screen(
            LoginMethodPickerScreen(theme=self.tui_settings.resolved_theme),
            callback=self._handle_login_method_result,
        )

    def _handle_login_method_result(self: Any, method: str | None) -> None:
        if method is None:
            return
        if method == "subscription":
            providers = subscription_login_providers(BUILTIN_PROVIDER_CATALOG)
        elif method == "api-key":
            providers = api_key_login_providers(BUILTIN_PROVIDER_CATALOG)
        elif method == "custom":
            self._open_custom_provider_login()
            return
        else:
            self._notify(f"Unknown login method: {method}", severity="error")
            return
        if not providers:
            self._notify("No login providers are available for that method.", severity="warning")
            return
        self.push_screen(
            LoginProviderPickerScreen(
                providers,
                theme=self.tui_settings.resolved_theme,
                back_on_cancel=True,
            ),
            callback=lambda provider_name: self._handle_login_provider_result(
                provider_name,
                method=method,
            ),
        )

    def _handle_login_provider_result(
        self: Any,
        provider_name: str | _LoginFlowAction | None,
        *,
        method: str | None = None,
    ) -> None:
        if provider_name is _LoginFlowAction.BACK:
            self._open_login_picker()
        elif provider_name is not None:
            self._open_login(provider_name, method=method)

    def _open_login(self: Any, provider_name: str, *, method: str | None = None) -> None:
        entry = builtin_provider_entry(provider_name)
        if entry is None:
            self._notify(f"Unknown provider: {provider_name}", severity="error")
            return
        use_oauth = method == "subscription" or (method is None and "api_key" not in entry.auth_methods)
        if use_oauth and get_oauth_provider(entry.name) is not None:
            login = None
            if entry.name == "openai-codex":

                async def login(callbacks: Any) -> OAuthCredential:
                    return await login_openai_codex(
                        on_auth=callbacks.on_auth,
                        on_prompt=callbacks.on_prompt,
                        on_manual_code_input=callbacks.on_manual_code_input,
                        on_progress=callbacks.on_progress,
                    )

            self.push_screen(
                OAuthLoginScreen(
                    entry,
                    theme=self.tui_settings.resolved_theme,
                    login=login,
                ),
                callback=lambda credential: self._handle_oauth_login_navigation_result(entry, credential),
            )
            return
        self.push_screen(
            LoginScreen(entry, theme=self.tui_settings.resolved_theme),
            callback=lambda api_key: self._handle_api_key_login_navigation_result(entry, api_key),
        )

    def _handle_login_result(self: Any, entry: ProviderCatalogEntry, api_key: str | None) -> None:
        if api_key is None:
            return
        if entry.credential_name is None:
            self._notify(
                f"Provider {entry.name} does not support saved credentials.",
                severity="error",
            )
            return
        try:
            FileCredentialStore().set(entry.credential_name, api_key)
            provider = provider_config_from_catalog_entry(entry.name)
            upsert_saved_provider(provider, set_default=False)
            self.session.reload_provider_settings()
            try:
                self.session.set_provider(entry.name, persist_default=False)
            except TypeError:
                self.session.set_provider(entry.name)
        except Exception as exc:
            self._notify(f"Could not save login: {exc}", severity="error")
            return
        self._notify(f"Saved login for {entry.display_name}.")
        self._refresh()

    def _open_logout_picker(self: Any) -> None:
        providers = stored_credential_providers(BUILTIN_PROVIDER_CATALOG)
        if not providers:
            self._notify(NO_STORED_CREDENTIALS_MESSAGE, severity="warning")
            return
        self.push_screen(
            LoginProviderPickerScreen(
                providers,
                theme=self.tui_settings.resolved_theme,
                title="Logout",
            ),
            callback=self._handle_logout_provider_result,
        )

    def _handle_logout_provider_result(self: Any, provider_name: str | _LoginFlowAction | None) -> None:
        if isinstance(provider_name, str):
            self._logout(provider_name)
