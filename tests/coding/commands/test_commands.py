from pathlib import Path

from baldric_coding.commands.base import (
    CommandKind,
    CommandOutcome,
    MessageDisplay,
    PickerKind,
    message_outcome,
    not_handled,
)
from baldric_coding.commands.registry import CommandRegistry, SlashCommand, create_default_command_registry
from baldric_coding.config.paths import BaldricPaths
from baldric_coding.context.resources import ResourceDiagnostic
from baldric_coding.context.skills.skills import Skill
from baldric_coding.context.system_prompt import ProjectContextFile
from baldric_coding.session.manager import SessionManager
from baldric_coding.session.session import ModelChoice
from baldric_coding.tools.registry import create_coding_tools
from baldric_coding.update.reload import CodingReloadSummary, ReloadCategorySummary


class FakeSession:
    def __init__(self, tmp_path: Path, manager: SessionManager | None = None) -> None:
        self.cwd = tmp_path
        self.provider_name = "openai"
        self.inference_provider: str | None = None
        self.inference_provider_mode = "automatic"
        self.model = "fake-model"
        self.available_models = ("fake-model", "other-model")
        self.available_model_choices = (
            ModelChoice(provider_name="openai", model="fake-model"),
            ModelChoice(provider_name="openai", model="other-model"),
            ModelChoice(provider_name="local", model="local-model"),
        )
        self.available_providers = ("openai", "local")
        self.tools = tuple(create_coding_tools(cwd=tmp_path))
        self.skills = (
            Skill(
                name="review",
                path=tmp_path / "review.md",
                content="Review code",
                description="Review code",
            ),
        )
        self.prompt_templates = ()
        self.context_files = (
            ProjectContextFile(path=str(tmp_path / "AGENTS.md"), content="Follow instructions."),
        )
        self.context_token_estimate = 123
        self.auto_compact_token_threshold = 200
        self.context_window_tokens = 584
        self.thinking_level = "medium"
        self.available_thinking_levels = ("off", "minimal", "low", "medium", "high", "xhigh")
        self.thinking_unavailable_reason: str | None = None
        self.tui_theme = "baldric-dark"
        self.resource_diagnostics = ()
        self.system_prompt = "You are Baldric.\nFollow project instructions."
        self.session_id = "session-1"
        self.session_title: str | None = None
        self.session_manager: SessionManager | None = manager
        self.ensure_session_indexed_called = False
        self.reload_called = False
        self.provider_reload_called = False

    def ensure_session_indexed(self) -> None:
        self.ensure_session_indexed_called = True
        if self.session_manager is not None:
            self.session_manager.create_session(
                cwd=self.cwd,
                model=self.model,
                provider_name=self.provider_name,
                session_id=self.session_id,
            )

    def set_model(self, model: str) -> None:
        self.model = model

    def set_inference_provider(self, route: str | None) -> str:
        self.inference_provider = route
        self.inference_provider_mode = "fixed" if route is not None else "automatic"
        return route or "automatic (will pin after the next successful response)"

    def set_provider(self, provider_name: str) -> None:
        self.provider_name = provider_name
        self.model = "local-model"
        self.available_models = ("local-model",)

    def reload(self) -> CodingReloadSummary:
        self.reload_called = True
        return CodingReloadSummary(
            skills=ReloadCategorySummary(before=0, after=len(self.skills), changed=True),
            prompt_templates=ReloadCategorySummary(
                before=0,
                after=len(self.prompt_templates),
                changed=False,
            ),
            context_files=ReloadCategorySummary(
                before=0,
                after=len(self.context_files),
                changed=True,
            ),
            extensions=ReloadCategorySummary(before=0, after=0, changed=False),
            diagnostics=ReloadCategorySummary(
                before=0,
                after=len(self.resource_diagnostics),
                changed=False,
            ),
            system_prompt_rebuilt=True,
        )

    def reload_provider_settings(self) -> None:
        self.provider_reload_called = True


def test_registry_ignores_ordinary_prompts_and_skill_expansion(tmp_path: Path) -> None:
    registry = create_default_command_registry()
    session = FakeSession(tmp_path)

    assert registry.execute(session, "hello").handled is False
    assert registry.execute(session, "/skill:review fix this").handled is False


def test_registry_ignores_unregistered_slash_prompts(tmp_path: Path) -> None:
    registry = create_default_command_registry()
    session = FakeSession(tmp_path)

    for prompt in ("/missing", "/README.md", "/tmp", "/Users/me/screenshot.png"):
        result = registry.execute(session, prompt)
        assert result.outcome == not_handled()


def test_registered_commands_are_expected(tmp_path: Path) -> None:
    commands = create_default_command_registry().list_commands()

    assert [command.name for command in commands] == [
        "approvals",
        "compact",
        "context",
        "diagnostics",
        "export",
        "extensions",
        "help",
        "hotkeys",
        "local",
        "login",
        "logout",
        "model",
        "name",
        "new",
        "prompts",
        "quit",
        "reload",
        "resume",
        "scoped-models",
        "session",
        "sidebar",
        "skill",
        "skills",
        "system",
        "theme",
        "thinking",
        "tools",
        "tree",
    ]


def test_diagnostics_command_shows_empty_state(tmp_path: Path) -> None:
    result = create_default_command_registry().execute(FakeSession(tmp_path), "/diagnostics")

    assert result.outcome == message_outcome("No resource diagnostics.")
    assert (
        create_default_command_registry()
        .execute(FakeSession(tmp_path), "/diagnostics extra")
        .outcome
        == message_outcome("Usage: /diagnostics")
    )


def test_extensions_command_requests_inventory_modal(tmp_path: Path) -> None:
    result = create_default_command_registry().execute(FakeSession(tmp_path), "/extensions")

    assert result.outcome == CommandOutcome(
        kind=CommandKind.OPEN_PICKER, picker=PickerKind.EXTENSIONS
    )
    assert (
        create_default_command_registry()
        .execute(FakeSession(tmp_path), "/extensions extra")
        .outcome
        == message_outcome("Usage: /extensions")
    )


def test_diagnostics_command_shows_complete_literal_details(tmp_path: Path) -> None:
    session = FakeSession(tmp_path)
    prompt_path = tmp_path / "[project]" / "prompts" / "review.md"
    session.resource_diagnostics = (
        ResourceDiagnostic(
            kind="prompt",
            name="review",
            path=prompt_path,
            severity="warning",
            message="template [ignored] because it is invalid",
        ),
        ResourceDiagnostic(
            kind="extension",
            severity="error",
            message="setup failed",
        ),
    )

    result = create_default_command_registry().execute(session, "/diagnostics")

    assert result.outcome == message_outcome(
        "\n".join(
            [
                "Resource diagnostics (2):",
                "",
                "1. WARNING",
                "Kind: prompt",
                "Name: review",
                f"Path: {prompt_path}",
                "Message: template [ignored] because it is invalid",
                "",
                "2. ERROR",
                "Kind: extension",
                "Message: setup failed",
            ]
        )
    )


def test_local_command_requests_host_action(tmp_path: Path) -> None:
    registry = create_default_command_registry()
    session = FakeSession(tmp_path)

    assert registry.execute(session, "/local").outcome == CommandOutcome(
        kind=CommandKind.OPEN_PICKER, picker=PickerKind.LOCAL_BACKEND
    )
    assert registry.execute(session, "/local extra").outcome == message_outcome("Usage: /local")


def test_sidebar_command_requests_host_action(tmp_path: Path) -> None:
    registry = create_default_command_registry()
    session = FakeSession(tmp_path)

    result = registry.execute(session, "/sidebar")

    assert result.outcome.kind is CommandKind.TOGGLE_SIDEBAR
    assert registry.execute(session, "/sidebar extra").outcome == message_outcome("Usage: /sidebar")


def test_approvals_command_requests_toggle_and_rejects_args(tmp_path: Path) -> None:
    registry = create_default_command_registry()
    session = FakeSession(tmp_path)

    result = registry.execute(session, "/approvals")

    assert result.outcome.kind is CommandKind.TOGGLE_APPROVALS
    assert registry.execute(session, "/approvals extra").outcome == message_outcome(
        "Usage: /approvals"
    )


def test_prompts_command_requests_picker(tmp_path: Path) -> None:
    registry = create_default_command_registry()
    session = FakeSession(tmp_path)

    assert registry.execute(session, "/prompts").outcome == CommandOutcome(
        kind=CommandKind.OPEN_PICKER, picker=PickerKind.PROMPTS
    )
    assert registry.execute(session, "/prompts extra").outcome == message_outcome("Usage: /prompts")


def test_system_command_returns_active_prompt(tmp_path: Path) -> None:
    registry = create_default_command_registry()
    session = FakeSession(tmp_path)

    result = registry.execute(session, "/system")

    assert result.outcome.kind is CommandKind.MESSAGE
    assert result.outcome.display is MessageDisplay.TRANSCRIPT
    assert result.outcome.message == (
        "#### 01 · Effective system prompt\n\n"
        "**Source:** `active Baldric session`\n\n"
        "You are Baldric.\nFollow project instructions."
    )
    assert result.outcome.system_prompt_inspection is not None
    assert registry.execute(session, "/system extra").outcome == message_outcome("Usage: /system")


def test_quit_and_new_return_control_flags(tmp_path: Path) -> None:
    registry = create_default_command_registry()
    session = FakeSession(tmp_path)

    assert registry.execute(session, "/quit").outcome.kind is CommandKind.EXIT
    assert registry.execute(session, "/exit").outcome.kind is CommandKind.EXIT
    assert registry.execute(session, "/q").outcome == not_handled()
    assert registry.execute(session, "/new").outcome.kind is CommandKind.NEW_SESSION
    assert registry.execute(session, "/clear").outcome == not_handled()


def test_compact_command_accepts_optional_instructions(tmp_path: Path) -> None:
    registry = create_default_command_registry()
    session = FakeSession(tmp_path)

    default = registry.execute(session, "/compact")
    requested = registry.execute(session, "/compact Summary of prior work.")

    assert default.outcome == CommandOutcome(kind=CommandKind.COMPACT, text="")
    assert requested.outcome == CommandOutcome(
        kind=CommandKind.COMPACT, text="Summary of prior work."
    )


def test_skills_command_requests_picker(tmp_path: Path) -> None:
    registry = create_default_command_registry()
    session = FakeSession(tmp_path)

    result = registry.execute(session, "/skills")

    assert result.outcome == CommandOutcome(kind=CommandKind.OPEN_PICKER, picker=PickerKind.SKILLS)
    assert registry.execute(session, "/skills extra").outcome == message_outcome("Usage: /skills")


def test_tree_command_requests_picker(tmp_path: Path) -> None:
    registry = create_default_command_registry()
    session = FakeSession(tmp_path)

    result = registry.execute(session, "/tree")
    with_args = registry.execute(session, "/tree root")

    assert result.outcome == CommandOutcome(kind=CommandKind.OPEN_PICKER, picker=PickerKind.TREE)
    assert with_args.outcome == message_outcome("Usage: /tree")


def test_export_command_requests_default_export(tmp_path: Path) -> None:
    result = create_default_command_registry().execute(FakeSession(tmp_path), "/export")

    assert result.outcome == CommandOutcome(kind=CommandKind.EXPORT)


def test_export_command_parses_format_and_destination(tmp_path: Path) -> None:
    result = create_default_command_registry().execute(
        FakeSession(tmp_path),
        "/export --format jsonl exports/session.jsonl",
    )

    assert result.outcome == CommandOutcome(
        kind=CommandKind.EXPORT,
        text=str(Path("exports/session.jsonl")),
        format="jsonl",
    )


def test_session_command_includes_session_details(tmp_path: Path) -> None:
    result = create_default_command_registry().execute(FakeSession(tmp_path), "/session")

    assert result.outcome.kind is CommandKind.MESSAGE
    assert result.outcome.message is not None
    assert "Model: fake-model" in result.outcome.message
    assert f"CWD: {tmp_path}" in result.outcome.message
    assert "Tools: 4" in result.outcome.message
    assert "Skills: 1" in result.outcome.message
    assert "Context files: 1" in result.outcome.message
    assert "Estimated context tokens: 123" in result.outcome.message
    assert "Context window: 584" in result.outcome.message
    assert "Thinking mode: medium" in result.outcome.message
    assert "Auto compact threshold: 200" in result.outcome.message
    assert "Resource diagnostics: 0" in result.outcome.message
    assert "Session: session-1" in result.outcome.message
    assert "Session name:" not in result.outcome.message
    assert create_default_command_registry().execute(FakeSession(tmp_path), "/status").handled is False


def test_session_command_distinguishes_automatic_and_fixed_huggingface_routes(
    tmp_path: Path,
) -> None:
    session = FakeSession(tmp_path)
    session.provider_name = "huggingface"
    session.inference_provider = "baseten"

    automatic = create_default_command_registry().execute(session, "/session")
    session.inference_provider_mode = "fixed"
    fixed = create_default_command_registry().execute(session, "/session")

    assert automatic.outcome.kind is CommandKind.MESSAGE
    assert automatic.outcome.message is not None
    assert "Hugging Face inference provider: automatic (currently baseten)" in automatic.outcome.message
    assert fixed.outcome.kind is CommandKind.MESSAGE
    assert fixed.outcome.message is not None
    assert "Hugging Face inference provider: baseten (fixed)" in fixed.outcome.message


def test_route_command_is_not_built_in(tmp_path: Path) -> None:
    result = create_default_command_registry().execute(FakeSession(tmp_path), "/route deepinfra")

    assert result.outcome == not_handled()


def test_session_command_includes_named_session_title(tmp_path: Path) -> None:
    session = FakeSession(tmp_path)
    session.session_title = "Customer bugfix"

    result = create_default_command_registry().execute(session, "/session")

    assert result.outcome.kind is CommandKind.MESSAGE
    assert result.outcome.message is not None
    assert "Session: session-1" in result.outcome.message
    assert "Session name: Customer bugfix" in result.outcome.message


def test_session_command_explains_unavailable_thinking_controls(tmp_path: Path) -> None:
    session = FakeSession(tmp_path)
    session.available_thinking_levels = ()
    session.thinking_unavailable_reason = "Provider local does not declare thinking_levels"

    result = create_default_command_registry().execute(session, "/session")

    assert result.outcome.kind is CommandKind.MESSAGE
    assert result.outcome.message is not None
    assert "Thinking mode: unavailable" in result.outcome.message
    assert (
        "Thinking unavailable: Provider local does not declare thinking_levels"
        in result.outcome.message
    )
    assert "Thinking mode: medium" not in result.outcome.message


def test_hotkeys_command_lists_common_tui_shortcuts(tmp_path: Path) -> None:
    result = create_default_command_registry().execute(FakeSession(tmp_path), "/hotkeys")

    assert result.outcome.kind is CommandKind.MESSAGE
    assert result.outcome.message is not None
    assert "Common keyboard shortcuts:" in result.outcome.message
    assert "Ctrl+E: edit prompt in external editor ($VISUAL/$EDITOR)" in result.outcome.message
    assert "Ctrl+K: open slash-command completions" in result.outcome.message
    assert "Ctrl+R: open session picker" in result.outcome.message
    assert (
        "Ctrl+P / Shift+Ctrl+P: cycle scoped models forward / backward" in result.outcome.message
    )
    assert "Shift+Tab: cycle thinking mode" in result.outcome.message


def test_model_command_requests_picker_and_switches_models(tmp_path: Path) -> None:
    session = FakeSession(tmp_path)
    registry = create_default_command_registry()

    list_result = registry.execute(session, "/model")
    switch_result = registry.execute(session, "/model other-model")

    assert list_result.outcome == CommandOutcome(
        kind=CommandKind.OPEN_PICKER, picker=PickerKind.MODEL
    )
    assert switch_result.outcome == message_outcome("Current model: other-model")
    assert session.model == "other-model"
    assert session.provider_reload_called is False


def test_scoped_models_command_requests_scoped_picker(tmp_path: Path) -> None:
    session = FakeSession(tmp_path)
    registry = create_default_command_registry()

    dashed_result = registry.execute(session, "/scoped-models")
    pi_style_result = registry.execute(session, "/scoped models")

    assert dashed_result.outcome == CommandOutcome(
        kind=CommandKind.OPEN_PICKER, picker=PickerKind.SCOPED_MODELS
    )
    assert pi_style_result.outcome == CommandOutcome(
        kind=CommandKind.OPEN_PICKER, picker=PickerKind.SCOPED_MODELS
    )
    assert session.provider_reload_called is False


def test_model_command_rejects_unknown_model(tmp_path: Path) -> None:
    session = FakeSession(tmp_path)

    result = create_default_command_registry().execute(session, "/model missing")

    assert result.outcome.kind is CommandKind.MESSAGE
    assert result.outcome.message is not None
    assert "Unknown model for provider openai: missing" in result.outcome.message
    assert session.model == "fake-model"


def test_model_pickers_open_even_if_provider_settings_cannot_reload(tmp_path: Path) -> None:
    class FailingRefreshSession(FakeSession):
        def reload_provider_settings(self) -> None:
            raise ValueError("active model is missing from the refreshed catalog")

    session = FailingRefreshSession(tmp_path)
    registry = create_default_command_registry()
    assert registry.execute(session, "/model").outcome == CommandOutcome(
        kind=CommandKind.OPEN_PICKER, picker=PickerKind.MODEL
    )
    assert registry.execute(session, "/scoped-models").outcome == CommandOutcome(
        kind=CommandKind.OPEN_PICKER, picker=PickerKind.SCOPED_MODELS
    )
    assert session.provider_reload_called is False


def test_theme_command_requests_picker_and_sets_theme(tmp_path: Path) -> None:
    session = FakeSession(tmp_path)
    registry = create_default_command_registry()

    list_result = registry.execute(session, "/theme")
    switch_result = registry.execute(session, "/theme baldric-light")
    unknown_result = registry.execute(session, "/theme solarized")

    assert list_result.outcome == CommandOutcome(
        kind=CommandKind.OPEN_PICKER, picker=PickerKind.THEME
    )
    assert switch_result.outcome == CommandOutcome(
        kind=CommandKind.THEME_SET, text="baldric-light"
    )
    assert unknown_result.outcome.kind is CommandKind.MESSAGE
    assert unknown_result.outcome.message is not None
    assert "Unknown theme: solarized" in unknown_result.outcome.message


def test_theme_command_accepts_registered_custom_theme(tmp_path: Path) -> None:
    from baldric_coding.rendering.themes import (
        THEME_COLOR_FIELDS,
        TRANSCRIPT_ROLES,
        parse_tui_theme_json,
        set_custom_tui_themes,
    )

    theme_data = {
        "name": "midnight",
        "colors": dict.fromkeys(THEME_COLOR_FIELDS, "#101010"),
        "roles": {role: {"border": "#101010", "body": "#e0e0e0"} for role in TRANSCRIPT_ROLES},
    }
    set_custom_tui_themes({"midnight": parse_tui_theme_json(theme_data)})
    try:
        result = create_default_command_registry().execute(FakeSession(tmp_path), "/theme midnight")
        unknown = create_default_command_registry().execute(FakeSession(tmp_path), "/theme nope")
    finally:
        set_custom_tui_themes({})

    assert result.outcome == CommandOutcome(kind=CommandKind.THEME_SET, text="midnight")
    assert unknown.outcome.kind is CommandKind.MESSAGE
    assert unknown.outcome.message is not None
    assert "midnight" in unknown.outcome.message


def test_non_pi_commands_are_not_registered(tmp_path: Path) -> None:
    registry = create_default_command_registry()
    session = FakeSession(tmp_path)

    # `/context` and `/help` are Baldric commands (implemented, tested, useful);
    # they were once forbidden here for pi-parity reasons. `/provider` and
    # `/resources` remain unregistered because the session commands cover them.
    for command in ("/provider", "/resources"):
        result = registry.execute(session, command)
        assert result.outcome == not_handled()


def test_tools_command_requests_read_only_picker(tmp_path: Path) -> None:
    result = create_default_command_registry().execute(FakeSession(tmp_path), "/tools")

    assert result.outcome == CommandOutcome(kind=CommandKind.OPEN_PICKER, picker=PickerKind.TOOLS)


def test_login_command_requests_provider_picker(tmp_path: Path) -> None:
    result = create_default_command_registry().execute(FakeSession(tmp_path), "/login")

    assert result.outcome == CommandOutcome(
        kind=CommandKind.OPEN_PICKER, picker=PickerKind.LOGIN_METHOD
    )


def test_login_command_requests_provider_login(tmp_path: Path) -> None:
    result = create_default_command_registry().execute(FakeSession(tmp_path), "/login openai")

    assert result.outcome == CommandOutcome(
        kind=CommandKind.OPEN_PICKER, picker=PickerKind.LOGIN_PROVIDER, provider="openai"
    )


def test_login_command_resolves_anthropic_auth_aliases(tmp_path: Path) -> None:
    registry = create_default_command_registry()
    session = FakeSession(tmp_path)

    api_result = registry.execute(session, "/login anthropic-api")
    subscription_result = registry.execute(session, "/login anthropic-subscription")

    assert api_result.outcome == CommandOutcome(
        kind=CommandKind.OPEN_PICKER,
        picker=PickerKind.LOGIN_PROVIDER,
        provider="anthropic",
        method="api-key",
    )
    assert subscription_result.outcome == CommandOutcome(
        kind=CommandKind.OPEN_PICKER,
        picker=PickerKind.LOGIN_PROVIDER,
        provider="anthropic",
        method="subscription",
    )


def test_login_command_lists_auth_aliases_for_unknown_provider(tmp_path: Path) -> None:
    result = create_default_command_registry().execute(FakeSession(tmp_path), "/login missing")

    assert result.outcome.kind is CommandKind.MESSAGE
    assert result.outcome.message is not None
    assert "anthropic-api" in result.outcome.message
    assert "anthropic-subscription" in result.outcome.message


def test_login_command_requests_custom_provider_login(tmp_path: Path) -> None:
    result = create_default_command_registry().execute(FakeSession(tmp_path), "/login custom")

    assert result.outcome == CommandOutcome(
        kind=CommandKind.OPEN_PICKER, picker=PickerKind.CUSTOM_PROVIDER_LOGIN
    )


def test_logout_command_requests_provider_picker(tmp_path: Path) -> None:
    result = create_default_command_registry().execute(FakeSession(tmp_path), "/logout")

    assert result.outcome == CommandOutcome(
        kind=CommandKind.OPEN_PICKER, picker=PickerKind.LOGOUT_PROVIDER
    )


def test_logout_command_requests_provider_logout(tmp_path: Path) -> None:
    result = create_default_command_registry().execute(FakeSession(tmp_path), "/logout openai")

    assert result.outcome == CommandOutcome(
        kind=CommandKind.OPEN_PICKER, picker=PickerKind.LOGOUT_PROVIDER, provider="openai"
    )


def test_logout_command_rejects_unknown_provider(tmp_path: Path) -> None:
    result = create_default_command_registry().execute(FakeSession(tmp_path), "/logout local")

    assert result.outcome.kind is CommandKind.MESSAGE
    assert result.outcome.message is not None
    assert "Unknown logout provider: local" in result.outcome.message


def test_reload_command_requests_async_session_reload(tmp_path: Path) -> None:
    session = FakeSession(tmp_path)

    result = create_default_command_registry().execute(session, "/reload")

    assert result.outcome == CommandOutcome(kind=CommandKind.RELOAD)
    assert session.reload_called is False
    assert session.provider_reload_called is False


def test_resume_without_argument_requests_picker(tmp_path: Path) -> None:
    manager = SessionManager(BaldricPaths(home=tmp_path / ".baldric", agents_home=tmp_path / ".agents"))
    session = FakeSession(tmp_path, manager=manager)

    result = create_default_command_registry().execute(session, "/resume")

    assert result.outcome == CommandOutcome(
        kind=CommandKind.OPEN_PICKER, picker=PickerKind.SESSION_RESUME
    )
    assert create_default_command_registry().execute(session, "/sessions").handled is False


def test_resume_command_requests_indexed_session(tmp_path: Path) -> None:
    manager = SessionManager(BaldricPaths(home=tmp_path / ".baldric", agents_home=tmp_path / ".agents"))
    record = manager.create_session(cwd=tmp_path, model="fake-model", title="Test session")
    session = FakeSession(tmp_path, manager=manager)

    result = create_default_command_registry().execute(session, f"/resume {record.id}")

    assert result.outcome == CommandOutcome(
        kind=CommandKind.OPEN_PICKER,
        picker=PickerKind.SESSION_RESUME,
        session_id=record.id,
    )


def test_resume_command_rejects_missing_or_unknown_session(tmp_path: Path) -> None:
    manager = SessionManager(BaldricPaths(home=tmp_path / ".baldric", agents_home=tmp_path / ".agents"))
    session = FakeSession(tmp_path, manager=manager)

    unknown = create_default_command_registry().execute(session, "/resume missing")

    assert unknown.outcome == message_outcome("Unknown session: missing")


def test_name_command_shows_current_name_and_usage(tmp_path: Path) -> None:
    manager = SessionManager(BaldricPaths(home=tmp_path / ".baldric", agents_home=tmp_path / ".agents"))
    record = manager.create_session(cwd=tmp_path, model="fake-model", title="Test session")
    session = FakeSession(tmp_path, manager=manager)
    session.session_id = record.id

    result = create_default_command_registry().execute(session, "/name")

    assert result.outcome == message_outcome(
        "Current session name: Test session\nUsage: /name <new name>"
    )


def test_name_command_requests_session_rename(tmp_path: Path) -> None:
    manager = SessionManager(BaldricPaths(home=tmp_path / ".baldric", agents_home=tmp_path / ".agents"))
    record = manager.create_session(cwd=tmp_path, model="fake-model", title="Old name")
    session = FakeSession(tmp_path, manager=manager)
    session.session_id = record.id

    result = create_default_command_registry().execute(session, "/name Customer bugfix")

    assert result.outcome.kind is CommandKind.SESSION_NAMED
    assert result.outcome.message == "Session renamed: Customer bugfix"
    assert result.outcome.text == "Customer bugfix"
    unchanged = manager.get_session(record.id)
    assert unchanged is not None
    assert unchanged.title == "Old name"


def test_name_command_defers_indexing_pending_session(tmp_path: Path) -> None:
    manager = SessionManager(BaldricPaths(home=tmp_path / ".baldric", agents_home=tmp_path / ".agents"))
    session = FakeSession(tmp_path, manager=manager)
    session.session_id = "pending-session"

    result = create_default_command_registry().execute(session, "/name Customer bugfix")

    assert result.outcome.kind is CommandKind.SESSION_NAMED
    assert result.outcome.message == "Session renamed: Customer bugfix"
    assert result.outcome.text == "Customer bugfix"
    assert session.ensure_session_indexed_called is False
    assert manager.get_session("pending-session") is None


def test_name_command_reports_missing_session_manager(tmp_path: Path) -> None:
    result = create_default_command_registry().execute(FakeSession(tmp_path), "/name Work")

    assert result.outcome == message_outcome("Session manager is not available.")


def test_name_command_rejects_multiline_name(tmp_path: Path) -> None:
    manager = SessionManager(BaldricPaths(home=tmp_path / ".baldric", agents_home=tmp_path / ".agents"))
    record = manager.create_session(cwd=tmp_path, model="fake-model")
    session = FakeSession(tmp_path, manager=manager)
    session.session_id = record.id

    result = create_default_command_registry().execute(session, "/name Bad\nName")

    assert result.outcome == message_outcome("Session name must be a single line.")
    assert manager.get_session(record.id) == record


def test_registry_rejects_duplicate_commands_and_aliases() -> None:
    registry = CommandRegistry()
    command = SlashCommand(
        name="test",
        usage="/test",
        description="Test",
        handler=lambda context: create_default_command_registry().execute(context.session, "/session"),
    )
    registry.register(command)

    try:
        registry.register(command)
    except ValueError as exc:
        assert "Duplicate slash command" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("expected duplicate command to fail")
