import asyncio

import pytest
from textual.containers import Container
from textual.widgets import (
    Input,
    Static,
)

from baldric_coding.tui.app import (
    RESERVED_EXTENSION_INTERCEPTOR_KEYS,
    BaldricTuiApp,
    ExtensionConfirmScreen,
    LoginMethodPickerScreen,
    PromptInput,
)
from baldric_coding.tui.widgets import (
    TranscriptView,
)
from tests.helpers.tui_helpers import (
    FakeSession,
    _component_bridge,
    _RenderCallRuntime,
)


class _CrashOnRender(Static):
    def render(self):  # noqa: ANN201
        raise RuntimeError("boom-in-render")


class _CrashOnMount(Static):
    def on_mount(self) -> None:
        raise RuntimeError("boom-in-on-mount")


@pytest.mark.anyio
async def test_component_slot_widget_mounts_and_unmounts() -> None:
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)

        bridge.set_slot_widget(
            "demo",
            lambda theme: Static("slot-content", id="ext-slot-demo"),
            placement="below_prompt",
        )
        await pilot.pause()

        slot = app.query_one("#below-prompt-slot", Container)
        assert slot.query("#ext-slot-demo")
        assert "demo" in app._extension_slot_widgets

        bridge.set_slot_widget("demo", None, placement="below_prompt")
        await pilot.pause()
        assert not slot.query("#ext-slot-demo")
        assert "demo" not in app._extension_slot_widgets


@pytest.mark.anyio
async def test_component_slot_widget_replace_reregisters() -> None:
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)

        bridge.set_slot_widget("k", lambda theme: Static("one", id="ext-one"), placement="below_prompt")
        await pilot.pause()
        bridge.set_slot_widget("k", lambda theme: Static("two", id="ext-two"), placement="below_prompt")
        await pilot.pause()

        slot = app.query_one("#below-prompt-slot", Container)
        assert not slot.query("#ext-one")
        assert slot.query("#ext-two")
        assert len(app._extension_slot_widgets) == 1


@pytest.mark.anyio
async def test_component_slot_widget_strings_mount_and_render() -> None:
    """A plain list of lines mounts as a Static the host builds (no widget defined)."""
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)

        bridge.set_slot_widget("lines", ["hello", "world"], placement="below_prompt")
        await pilot.pause()

        slot = app.query_one("#below-prompt-slot", Container)
        statics = slot.query(Static)
        assert statics
        text = statics.first().render().plain
        assert "hello" in text
        assert "world" in text
        assert "lines" in app._extension_slot_widgets


@pytest.mark.anyio
async def test_component_slot_widget_strings_replace_updates_content() -> None:
    """Re-setting a key with different lines replaces the rendered content."""
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)

        bridge.set_slot_widget("lines", ["first"], placement="below_prompt")
        await pilot.pause()
        bridge.set_slot_widget("lines", ["second"], placement="below_prompt")
        await pilot.pause()

        slot = app.query_one("#below-prompt-slot", Container)
        statics = slot.query(Static)
        assert len(statics) == 1
        text = statics.first().render().plain
        assert "second" in text
        assert "first" not in text


@pytest.mark.anyio
async def test_component_slot_widget_strings_none_unmounts() -> None:
    """Setting a string slot to None unmounts and forgets the key."""
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)

        bridge.set_slot_widget("lines", ["visible"], placement="below_prompt")
        await pilot.pause()
        slot = app.query_one("#below-prompt-slot", Container)
        assert slot.query(Static)

        bridge.set_slot_widget("lines", None, placement="below_prompt")
        await pilot.pause()
        assert not slot.query(Static)
        assert "lines" not in app._extension_slot_widgets


@pytest.mark.anyio
async def test_component_slot_widget_strings_malformed_markup_falls_back() -> None:
    """Malformed Rich markup in a string widget renders literally, never crashes."""
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)

        # An unclosed tag is invalid Rich markup; from_markup would raise.
        bridge.set_slot_widget("bad", ["[not-a-tag"], placement="below_prompt")
        await pilot.pause()

        assert app.is_running
        slot = app.query_one("#below-prompt-slot", Container)
        statics = slot.query(Static)
        assert statics
        text = statics.first().render().plain
        assert "[not-a-tag" in text
        assert app._extension_component_failures_reported == set()


@pytest.mark.anyio
async def test_component_slot_widget_default_placement_is_above_prompt() -> None:
    """With no explicit placement, a slot widget mounts into #above-prompt-slot."""
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)

        bridge.set_slot_widget("k", lambda theme: Static("x", id="ext-default"))
        await pilot.pause()

        assert app.query_one("#above-prompt-slot", Container).query("#ext-default")
        assert not app.query_one("#below-prompt-slot", Container).query("#ext-default")


@pytest.mark.anyio
async def test_component_main_view_open_and_close_restores_transcript() -> None:
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)

        handle = bridge.open_main_view(lambda handle, theme: Static("main-view", id="ext-main-view"))
        await pilot.pause()

        assert handle.is_open
        assert app.query_one("#main-slot", Container).display
        assert not app.query_one("#transcript", TranscriptView).display
        assert app.query("#ext-main-view")

        handle.close()
        await pilot.pause()

        assert not handle.is_open
        assert not app.query_one("#main-slot", Container).display
        assert app.query_one("#transcript", TranscriptView).display
        assert not app.query("#ext-main-view")
        assert app.query_one("#prompt", PromptInput).has_focus


@pytest.mark.anyio
async def test_click_does_not_steal_focus_while_main_view_open() -> None:
    # The app-level click handler refocuses the prompt after main-TUI clicks,
    # but an open extension main view owns the keyboard: yanking focus back
    # would silently reroute esc/toggles/typed text to the main chat.
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)

        view = Static("main-view", id="ext-main-view")
        view.can_focus = True
        bridge.open_main_view(lambda handle, theme: view)
        await pilot.pause()
        view.focus()
        await pilot.pause()
        assert app.screen.focused is view

        await pilot.click("#ext-main-view")
        await pilot.pause()

        assert app.screen.focused is view
        assert not app.query_one("#prompt", PromptInput).has_focus


@pytest.mark.anyio
async def test_component_main_view_close_result_resolves_wait() -> None:
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)

        handle = bridge.open_main_view(lambda handle, theme: Static("main-view", id="ext-main-view"))
        await pilot.pause()

        sentinel = object()
        handle.close(sentinel)
        # wait() may be awaited after close already happened: returns at once.
        assert await handle.wait() is sentinel
        # Idempotent: a later close does not overwrite the first result.
        handle.close("ignored")
        assert await handle.wait() is sentinel


@pytest.mark.anyio
async def test_component_main_view_close_without_result_resolves_none() -> None:
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)

        handle = bridge.open_main_view(lambda handle, theme: Static("main-view", id="ext-main-view"))
        await pilot.pause()

        handle.close()
        assert await handle.wait() is None


@pytest.mark.anyio
async def test_component_main_view_superseded_resolves_first_wait_with_none() -> None:
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)

        first = bridge.open_main_view(lambda h, theme: Static("one", id="ext-one"))
        await pilot.pause()
        assert first.is_open

        # Opening a second view supersedes (last writer wins) the first.
        second = bridge.open_main_view(lambda h, theme: Static("two", id="ext-two"))
        await pilot.pause()

        assert not first.is_open
        assert await first.wait() is None
        assert second.is_open


@pytest.mark.anyio
async def test_component_main_view_rebind_resolves_pending_wait_with_none() -> None:
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)

        handle = bridge.open_main_view(lambda h, theme: Static("v", id="ext-view"))
        await pilot.pause()

        # Start awaiting before the teardown so a leaked future would hang here.
        waiter = asyncio.ensure_future(handle.wait())
        await pilot.pause()
        assert not waiter.done()

        app._clear_extension_components()
        await pilot.pause()

        assert not handle.is_open
        assert await asyncio.wait_for(waiter, timeout=1.0) is None


@pytest.mark.anyio
async def test_component_key_interceptor_consumes_and_gates_on_prompt_text() -> None:
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)
        seen: list[tuple[str, str]] = []

        def interceptor(event, text: str) -> bool:  # noqa: ANN001
            seen.append((event.key, text))
            return event.key == "j" and text == ""

        bridge.register_key_interceptor(interceptor)

        prompt = app.query_one("#prompt", PromptInput)
        prompt.focus()
        await pilot.pause()

        # Empty prompt: interceptor consumes "j" (nothing typed).
        await pilot.press("j")
        assert prompt.text == ""
        # Non-empty prompt: interceptor declines, so "j" types normally.
        await pilot.press("a")
        await pilot.press("j")
        assert prompt.text == "aj"
        assert ("j", "") in seen


@pytest.mark.anyio
async def test_component_consumed_escape_preempts_cancel() -> None:
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)
        cancels: list[int] = []
        app.action_cancel = lambda: cancels.append(1)  # type: ignore[method-assign]

        unsubscribe = bridge.register_key_interceptor(lambda event, text: event.key == "escape")
        app.query_one("#prompt", PromptInput).focus()
        await pilot.pause()

        await pilot.press("escape")
        await pilot.pause()
        assert cancels == []  # interceptor consumed escape before action_cancel

        # With no interceptor consuming it, escape falls through to cancel.
        unsubscribe()
        await pilot.press("escape")
        await pilot.pause()
        assert cancels == [1]


@pytest.mark.anyio
async def test_component_key_interceptor_failure_degrades_to_typing() -> None:
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)

        def boom(event, text: str) -> bool:  # noqa: ANN001
            raise RuntimeError("interceptor exploded")

        bridge.register_key_interceptor(boom)
        prompt = app.query_one("#prompt", PromptInput)
        prompt.focus()
        await pilot.pause()

        await pilot.press("z")
        assert prompt.text == "z"  # broken interceptor never blocks typing
        assert app.is_running
        # Failures are keyed per-interceptor now (so a second faulty handler
        # still gets diagnosed) and notify like the other failure classes.
        assert any(key.startswith("key_interceptor:") for key in app._extension_component_failures_reported)


@pytest.mark.anyio
async def test_component_key_interceptor_preempts_priority_binding() -> None:
    """A key bound with priority=True on the app (down) is still interceptable.

    down/up/tab/alt+enter are app-level priority bindings, which Textual checks
    before forwarding a key to the focused widget. The interceptor now runs in
    BaldricTuiApp.on_event, ahead of that priority check, so it can own those keys.
    """
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)
        completion_next: list[int] = []
        app.action_completion_next = lambda: completion_next.append(1)  # type: ignore[method-assign]

        seen: list[str] = []

        def interceptor(event, text: str) -> bool:  # noqa: ANN001
            seen.append(event.key)
            return event.key == "down"

        bridge.register_key_interceptor(interceptor)
        app.query_one("#prompt", PromptInput).focus()
        await pilot.pause()

        await pilot.press("down")
        await pilot.pause()

        assert "down" in seen  # interceptor saw the priority-bound key
        assert completion_next == []  # completion_next preempted, not run


@pytest.mark.anyio
async def test_component_key_interceptor_skipped_while_modal_open() -> None:
    """Interceptors see main-screen keys only; a modal on top is never intercepted."""
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)
        seen: list[str] = []

        # Consume everything — so if this fired while the modal is up, the modal
        # could never be dismissed.
        bridge.register_key_interceptor(lambda event, text: (seen.append(event.key), True)[1])

        confirm_task = asyncio.ensure_future(bridge.confirm("Ship?", "to prod"))
        await pilot.pause()
        assert isinstance(app.screen, ExtensionConfirmScreen)

        # A key while the modal is on top must NOT reach the interceptor.
        await pilot.press("j")
        await pilot.pause()
        assert "j" not in seen

        # And the modal still handles its own keys (escape dismisses -> False).
        await pilot.press("escape")
        assert await confirm_task is False
        assert "escape" not in seen


@pytest.mark.anyio
async def test_component_interceptor_never_consumes_reserved_interrupt_keys() -> None:
    """The hard interrupt/exit keys bypass the interceptor entirely.

    A buggy interceptor that returns True for everything must not be able to
    swallow ctrl+c/ctrl+d and brick the session: those keys are skipped before
    the consult (never reach the interceptor) and flow to normal dispatch, so
    the app's escape hatches always fire. Everything else (e.g. escape) stays
    interceptable.
    """
    assert "ctrl+c" in RESERVED_EXTENSION_INTERCEPTOR_KEYS
    assert "ctrl+d" in RESERVED_EXTENSION_INTERCEPTOR_KEYS
    assert "escape" not in RESERVED_EXTENSION_INTERCEPTOR_KEYS

    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)
        seen: list[str] = []
        quits: list[int] = []

        async def fake_quit() -> None:  # don't actually tear down the pilot
            quits.append(1)

        app.action_quit = fake_quit  # type: ignore[method-assign]

        # Greedy interceptor: consumes literally every key it is consulted for.
        bridge.register_key_interceptor(lambda event, text: (seen.append(event.key), True)[1])
        prompt = app.query_one("#prompt", PromptInput)
        prompt.focus()
        await pilot.pause()

        # ctrl+c (SIGINT/interrupt reflex, bound to clear_prompt): never consulted,
        # and its bound action still fires (the prompt is cleared).
        prompt.text = "hi"
        prompt.move_cursor((0, 2))
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert "ctrl+c" not in seen
        assert prompt.text == ""

        # ctrl+d (quit / hard exit): never consulted, and quit still fires.
        await pilot.press("ctrl+d")
        await pilot.pause()
        assert "ctrl+d" not in seen
        assert quits == [1]

        # A non-reserved key is still routed through the interceptor.
        await pilot.press("escape")
        await pilot.pause()
        assert "escape" in seen


@pytest.mark.anyio
async def test_component_factory_crash_is_isolated() -> None:
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)

        def exploding_factory(theme):  # noqa: ANN001, ANN202
            raise RuntimeError("factory exploded")

        bridge.set_slot_widget("bad", exploding_factory, placement="below_prompt")
        await pilot.pause()

        assert app.is_running
        assert "bad" not in app._extension_slot_widgets
        assert not app.query_one("#below-prompt-slot", Container).children
        assert "slot:bad" in app._extension_component_failures_reported


@pytest.mark.anyio
async def test_component_render_crash_is_quarantined() -> None:
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)

        bridge.set_slot_widget("crash", lambda theme: _CrashOnRender("x", id="ext-crash"))
        await pilot.pause()
        await pilot.pause()

        # The app survives the render exception and the widget is quarantined.
        assert app.is_running
        assert "crash" not in app._extension_slot_widgets
        assert not app.query("#ext-crash")


@pytest.mark.anyio
async def test_component_mount_crash_is_quarantined() -> None:
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)

        bridge.set_slot_widget("crash", lambda theme: _CrashOnMount("x", id="ext-crash-mount"))
        # A widget that crashes in on_mount never finishes mounting, so its
        # pending message never drains (pilot.pause would time out); sleep to
        # let _handle_exception run instead. The app must stay alive and the
        # widget must be untracked and made inert.
        await asyncio.sleep(0.3)

        assert app.is_running
        assert "crash" not in app._extension_slot_widgets
        ghosts = app.query("#ext-crash-mount")
        assert all(not widget.display for widget in ghosts)


@pytest.mark.anyio
async def test_component_bridge_clear_components_tears_down_extension_ui() -> None:
    # clear_components is the teardown seam the runtime drives on /reload and
    # session rebinds (resume/new): every slot widget, the main view (with its
    # pending wait() resolved), and all key interceptors must go.
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)

        bridge.set_slot_widget("k", lambda theme: Static("x", id="ext-bridge-clear"))
        unsubscribe = bridge.register_key_interceptor(lambda event, text: False)
        handle = bridge.open_main_view(lambda h, theme: Static("v", id="ext-bridge-view"))
        await pilot.pause()
        assert app._extension_slot_widgets
        assert app._extension_key_interceptors
        assert handle.is_open
        waiter = asyncio.ensure_future(handle.wait())

        bridge.clear_components()
        await pilot.pause()
        await pilot.pause()

        assert app._extension_slot_widgets == {}
        assert app._extension_key_interceptors == []
        assert app._extension_main_view is None
        assert not handle.is_open
        assert await waiter is None
        assert app.query_one("#transcript", TranscriptView).display
        assert not app.query("#ext-bridge-clear")
        assert not app.query("#ext-bridge-view")
        # A stale unsubscribe after the clear is a safe no-op.
        unsubscribe()


@pytest.mark.anyio
async def test_component_rebind_clears_slots_and_interceptors() -> None:
    app = BaldricTuiApp(FakeSession())

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        bridge = _component_bridge(app)

        bridge.set_slot_widget("k", lambda theme: Static("x", id="ext-rebind"))
        bridge.register_key_interceptor(lambda event, text: False)
        handle = bridge.open_main_view(lambda h, theme: Static("v", id="ext-view"))
        await pilot.pause()
        assert app._extension_slot_widgets
        assert app._extension_key_interceptors
        assert handle.is_open

        # Rebinding a session force-clears everything before the new bridge.
        session = FakeSession()
        session.extension_runtime = _RenderCallRuntime()  # type: ignore[attr-defined]
        app._connect_extension_runtime(session)  # type: ignore[arg-type]
        await pilot.pause()

        assert app._extension_slot_widgets == {}
        assert app._extension_key_interceptors == []
        assert app._extension_main_view is None
        assert not handle.is_open
        assert app.query_one("#transcript", TranscriptView).display
        assert not app.query("#ext-rebind")
        assert not app.query("#ext-view")


@pytest.mark.anyio
async def test_tui_login_provider_search_autofocus() -> None:
    app = BaldricTuiApp(FakeSession())

    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt")
        prompt.value = "/login"
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, LoginMethodPickerScreen)
        app.screen.action_cursor_down()
        app.screen.action_select_cursor()

        await pilot.wait_for_scheduled_animations()

        search = app.screen.query_one("#login-provider-search", Input)
        assert search.has_focus, "Search input failed to automatically gain focus on screen mount."
