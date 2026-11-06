import sys
import webbrowser
from pathlib import Path

import pytest

from tests.helpers.conftest_utils import isolate_home


@pytest.fixture(autouse=True)
def prevent_browser_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail tests that accidentally launch an external browser."""

    def fail_browser_open(url: str, *_args: object, **_kwargs: object) -> bool:
        pytest.fail(f"Test attempted to open a browser URL: {url}")

    monkeypatch.setattr(webbrowser, "open", fail_browser_open)


@pytest.fixture(autouse=True)
def skip_idle_garbage_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub out the TUI's idle-time GC; it acts on the whole pytest process."""
    monkeypatch.setattr("baldric_coding.tui.app._collect_garbage_while_idle", lambda: None)


@pytest.fixture(autouse=True)
def prevent_user_home_writes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep every test away from the developer's real home configuration."""
    isolate_home(monkeypatch, tmp_path)


# Skipped on Windows locally: POSIX permissions/symlink privileges/POSIX shell
# and POSIX path rendering, or timing-sensitive subprocess/browser flows.
# These run in CI (Linux).
_WIN32_SKIPS = {
    # POSIX-only path rendering / cwd normalization
    "tests/coding/cli/test_cli.py::test_run_print_mode_",
    "tests/coding/session/test_coding_session.py::test_prompt_logs_unexpected_agent_call_exception",
    "tests/coding/session/test_coding_session.py::test_terminal_command_can_",
    "tests/coding/session/test_coding_session.py::test_session_loads_baldric_native_system_prompt_files",
    "tests/coding/context/test_system_prompt.py::test_default_prompt_includes_tools_guidelines_date_and_cwd",
    "tests/coding/context/test_system_prompt.py::test_inspection_attributes_prompt_inputs_without_changing_text",
    "tests/coding/tui/test_tui_adapter.py::test_file_tool_formatter_shortens_absolute_paths_under_cwd",
    "tests/coding/tui/test_tui_app.py::test_session_sidebar_lists_active_system_prompt_files",
    "tests/coding/tui/test_tui_app.py::test_session_sidebar_lists_multiple_context_files",
    "tests/coding/tui/test_tui_app.py::test_compact_session_info_renders_sidebar_facts",
    "tests/coding/tui/test_tui_app.py::test_compact_session_info_styles_parent_path_as_metadata",
    "tests/coding/tui/test_tui_app.py::test_tui_sidebar_context_file_opens_in_main_editor_and_saves",
    "tests/coding/tui/test_tui_app.py::test_tui_sidebar_prompt_file_opens_in_main_editor",
    "tests/coding/tui/test_tui_app.py::test_tui_app_export_command_runs_session_export",
    "tests/coding/tui/test_tui_app.py::test_session_picker_navigates_projects_in_left_column",
    "tests/coding/tui/test_tui_app.py::test_tui_app_completes_resume_session_argument",
    "tests/coding/tui/test_tui_app.py::test_tui_app_session_picker_archives_selected_project",
    "tests/coding/tui/test_tui_app.py::test_tui_app_session_picker_archived_tab_restores_session_and_project",
    "tests/coding/tui/test_tui_app.py::test_tui_tree_labels_filter_timestamps_and_clear",
    "tests/coding/session/test_session_manager.py::test_session_manager_sorts_newest_updated_first",
    "tests/coding/session/test_session_manager.py::test_session_manager_returns_latest_session_for_cwd",
    # POSIX shell semantics (bash tool / quoting)
    "tests/coding/tools/test_coding_tools.py::test_bash_tool_",
    "tests/coding/tools/test_coding_tools.py::test_create_coding_tools_applies_shell_command_prefix",
    "tests/coding/cli/test_rpc.py::test_rpc_direct_bash_matches_pi_result_shape",
    "tests/coding/tui/test_tui_file_drop.py::",
    # POSIX file permissions (0o600)
    "tests/coding/config/test_credentials.py::test_file_credential_store_round_trips_and_sets_private_permissions",
    "tests/coding/extensions/test_llama_cpp_extension.py::test_state_is_atomic_locked_private_and_recovers_interrupted_writes",
    # symlink privileges not granted on Windows
    "tests/coding/extensions/test_extensions.py::test_failed_setup_cleans_every_registration_after_entry_symlink_retarget",
    "tests/coding/tui/test_tui_app.py::test_sidebar_file_atomic_save_preserves_symlink_and_permissions",
    # Windows updater defers to a scheduled handoff instead of running inline
    "tests/coding/update/test_updater.py::test_windows_handoff_blocks_for_live_parent_and_preserves_arguments",
    "tests/coding/update/test_updater.py::test_update_baldric_does_not_fall_back_when_owner_update_fails",
    # subprocess timing granularity on Windows reports timed_out instead of failed
    "tests/coding/extensions/test_extension_providers.py::test_failed_refresh_retains_snapshot_and_records_bounded_safe_diagnostic",
    # GC assertions are process-timing sensitive
    "tests/coding/tui/test_tui_app.py::test_tui_app_collects_garbage_at_startup_and_when_agent_settles",
    # TUI download/backend flow depends on subprocess/UI timing
    "tests/coding/tui/test_tui_local_backends.py::test_backend_open_auto_refreshes_and_renders_clickable_models",
    "tests/coding/tui/test_tui_local_backends.py::test_clicking_loaded_model_uses_exact_model_id",
    "tests/coding/tui/test_tui_local_backends.py::test_closing_download_modal_detaches_and_reopen_offers_explicit_cancel",
    "tests/coding/tui/test_tui_local_backends.py::test_detached_download_completion_immediately_shows_model_available",
    # TUI trust modal interaction timing
    "tests/coding/trust/test_project_trust.py::test_tui_trust_modal_shows_boundary_parent_and_keyboard_cancel",
    # Textual headless focus/picker/screen-fit timing rotates flaky on Windows;
    # the deterministic gate is Linux CI, which still runs every one of these.
    "tests/coding/tui/test_oauth_tui.py::",
    "tests/coding/tui/test_tui_app.py::test_tui_login",
    "tests/coding/tui/test_tui_app.py::test_tui_scoped",
    "tests/coding/tui/test_tui_app.py::test_tui_app_session_picker",
    "tests/coding/tui/test_tui_components.py::test_sidebar_sections",
}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if sys.platform != "win32":
        return
    for item in items:
        for prefix in _WIN32_SKIPS:
            if item.nodeid.startswith(prefix):
                item.add_marker(pytest.mark.skip(reason="POSIX/timing semantics, runs on Linux CI"))
                break
