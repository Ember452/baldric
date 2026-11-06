"""Picker orchestration mixed into ``BaldricTuiApp``.

The picker *screens* already live in ``baldric_coding.tui.screens`` (and
``backends``); this module holds only the ``BaldricTuiApp`` methods that open
those screens and handle their results. They are methods on a mixin rather than
free functions because they read app state through ``self`` (``session``,
``tui_settings``, ``push_screen``, ``run_worker`` ...) exactly as before, so
moving them changes no call sites and no behaviour.

The bodies are thin screen-orchestration glue, so ``self`` is typed ``Any`` here
rather than re-declaring Textual's ``App`` surface (re-declaring it would clash
with ``App``/``MessagePump`` in the concrete class's MRO). All real type checking
of session/config objects happens at their construction sites.

This is the first slice of the ``tui/app.py`` decomposition: the model,
scoped-model and theme pickers, which depend on no app-local helper functions.
Later slices (session/tree/login pickers, then the extension reconcile cluster)
can follow the same pattern once their helper families are relocated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from baldric_coding.rendering.themes import available_tui_theme_names
from baldric_coding.tui.screens.model_picker import ModelPickerScreen
from baldric_coding.tui.screens.theme import ThemePickerScreen

if TYPE_CHECKING:
    from baldric_coding.session.session import ModelChoice
    from baldric_coding.tui.config import TuiThemeName

__all__ = ["PickerMixin"]


class PickerMixin:
    """Model / scoped-model / theme picker orchestration for ``BaldricTuiApp``.

    Mixed into the app; bodies are moved verbatim from ``BaldricTuiApp`` so call
    sites and behaviour are unchanged. ``self`` is the app at runtime.
    """

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

    def _handle_scoped_models_picker_result(
        self: Any, picker: ModelPickerScreen, choice: ModelChoice | None
    ) -> None:
        del choice
        picker.cancel_refresh()
        if (
            picker.initial_thinking_level is not None
            and picker.initial_thinking_level != self.session.thinking_level
        ):
            self.call_after_refresh(self._refresh_chrome)

    def _handle_model_picker_result(self: Any, picker: ModelPickerScreen, choice: ModelChoice | None) -> None:
        picker.cancel_refresh()
        if choice is not None:
            self.call_after_refresh(self._start_selected_model_switch, choice)

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
