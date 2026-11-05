"""Shared test helpers for TUI tests.

These helpers are importable by any test file without creating a test-package
dependency on ``test_tui_app``. They do not run any tests themselves.
"""

from __future__ import annotations

from baldric_coding.tui.app import BaldricTuiApp, _TuiExtensionUiBridge


def _component_bridge(app: BaldricTuiApp) -> _TuiExtensionUiBridge:
    """Return a host component bridge bound to a running app."""
    return _TuiExtensionUiBridge(app)