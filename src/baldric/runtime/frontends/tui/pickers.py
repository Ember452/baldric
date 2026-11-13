"""Model / scoped-model / theme picker orchestration.

The picker *screens* live in ``baldric.runtime.frontends.tui.screens``; this module holds
the ``BaldricTuiApp`` methods that open the model/scoped-model and theme pickers
and handle their results. Session/tree/skill/login pickers live in
``tui/session_pickers.py`` and are composed here via ``SessionPickerMixin``, so
``BaldricTuiApp`` inherits a single picker entry point.

``self`` is typed ``Any``: re-declaring Textual's ``App`` surface clashes with
``App``/``MessagePump`` in the concrete class's MRO. Bodies are thin
orchestration glue moved verbatim; nothing here changes behaviour.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from baldric.runtime.frontends.tui.screens.model_picker import ModelPickerScreen
from baldric.runtime.frontends.tui.screens.theme import ThemePickerScreen
from baldric.runtime.frontends.tui.session_pickers import SessionPickerMixin
from baldric.runtime.rendering.themes import available_tui_theme_names

if TYPE_CHECKING:
    from baldric.runtime.frontends.tui.config import TuiThemeName

__all__ = ["PickerMixin"]


class PickerMixin(SessionPickerMixin):
    """Model / scoped-model / theme pickers; ``self`` is the app."""

    def _open_model_picker(self: Any) -> None:
        choices = self._available_model_choices()
        scoped = tuple(getattr(self.session, "scoped_model_choices", ()))
        if not choices and not scoped and not getattr(self.session, "has_stale_active_model", False):
            self._notify(
                "No configured providers are usable. Run /login to set up a provider.",
                severity="warning",
            )
            return
        picker = ModelPickerScreen(
            choices,
            scoped_choices=scoped,
            current_model=self.session.model,
            provider_name=self.session.provider_name,
            theme=self.tui_settings.resolved_theme,
            on_toggle_scoped=None,
            picker_kind="model",
        )
        picker.on_first_refresh = lambda: self._start_model_picker_refresh(picker)
        self.push_screen(picker, callback=lambda choice: self._handle_model_picker_result(picker, choice))

    def _start_model_picker_refresh(self: Any, picker: ModelPickerScreen) -> None:
        if self.screen is picker:
            picker.refresh_worker = self.run_worker(self._refresh_open_model_picker(picker), exclusive=False)

    async def _refresh_open_model_picker(self: Any, picker: ModelPickerScreen) -> None:
        refresh = getattr(self.session, "refresh_model_catalogs", None)
        if not callable(refresh):
            return
        try:
            await refresh()
        except Exception as error:
            if self.screen is picker:
                self._notify(f"Could not refresh model catalogs: {error}", severity="warning")
            return
        if self.screen is picker and picker.is_mounted:
            picker.update_choices(
                self._available_model_choices(),
                tuple(getattr(self.session, "scoped_model_choices", ())),
            )

    def _handle_model_picker_result(self: Any, picker: ModelPickerScreen, choice: Any) -> None:
        picker.cancel_refresh()
        if choice is not None:
            self.call_after_refresh(self._start_selected_model_switch, choice)

    def _open_scoped_models_picker(self: Any) -> None:
        choices = self._available_model_choices()
        scoped = tuple(getattr(self.session, "scoped_model_choices", ()))
        if not choices and not scoped and not getattr(self.session, "has_stale_active_model", False):
            self._notify(
                "No configured providers are usable. Run /login to set up a provider.",
                severity="warning",
            )
            return
        picker = ModelPickerScreen(
            choices,
            scoped_choices=scoped,
            current_model=self.session.model,
            provider_name=self.session.provider_name,
            theme=self.tui_settings.resolved_theme,
            on_toggle_scoped=self._toggle_scoped_model,
            picker_kind="scoped",
            initial_thinking_level=self.session.thinking_level,
        )
        picker.on_first_refresh = lambda: self._start_model_picker_refresh(picker)
        self.push_screen(
            picker,
            callback=lambda choice: self._handle_scoped_models_picker_result(picker, choice),
        )

    def _handle_scoped_models_picker_result(self: Any, picker: ModelPickerScreen, choice: Any) -> None:
        del choice
        picker.cancel_refresh()
        if (
            picker.initial_thinking_level is not None
            and picker.initial_thinking_level != self.session.thinking_level
        ):
            self.call_after_refresh(self._refresh_chrome)

    def _open_theme_picker(self: Any) -> None:
        self.push_screen(
            ThemePickerScreen(
                current_theme=self.tui_settings.theme,
                theme=self.tui_settings.resolved_theme,
                theme_names=available_tui_theme_names(),
            ),
            callback=self._handle_theme_picker_result,
        )

    def _handle_theme_picker_result(self: Any, theme: TuiThemeName | None) -> None:
        if theme is None:
            return
        self._set_tui_theme(theme)
