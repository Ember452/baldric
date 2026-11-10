"""Tests for the searchable extensions inventory modal."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from textual.widgets import Input, Static

from baldric.coding.tui.app import BaldricTuiApp
from baldric.coding.tui.config import BALDRIC_DARK_THEME
from baldric.coding.tui.screens.extensions import ExtensionsScreen
from tests.helpers.tui_helpers import FakeSession


@pytest.mark.anyio
async def test_extensions_screen_inventory_filter_empty_and_cancel() -> None:
    runtime = SimpleNamespace(
        extension_info=(
            SimpleNamespace(
                name="Alpha Tools",
                scope="user",
                status="loaded",
                path="/home/user/.baldric/extensions/alpha.py",
            ),
            SimpleNamespace(
                name="Beta",
                scope="explicit",
                status="loaded",
                path="/tmp/beta.py",
            ),
        ),
        diagnostics=(),
    )
    app = BaldricTuiApp(FakeSession())

    async with app.run_test() as pilot:
        screen = ExtensionsScreen(runtime, theme=BALDRIC_DARK_THEME)
        app.push_screen(screen)
        await pilot.pause()
        assert len(screen.query("#extensions-list ListItem")) == 2

        search = screen.query_one("#extensions-search", Input)
        search.value = "ALPHA"
        await pilot.pause()
        assert len(screen.visible_rows) == 1
        assert screen.visible_rows[0].name == "Alpha Tools"

        search.value = "missing"
        await pilot.pause()
        assert screen.visible_rows == ()
        help_text = screen.query_one("#extensions-help", Static).render()
        assert "No matching extensions" in str(help_text)

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, ExtensionsScreen)


@pytest.mark.anyio
async def test_extensions_screen_shows_diagnostics() -> None:
    from baldric.coding.context.resources import ResourceDiagnostic

    runtime = SimpleNamespace(
        extension_info=(),
        diagnostics=(
            ResourceDiagnostic(
                kind="extension",
                name="Broken",
                message="import failed",
                severity="error",
            ),
        ),
    )
    app = BaldricTuiApp(FakeSession())

    async with app.run_test() as pilot:
        screen = ExtensionsScreen(runtime, theme=BALDRIC_DARK_THEME)
        app.push_screen(screen)
        await pilot.pause()

        assert len(screen.query("#extensions-list ListItem")) == 1
        assert screen.rows[0].name == "Broken"
        assert "import failed" in screen.rows[0].detail


@pytest.mark.anyio
async def test_extensions_screen_empty_state() -> None:
    app = BaldricTuiApp(FakeSession())

    async with app.run_test() as pilot:
        screen = ExtensionsScreen(
            SimpleNamespace(extension_info=(), diagnostics=()), theme=BALDRIC_DARK_THEME
        )
        app.push_screen(screen)
        await pilot.pause()

        assert "No extensions loaded" in str(screen.query_one("#extensions-help", Static).render())
