"""Guard: picker/extension orchestration lives in mixins, not on the app.

The TUI app was decomposed by moving cohesive method families into mixins:
``tui/pickers.py`` (model/theme), ``tui/session_pickers.py``
(session/tree/skill/login), and ``tui/extension_components.py`` (the extension
slot/sidebar/main-view reconcile cluster). A future edit could re-inline them or
leave a duplicate definition; these assertions keep the split real and singular.
"""

from __future__ import annotations

from baldric.runtime.frontends.tui.app import BaldricTuiApp
from baldric.runtime.frontends.tui.extension_components import ExtensionComponentsMixin
from baldric.runtime.frontends.tui.pickers import PickerMixin
from baldric.runtime.frontends.tui.session_pickers import SessionPickerMixin

_PICKER_METHODS = (
    # model / scoped-model / theme (PickerMixin)
    "_open_model_picker",
    "_start_model_picker_refresh",
    "_refresh_open_model_picker",
    "_open_scoped_models_picker",
    "_handle_scoped_models_picker_result",
    "_handle_model_picker_result",
    "_open_theme_picker",
    "_handle_theme_picker_result",
    # session / tree / skill / login / logout (SessionPickerMixin)
    "action_open_session_picker",
    "_refresh_open_session_picker",
    "_wait_for_open_session_picker",
    "_handle_session_picker_result",
    "_open_skills_picker",
    "_handle_skill_picker_result",
    "_open_tree_picker",
    "_handle_tree_picker_result",
    "_open_login_picker",
    "_handle_login_method_result",
    "_handle_login_provider_result",
    "_open_login",
    "_handle_login_result",
    "_open_logout_picker",
    "_handle_logout_provider_result",
)

_EXTENSION_METHODS = (
    "_connect_extension_runtime",
    "_reconcile_slot",
    "_reconcile_sidebar",
    "_reconcile_main_view",
    "_refresh_extension_components",
    "_clear_extension_components",
    "_quarantine_extension_widget",
    "_record_extension_component_failure",
    "_toggle_sidebar_visibility",
)


def test_mixins_are_bases_of_the_app() -> None:
    mro = BaldricTuiApp.__mro__
    assert PickerMixin in mro
    assert SessionPickerMixin in mro
    assert ExtensionComponentsMixin in mro
    # PickerMixin composes SessionPickerMixin (one picker entry point).
    assert SessionPickerMixin in PickerMixin.__mro__


def test_picker_methods_are_provided_by_mixins_not_the_app() -> None:
    for name in _PICKER_METHODS:
        assert callable(getattr(PickerMixin, name)), f"PickerMixin missing {name}"
        assert name not in BaldricTuiApp.__dict__, (
            f"{name} is redefined on BaldricTuiApp; it belongs to a picker mixin"
        )


def test_extension_methods_are_provided_by_the_mixin_not_the_app() -> None:
    for name in _EXTENSION_METHODS:
        assert callable(getattr(ExtensionComponentsMixin, name)), f"ExtensionComponentsMixin missing {name}"
        assert name not in BaldricTuiApp.__dict__, (
            f"{name} is redefined on BaldricTuiApp; it belongs to ExtensionComponentsMixin"
        )
