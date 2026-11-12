"""Minimal Textual app for Baldric coding sessions."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, ClassVar, cast

from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
)

from baldric.runtime.frontends.tui.config import (
    TuiTheme,
)
from baldric.runtime.providers.auth.credentials import OAuthCredential
from baldric.runtime.providers.auth.types import (
    OAuthAuthInfo,
    OAuthDeviceCodeInfo,
    OAuthLoginCallbacks,
    OAuthPrompt,
    OAuthSelectPrompt,
)
from baldric.runtime.providers.catalog import (
    ProviderCatalogEntry,
)

if TYPE_CHECKING:
    pass

from baldric.runtime.frontends.tui.screens.support import (
    _filter_login_providers,
    _login_provider_label,
)

type BindingEntry = Binding | tuple[str, str] | tuple[str, str, str]


class LoginProviderSearchInput(Input):
    """Search input that keeps provider-picker navigation local."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "cancel", "Cancel", show=False, priority=True),
        Binding("up", "cursor_up", "Up", show=False, priority=True),
        Binding("down", "cursor_down", "Down", show=False, priority=True),
    ]

    def _picker(self) -> LoginProviderPickerScreen:
        return cast(LoginProviderPickerScreen, self.screen)

    def on_key(self, event: Key) -> None:
        """Route picker control keys before the input edits its text."""
        if event.key == "up":
            event.stop()
            event.prevent_default()
            self.action_cursor_up()
        elif event.key == "down":
            event.stop()
            event.prevent_default()
            self.action_cursor_down()
        elif event.key == "escape":
            event.stop()
            event.prevent_default()
            self.action_cancel()

    def action_cursor_up(self) -> None:
        """Move the provider picker selection up."""
        self._picker().action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move the provider picker selection down."""
        self._picker().action_cursor_down()

    def action_cancel(self) -> None:
        """Close the provider picker."""
        self._picker().action_cancel()


class _LoginFlowAction(Enum):
    """Navigation actions returned by nested login screens."""

    BACK = auto()


class LoginProviderPickerScreen(ModalScreen[str | _LoginFlowAction | None]):
    """Searchable provider picker for the TUI login flow."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+d", "close", "Close", priority=True),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("enter", "select_cursor", "Select", show=False),
    ]

    def __init__(
        self,
        providers: Sequence[ProviderCatalogEntry],
        *,
        theme: TuiTheme,
        title: str = "Login",
        back_on_cancel: bool = False,
    ) -> None:
        super().__init__()
        self.providers = tuple(providers)
        self.back_on_cancel = back_on_cancel
        self.visible_providers = self.providers
        self.theme = theme
        self.title_text = title

    def compose(self) -> ComposeResult:
        """Compose the provider picker."""
        with Vertical(id="login-provider-picker"):
            yield Static(self.title_text, id="login-provider-title")
            yield LoginProviderSearchInput(
                placeholder="Search providers",
                id="login-provider-search",
            )
            yield ListView(
                *[
                    ListItem(Label(_login_provider_label(provider), markup=False))
                    for provider in self.providers
                ],
                id="login-provider-list",
            )
            yield Static("Enter selects - Escape closes", id="login-provider-help")

    async def on_mount(self) -> None:
        """Focus the provider search field."""
        self.query_one("#login-provider-search", Input).focus()
        await self._refresh_provider_list()

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Filter providers as the search value changes."""
        if event.input.id != "login-provider-search":
            return
        event.stop()
        self.visible_providers = _filter_login_providers(self.providers, event.value)
        await self._refresh_provider_list()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Select the highlighted provider from the search field."""
        if event.input.id != "login-provider-search":
            return
        event.stop()
        self._select_visible_provider()

    def on_key(self, event: Key) -> None:
        """Route provider picker keys to the list."""
        if event.key == "up":
            event.stop()
            self.action_cursor_up()
        elif event.key == "down":
            event.stop()
            self.action_cursor_down()
        elif event.key == "enter":
            event.stop()
            self.action_select_cursor()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Dismiss with the selected provider name."""
        event.stop()
        self._select_visible_provider()

    def action_cursor_up(self) -> None:
        """Move to the previous provider."""
        self.query_one("#login-provider-list", ListView).action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move to the next provider."""
        self.query_one("#login-provider-list", ListView).action_cursor_down()

    def action_select_cursor(self) -> None:
        """Select the highlighted provider."""
        self._select_visible_provider()

    def action_cancel(self) -> None:
        """Go back in a login flow, or close a standalone provider picker."""
        self.dismiss(_LoginFlowAction.BACK if self.back_on_cancel else None)

    def action_close(self) -> None:
        """Close the entire login flow."""
        self.dismiss(None)

    def _select_visible_provider(self) -> None:
        if not self.visible_providers:
            return
        provider_list = self.query_one("#login-provider-list", ListView)
        # Fall back to the first match: submitting from the search field can
        # land here before the refreshed list has applied its highlight.
        index = provider_list.index
        self.dismiss(self.visible_providers[0 if index is None else index].name)

    async def _refresh_provider_list(self) -> None:
        provider_list = self.query_one("#login-provider-list", ListView)
        # Await the mounts: assigning the index while the list is still empty
        # validates it back to None, leaving the first provider unreachable
        # with the down key (issue #494).
        await provider_list.clear()
        await provider_list.extend(
            [
                ListItem(Label(_login_provider_label(provider), markup=False))
                for provider in self.visible_providers
            ]
        )
        provider_list.index = 0 if self.visible_providers else None
        help_text = (
            "Enter selects - Escape closes"
            if self.visible_providers
            else "No matching providers - Escape closes"
        )
        self.query_one("#login-provider-help", Static).update(help_text)


class LoginMethodPickerScreen(ModalScreen[str | None]):
    """Login method picker for the TUI login flow."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("ctrl+d", "cancel", "Close", priority=True),
        Binding("up", "cursor_up", "Up", show=False, priority=True),
        Binding("down", "cursor_down", "Down", show=False, priority=True),
        Binding("enter", "select_cursor", "Select", show=False, priority=True),
    ]

    def __init__(self, *, theme: TuiTheme) -> None:
        super().__init__()
        self.theme = theme

    def compose(self) -> ComposeResult:
        """Compose the login method picker."""
        with Vertical(id="login-method-picker"):
            yield Static("Login", id="login-method-title")
            yield Static("Choose how to authenticate.", id="login-method-intro")
            yield LoginMethodListView(
                ListItem(
                    Label("Subscription — OAuth account", markup=False),
                    id="login-method-subscription",
                ),
                ListItem(
                    Label("API key — built-in provider", markup=False),
                    id="login-method-api-key",
                ),
                ListItem(
                    Label("Custom provider — OpenAI-compatible", markup=False),
                    id="login-method-custom",
                ),
                id="login-method-list",
            )
            yield Static("Enter selects - Escape/Ctrl+D closes", id="login-method-help")

    def on_mount(self) -> None:
        """Focus the default subscription method."""
        method_list = self.query_one("#login-method-list", ListView)
        method_list.index = 0
        method_list.focus()

    def on_key(self, event: Key) -> None:
        """Route arrow keys between login method buttons."""
        if event.key == "up":
            event.stop()
            self.action_cursor_up()
        elif event.key == "down":
            event.stop()
            self.action_cursor_down()
        elif event.key == "enter":
            event.stop()
            self.action_select_cursor()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Dismiss with the selected login method."""
        if event.button.id == "login-method-subscription":
            self.dismiss("subscription")
        elif event.button.id == "login-method-api-key":
            self.dismiss("api-key")
        elif event.button.id == "login-method-custom":
            self.dismiss("custom")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Dismiss with the selected login method."""
        if event.item.id == "login-method-subscription":
            self.dismiss("subscription")
        elif event.item.id == "login-method-api-key":
            self.dismiss("api-key")
        elif event.item.id == "login-method-custom":
            self.dismiss("custom")

    def action_cancel(self) -> None:
        """Close without selecting a login method."""
        self.dismiss(None)

    def action_cursor_up(self) -> None:
        """Focus the previous login method."""
        self._move_method_cursor(offset=-1)

    def action_cursor_down(self) -> None:
        """Focus the next login method."""
        self._move_method_cursor(offset=1)

    def action_select_cursor(self) -> None:
        """Select the currently focused login method."""
        self.query_one("#login-method-list", ListView).action_select_cursor()

    def _move_method_cursor(self, *, offset: int) -> None:
        method_list = self.query_one("#login-method-list", ListView)
        item_count = len(method_list.children)
        if item_count == 0:
            method_list.index = None
            return
        current_index = method_list.index if method_list.index is not None else 0
        method_list.index = (current_index + offset) % item_count


class LoginMethodListView(ListView):
    """List view with wrapping arrow navigation for the login method picker."""

    def action_cursor_up(self) -> None:
        """Move to the previous login method."""
        self._move_cursor(offset=-1)

    def action_cursor_down(self) -> None:
        """Move to the next login method."""
        self._move_cursor(offset=1)

    def _move_cursor(self, *, offset: int) -> None:
        item_count = len(self.children)
        if item_count == 0:
            self.index = None
            return
        current_index = self.index if self.index is not None else 0
        self.index = (current_index + offset) % item_count


@dataclass(frozen=True, slots=True)
class CustomProviderLoginResult:
    """Provider details collected by the custom-provider login flow."""

    provider_name: str
    display_name: str
    base_url: str
    api_key_env: str
    models: tuple[str, ...]
    default_model: str
    api_key: str


class CustomProviderLoginScreen(ModalScreen[CustomProviderLoginResult | _LoginFlowAction | None]):
    """Prompt for adding an OpenAI-compatible custom provider."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "back", "Back"),
        Binding("ctrl+d", "close", "Close", priority=True),
    ]

    _INPUT_ORDER: ClassVar[tuple[str, ...]] = (
        "custom-provider-name",
        "custom-provider-display-name",
        "custom-provider-base-url",
        "custom-provider-api-key-env",
        "custom-provider-models",
        "custom-provider-default-model",
        "custom-provider-api-key",
    )

    def __init__(self, *, theme: TuiTheme) -> None:
        super().__init__()
        self.theme = theme

    def compose(self) -> ComposeResult:
        """Compose the custom provider prompt."""
        with Vertical(id="login-screen"):
            yield Static("Add custom provider", id="login-title")
            yield Static(
                "Short provider name is used in commands/config.",
                id="custom-provider-help",
            )
            yield Input(placeholder="Provider name/id, e.g. nebius", id="custom-provider-name")
            yield Input(
                placeholder="Display name shown in UI, e.g. Nebius AI Studio",
                id="custom-provider-display-name",
            )
            yield Input(
                placeholder="OpenAI-compatible base URL, e.g. https://api.studio.nebius.ai/v1",
                id="custom-provider-base-url",
            )
            yield Input(
                placeholder="API key environment variable fallback, e.g. NEBIUS_API_KEY",
                id="custom-provider-api-key-env",
            )
            yield Input(
                placeholder="Model ids, comma-separated, e.g. model-a, model-b",
                id="custom-provider-models",
            )
            yield Input(
                placeholder="Default model id, must be listed above",
                id="custom-provider-default-model",
            )
            yield Input(
                placeholder="Paste API key to save for this provider",
                password=True,
                id="custom-provider-api-key",
            )
            yield Static(
                "Enter advances/saves - Escape goes back - Ctrl+D closes",
                id="login-footer",
            )

    def on_mount(self) -> None:
        """Focus the first provider-detail field."""
        self.query_one("#custom-provider-name", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Advance through fields, then dismiss with provider details."""
        input_id = event.input.id
        if input_id not in self._INPUT_ORDER:
            return
        event.stop()
        if input_id != self._INPUT_ORDER[-1]:
            self._focus_next(input_id)
            return
        result = self._collect_result()
        if result is not None:
            self.dismiss(result)

    def _focus_next(self, input_id: str) -> None:
        index = self._INPUT_ORDER.index(input_id)
        self.query_one(f"#{self._INPUT_ORDER[index + 1]}", Input).focus()

    def _collect_result(self) -> CustomProviderLoginResult | None:
        provider_name = self._field("custom-provider-name", "Provider name")
        if provider_name is None:
            return None
        base_url = self._field("custom-provider-base-url", "Base URL")
        if base_url is None:
            return None
        api_key_env = self._field("custom-provider-api-key-env", "API key environment variable")
        if api_key_env is None:
            return None
        models_text = self._field("custom-provider-models", "Model ids")
        if models_text is None:
            return None
        models = tuple(dict.fromkeys(item.strip() for item in models_text.split(",") if item.strip()))
        if not models:
            self.query_one("#custom-provider-help", Static).update("At least one model id is required.")
            self.query_one("#custom-provider-models", Input).focus()
            return None
        default_model = self._field("custom-provider-default-model", "Default model")
        if default_model is None:
            return None
        if default_model not in models:
            self.query_one("#custom-provider-help", Static).update(
                "Default model must be included in the model list."
            )
            self.query_one("#custom-provider-default-model", Input).focus()
            return None
        api_key = self._field("custom-provider-api-key", "API key")
        if api_key is None:
            return None
        display_name = self.query_one("#custom-provider-display-name", Input).value.strip()
        return CustomProviderLoginResult(
            provider_name=provider_name,
            display_name=display_name or provider_name,
            base_url=base_url,
            api_key_env=api_key_env,
            models=models,
            default_model=default_model,
            api_key=api_key,
        )

    def _field(self, input_id: str, label: str) -> str | None:
        value = self.query_one(f"#{input_id}", Input).value.strip()
        if value:
            return value
        self.query_one("#custom-provider-help", Static).update(f"{label} is required.")
        self.query_one(f"#{input_id}", Input).focus()
        return None

    def action_back(self) -> None:
        """Return to the login method picker."""
        self.dismiss(_LoginFlowAction.BACK)

    def action_close(self) -> None:
        """Close the entire login flow."""
        self.dismiss(None)


class LoginScreen(ModalScreen[str | _LoginFlowAction | None]):
    """Password prompt for saving a provider API key."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "back", "Back"),
        Binding("ctrl+d", "close", "Close", priority=True),
    ]

    def __init__(self, provider: ProviderCatalogEntry, *, theme: TuiTheme) -> None:
        super().__init__()
        self.provider = provider
        self.theme = theme

    def compose(self) -> ComposeResult:
        """Compose the provider login prompt."""
        with Vertical(id="login-screen"):
            yield Static(f"Login: {self.provider.display_name}", id="login-title")
            yield Static("Paste this provider's API key.", id="login-help")
            yield Input(placeholder="Paste API key", password=True, id="login-api-key")
            yield Static("Enter saves - Escape goes back - Ctrl+D closes", id="login-footer")

    def on_mount(self) -> None:
        """Focus the API key field."""
        self.query_one("#login-api-key", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Dismiss with the submitted API key."""
        if event.input.id != "login-api-key":
            return
        event.stop()
        self.dismiss(event.value.strip() or None)

    def action_back(self) -> None:
        """Return to the login method picker without saving."""
        self.dismiss(_LoginFlowAction.BACK)

    def action_close(self) -> None:
        """Close the entire login flow."""
        self.dismiss(None)


class OAuthLoginScreen(ModalScreen[OAuthCredential | _LoginFlowAction | None]):
    """OAuth login flow for providers backed by subscription auth."""

    BINDINGS: ClassVar[list[BindingEntry]] = [
        Binding("escape", "back", "Back"),
        Binding("ctrl+d", "close", "Close", priority=True),
    ]

    def __init__(
        self,
        provider: ProviderCatalogEntry,
        *,
        theme: TuiTheme,
        login: Callable[[OAuthLoginCallbacks], Awaitable[OAuthCredential]] | None = None,
    ) -> None:
        super().__init__()
        self.provider = provider
        self.theme = theme
        self._login = login
        self._manual_code_future: asyncio.Future[str] | None = None
        self._manual_code_value: str | None = None
        self._prompt_allows_empty = False

    def compose(self) -> ComposeResult:
        """Compose the OAuth login prompt."""
        with Vertical(id="login-screen"):
            yield Static(f"Login: {self.provider.display_name}", id="login-title")
            yield Static("Follow the provider instructions to complete login.", id="login-help")
            yield Static("", id="login-oauth-url")
            yield Input(
                placeholder="Paste redirect URL or authorization code",
                id="login-oauth-code",
            )
            yield Static("Enter submits - Escape goes back - Ctrl+D closes", id="login-footer")

    def on_mount(self) -> None:
        """Focus the manual-code field and start OAuth."""
        self.query_one("#login-oauth-code", Input).focus()
        self.run_worker(self._run_login(), exclusive=True)

    async def _run_login(self) -> None:
        try:
            oauth_provider = _app_module().get_oauth_provider(self.provider.name)
            login = self._login or (oauth_provider.login if oauth_provider is not None else None)
            if login is None:
                raise RuntimeError(f"No OAuth implementation for {self.provider.name}")
            credential = await login(
                OAuthLoginCallbacks(
                    on_auth=self._show_auth,
                    on_device_code=self._show_device_code,
                    on_prompt=self._prompt_for_code,
                    on_select=self._select_option,
                    on_progress=self._show_progress,
                    on_manual_code_input=self._manual_code_input,
                )
            )
        except Exception as exc:  # noqa: BLE001 - surface OAuth failures in the TUI
            self.query_one("#login-help", Static).update(f"OAuth failed: {exc}")
            return
        self.dismiss(credential)

    def _show_auth(self, info: OAuthAuthInfo) -> None:
        self._show_url(info.url)
        # Copy only the browser-flow URL. It is hundreds of characters long and
        # wraps across the dialog, so hand-selecting it is what corrupts it;
        # taking over the clipboard is worth it there and nowhere else.
        with suppress(Exception):
            self.app.copy_to_clipboard(info.url)
        self.notify("Authorization URL copied to clipboard.")
        if info.instructions:
            self.query_one("#login-help", Static).update(info.instructions)

    def _show_url(self, url: str) -> None:
        """Display a URL as one clickable unit.

        Authorization URLs are far wider than the dialog, so they render across
        several wrapped lines. Selecting those lines by hand tends to corrupt
        the URL — a query parameter split across a wrap picks up the line break
        or trailing padding and the provider rejects the request. An OSC 8
        hyperlink keeps a click on any wrapped line opening the intact URL.
        """
        self.query_one("#login-oauth-url", Static).update(Text(url, style=Style(link=url)))

    def _show_device_code(self, info: OAuthDeviceCodeInfo) -> None:
        # No clipboard copy here: the verification URI is short and clickable,
        # and the thing the user carries to the browser is the code below it.
        self._show_url(info.verification_uri)
        self.query_one("#login-help", Static).update(f"Open the URL and enter code: {info.user_code}")

    def _show_progress(self, message: str) -> None:
        self.query_one("#login-help", Static).update(message)

    async def _prompt_for_code(self, prompt: OAuthPrompt) -> str:
        self.query_one("#login-help", Static).update(prompt.message)
        self._prompt_allows_empty = prompt.allow_empty
        try:
            return await self._manual_code_input()
        finally:
            self._prompt_allows_empty = False

    async def _select_option(self, prompt: OAuthSelectPrompt) -> str | None:
        self.query_one("#login-help", Static).update(prompt.message)
        return prompt.options[0].id if prompt.options else None

    async def _manual_code_input(self) -> str:
        if self._manual_code_value is not None:
            return self._manual_code_value
        loop = asyncio.get_running_loop()
        self._manual_code_future = loop.create_future()
        try:
            return await self._manual_code_future
        finally:
            self._manual_code_future = None

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Resolve the manual OAuth code fallback."""
        if event.input.id != "login-oauth-code":
            return
        event.stop()
        value = event.value.strip()
        if not value and not self._prompt_allows_empty:
            return
        self._manual_code_value = value
        if self._manual_code_future is not None and not self._manual_code_future.done():
            self._manual_code_future.set_result(value)

    def action_back(self) -> None:
        """Return to the login method picker without saving credentials."""
        self._cancel_manual_code_input()
        self.dismiss(_LoginFlowAction.BACK)

    def action_close(self) -> None:
        """Close the entire login flow without saving credentials."""
        self._cancel_manual_code_input()
        self.dismiss(None)

    def _cancel_manual_code_input(self) -> None:
        if self._manual_code_future is not None and not self._manual_code_future.done():
            self._manual_code_future.cancel()


def _app_module() -> Any:
    import baldric.runtime.frontends.tui.app as app_module

    return app_module
