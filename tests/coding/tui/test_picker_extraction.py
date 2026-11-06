"""Guard: picker orchestration lives on PickerMixin and is mixed into the app.

The model/scoped-model/theme picker methods were extracted from
``BaldricTuiApp`` into ``baldric_coding.tui.pickers.PickerMixin`` (first slice of
the ``tui/app.py`` decomposition). A future edit could re-inline them, drop the
mixin base, or leave a duplicate definition; these assertions keep the split
real and singular.
"""

from __future__ import annotations

from baldric_coding.tui.app import BaldricTuiApp
from baldric_coding.tui.pickers import PickerMixin

_EXTRACTED = (
    "_open_model_picker",
    "_start_model_picker_refresh",
    "_refresh_open_model_picker",
    "_open_scoped_models_picker",
    "_handle_scoped_models_picker_result",
    "_handle_model_picker_result",
    "_open_theme_picker",
    "_handle_theme_picker_result",
)


def test_picker_mixin_is_a_base_of_the_app() -> None:
    assert PickerMixin in BaldricTuiApp.__mro__


def test_extracted_picker_methods_are_provided_by_the_mixin() -> None:
    for name in _EXTRACTED:
        assert hasattr(PickerMixin, name), f"PickerMixin missing {name}"
        # The app resolves it through the mixin, not its own dict.
        assert name not in BaldricTuiApp.__dict__, (
            f"{name} is redefined on BaldricTuiApp; it belongs to PickerMixin"
        )


def test_app_still_dispatches_the_picker_methods() -> None:
    # Sanity: the app instance exposes them (mixin provides them).
    for name in _EXTRACTED:
        assert callable(getattr(BaldricTuiApp, name))
