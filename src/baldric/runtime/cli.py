"""Command-line entry point for Baldric."""

from __future__ import annotations

import sys
from functools import partial
from pathlib import Path
from typing import Annotated

import anyio
import typer

from baldric.ai.env import (
    DEFAULT_OPENAI_COMPATIBLE_BASE_URL,
    DEFAULT_OPENAI_COMPATIBLE_MAX_RETRIES,
    DEFAULT_OPENAI_COMPATIBLE_MAX_RETRY_DELAY_SECONDS,
    DEFAULT_OPENAI_COMPATIBLE_TIMEOUT_SECONDS,
)
from baldric.runtime.cli_commands.export import _run_export_cli
from baldric.runtime.cli_commands.extensions import extensions_command
from baldric.runtime.cli_commands.install import install_command
from baldric.runtime.cli_commands.providers import providers_command
from baldric.runtime.cli_commands.sessions import render_session_list
from baldric.runtime.cli_commands.setup import _cli_preflight, setup_command
from baldric.runtime.cli_commands.update import update_command, update_models_command
from baldric.runtime.cli_io import _force_utf8_streams
from baldric.runtime.config.paths import BaldricPaths
from baldric.runtime.context.thinking import THINKING_LEVELS, ThinkingLevel, normalize_thinking_level
from baldric.runtime.frontends.print import run_openai_print_mode
from baldric.runtime.frontends.rpc import run_openai_rpc_mode
from baldric.runtime.frontends.tui import run_openai_tui
from baldric.runtime.providers.config import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER_NAME,
)
from baldric.runtime.rendering import PrintOutputMode
from baldric.runtime.session.manager import SessionManager, validate_session_id
from baldric.runtime.trust.policy import TrustOverride
from baldric.runtime.update.check import (
    UpdateNotice,
    cached_update_notice,
    startup_update_notice,
)
from baldric.runtime.version import current_version as _current_version

_force_utf8_streams()

app = typer.Typer(
    name="baldric",
    help="Baldric coding-agent harness.",
    epilog="""Commands:

  baldric install SOURCE [--force] - Install a trusted local or Git extension.

  baldric extensions [list] - Show managed and unmanaged extensions.

  baldric extensions update <name> [--force] - Refresh a managed Git extension.

  baldric extensions remove <name> - Remove a managed extension.

  baldric update - Upgrade Baldric.

  baldric sessions - List indexed sessions.

  baldric export REF [DEST] - Export a session as HTML or JSONL.

  baldric providers - List configured model providers.

  baldric setup - Configure an OpenAI-compatible provider.
""",
    add_completion=False,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    prompt_args: Annotated[
        list[str] | None,
        typer.Argument(help="Initial prompt to run in interactive TUI mode."),
    ] = None,
    print_mode: Annotated[
        bool,
        typer.Option(
            "--print",
            "-p",
            help="Run the positional prompt in non-interactive print mode.",
        ),
    ] = False,
    prompt_option: Annotated[
        str | None,
        typer.Option(
            "--prompt",
            help="Removed; pass the prompt positionally and use --print instead.",
            hidden=True,
        ),
    ] = None,
    provider: Annotated[
        str | None,
        typer.Option("--provider", help="Configured provider name to use."),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Model name to request from the provider."),
    ] = None,
    thinking: Annotated[
        str | None,
        typer.Option(
            "--thinking",
            "-t",
            help=(
                "Initial thinking level for this run "
                f"({', '.join(THINKING_LEVELS)}). "
                "Overrides remembered defaults without persisting."
            ),
        ),
    ] = None,
    setup_base_url: Annotated[
        str,
        typer.Option("--base-url", help="OpenAI-compatible base URL for `baldric setup`."),
    ] = DEFAULT_OPENAI_COMPATIBLE_BASE_URL,
    setup_api_key_env: Annotated[
        str,
        typer.Option("--api-key-env", help="API key environment variable for `baldric setup`."),
    ] = "OPENAI_API_KEY",
    setup_timeout_seconds: Annotated[
        float,
        typer.Option(
            "--timeout-seconds",
            help="HTTP timeout in seconds for `baldric setup` provider requests.",
        ),
    ] = DEFAULT_OPENAI_COMPATIBLE_TIMEOUT_SECONDS,
    setup_max_retries: Annotated[
        int,
        typer.Option("--max-retries", help="Provider retry count for `baldric setup`."),
    ] = DEFAULT_OPENAI_COMPATIBLE_MAX_RETRIES,
    setup_max_retry_delay_seconds: Annotated[
        float,
        typer.Option(
            "--max-retry-delay-seconds",
            help="Provider retry delay in seconds for `baldric setup`.",
        ),
    ] = DEFAULT_OPENAI_COMPATIBLE_MAX_RETRY_DELAY_SECONDS,
    setup_default: Annotated[
        bool,
        typer.Option("--set-default/--no-set-default", help="Make setup provider the default."),
    ] = True,
    cwd: Annotated[
        Path | None,
        typer.Option("--cwd", help="Working directory for built-in coding tools."),
    ] = None,
    mode: Annotated[
        PrintOutputMode | None,
        typer.Option(
            "--mode",
            help="Run headlessly with this output format (text, json, transcript, or rpc).",
        ),
    ] = None,
    output: Annotated[
        PrintOutputMode | None,
        typer.Option(
            "--output",
            "-o",
            help="Removed; use --mode instead.",
            hidden=True,
        ),
    ] = None,
    show_full_output: Annotated[
        bool,
        typer.Option(
            "--show-full-output",
            help=(
                "Start the TUI with untruncated tool and terminal-command output "
                "instead of previews. Also available in-session via the "
                "tool-results toggle."
            ),
        ),
    ] = False,
    session: Annotated[
        str | None,
        typer.Option("--session", help="Resume a session id in TUI or print mode."),
    ] = None,
    resume: Annotated[
        str | None,
        typer.Option(
            "--resume",
            help="Removed; use --session <session-id> instead.",
            hidden=True,
        ),
    ] = None,
    new_session: Annotated[
        bool,
        typer.Option("--new-session", help="Create a new session in TUI mode (default)."),
    ] = False,
    session_id: Annotated[
        str | None,
        typer.Option(
            "--session-id",
            help="Set the exact id for the newly created print-mode session.",
        ),
    ] = None,
    system_prompt: Annotated[
        str | None,
        typer.Option(
            "--system-prompt",
            metavar="TEXT_OR_PATH",
            help="Replace the default system-prompt base with literal text or a UTF-8 file.",
        ),
    ] = None,
    append_system_prompt: Annotated[
        list[str] | None,
        typer.Option(
            "--append-system-prompt",
            metavar="TEXT_OR_PATH",
            help="Append literal text or a UTF-8 file to the system prompt (repeatable).",
        ),
    ] = None,
    auto_compact_threshold: Annotated[
        int | None,
        typer.Option(
            "--auto-compact-threshold",
            help="Automatically compact TUI context above this rough token estimate.",
        ),
    ] = None,
    extension: Annotated[
        list[Path] | None,
        typer.Option(
            "--extension",
            "-e",
            help="Load an extension file or directory (repeatable).",
        ),
    ] = None,
    extension_legacy: Annotated[
        list[Path] | None,
        typer.Option(
            "-x",
            help="Removed; use -e/--extension instead.",
            hidden=True,
        ),
    ] = None,
    export: Annotated[
        bool,
        typer.Option(
            "--export",
            help="Export the given session id or JSONL path (mirrors `baldric export`).",
        ),
    ] = False,
    no_extensions: Annotated[
        bool,
        typer.Option(
            "--no-extensions",
            help="Disable extension directory discovery (explicit -e paths still load).",
        ),
    ] = False,
    project_extensions: Annotated[
        bool,
        typer.Option(
            "--project-extensions",
            help="Also load trusted project .baldric/extensions (additional code opt-in).",
        ),
    ] = False,
    approve: Annotated[
        bool,
        typer.Option("--approve", "-a", help="Trust protected project inputs for this run."),
    ] = False,
    no_approve: Annotated[
        bool,
        typer.Option("--no-approve", "-na", help="Decline protected project inputs for this run."),
    ] = False,
    version: Annotated[
        bool,
        typer.Option("--version", "-v", help="Show Baldric's version and exit."),
    ] = False,
    models: Annotated[
        bool,
        typer.Option("--models", help="With `baldric update`, refresh model catalogs only."),
    ] = False,
    doctor: Annotated[
        bool,
        typer.Option("--doctor", help="Print a terminal capability report and exit."),
    ] = False,
) -> None:
    """Run the Baldric CLI."""
    _cli_preflight(doctor=doctor)
    current_version = _current_version()
    if version:
        typer.echo(f"baldric {current_version}")
        raise typer.Exit()

    try:
        BaldricPaths()
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="BALDRIC_HOME") from exc

    if ctx.invoked_subcommand is not None:
        return

    if approve and no_approve:
        raise typer.BadParameter("--approve and --no-approve cannot be used together")
    trust_override: TrustOverride | None = "approve" if approve else "decline" if no_approve else None

    if resume is not None:
        raise typer.BadParameter(
            f"--resume was renamed to --session. Use `baldric --session {resume}` instead."
        )

    if session is not None and new_session:
        raise typer.BadParameter("--session and --new-session cannot be used together")
    if session is not None and session_id is not None:
        raise typer.BadParameter("--session and --session-id cannot be used together")

    if prompt_option is not None:
        raise typer.BadParameter(
            "--prompt was removed. Pass the prompt positionally and use --print, e.g. "
            f'`baldric --print "{prompt_option}"`.'
        )

    if output is not None:
        raise typer.BadParameter(
            f"--output was renamed to --mode. Use `baldric --mode {output.value}` instead."
        )

    if extension_legacy is not None:
        raise typer.BadParameter("-x was renamed to -e/--extension.")

    thinking_level_override: ThinkingLevel | None = None
    if thinking is not None:
        try:
            thinking_level_override = normalize_thinking_level(thinking)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc

    rpc_requested = mode is PrintOutputMode.rpc
    print_requested = print_mode or (mode is not None and not rpc_requested)
    effective_output = mode or PrintOutputMode.text

    if session_id is not None:
        if not print_requested:
            raise typer.BadParameter("--session-id is only supported in print mode")
        try:
            validate_session_id(session_id)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc

    positional_args = prompt_args or []
    command = positional_args[0] if positional_args else None
    initial_prompt = " ".join(positional_args) if positional_args else None

    if rpc_requested and export:
        raise typer.BadParameter("--export cannot be combined with --mode rpc")

    if not rpc_requested and not print_requested and not export and command == "update":
        positional_models = positional_args[1:] == ["--models"]
        if len(positional_args) != 1 and not positional_models:
            raise typer.BadParameter("Usage: baldric update [--models]")
        if models or positional_models:
            update_models_command()
        else:
            update_command()
        raise typer.Exit()

    if models:
        raise typer.BadParameter("--models is only supported with `baldric update`")

    if not rpc_requested and not print_requested and not export and command == "install":
        install_command(positional_args[1:])
        raise typer.Exit()

    if not rpc_requested and not print_requested and not export and command == "extensions":
        extensions_command(positional_args[1:])
        raise typer.Exit()

    if (
        not rpc_requested
        and not print_requested
        and not export
        and command == "sessions"
        and len(positional_args) == 1
    ):
        render_session_list(SessionManager().list_sessions())
        raise typer.Exit()

    if not rpc_requested and not print_requested and not export and command == "export":
        _run_export_cli(positional_args[1:])

    if export and not rpc_requested:
        if print_requested:
            raise typer.BadParameter("--export cannot be combined with --print/--mode.")
        _run_export_cli(positional_args)

    if not rpc_requested and not print_requested and command == "providers" and len(positional_args) == 1:
        providers_command()
        raise typer.Exit()

    if not rpc_requested and not print_requested and command == "setup" and len(positional_args) == 1:
        setup_command(
            provider_name=provider or DEFAULT_PROVIDER_NAME,
            base_url=setup_base_url,
            api_key_env=setup_api_key_env,
            model=model or DEFAULT_MODEL,
            timeout_seconds=setup_timeout_seconds,
            max_retries=setup_max_retries,
            max_retry_delay_seconds=setup_max_retry_delay_seconds,
            set_default=setup_default,
        )
        raise typer.Exit()

    extension_paths = tuple(extension or ())
    custom_system_prompt = (
        _resolve_prompt_input(system_prompt, option="--system-prompt") if system_prompt is not None else None
    )
    resolved_append_system_prompt = _resolve_append_system_prompts(append_system_prompt or ())

    if rpc_requested:
        if initial_prompt is not None:
            raise typer.BadParameter("RPC mode reads commands from stdin and does not accept a prompt")
        try:
            anyio.run(
                partial(
                    run_openai_rpc_mode,
                    thinking_level_override=thinking_level_override,
                )
                if thinking_level_override is not None
                else run_openai_rpc_mode,
                model,
                cwd or Path.cwd(),
                provider,
                session,
                extension_paths,
                not no_extensions,
                project_extensions,
                custom_system_prompt,
                resolved_append_system_prompt,
                trust_override,
            )
        except (RuntimeError, ValueError) as exc:
            raise typer.BadParameter(str(exc)) from exc
        raise typer.Exit()

    if not print_requested:
        # A due PyPI check runs in the background once the TUI is up.
        notice = _cached_startup_update_notice()
        try:
            tui_args = (
                model,
                cwd or Path.cwd(),
                session,
                new_session,
                provider,
                auto_compact_threshold,
                initial_prompt,
                notice,
                extension_paths,
                not no_extensions,
                project_extensions,
                custom_system_prompt,
                resolved_append_system_prompt,
            )
            tui_runner = (
                partial(
                    run_openai_tui,
                    thinking_level_override=thinking_level_override,
                    show_full_output=show_full_output,
                )
                if thinking_level_override is not None
                else partial(run_openai_tui, show_full_output=show_full_output)
            )
            resumable_session_id = (
                anyio.run(tui_runner, *tui_args)
                if trust_override is None
                else anyio.run(tui_runner, *tui_args, trust_override)
            )
        except (RuntimeError, ValueError) as exc:
            raise typer.BadParameter(str(exc)) from exc
        if resumable_session_id is not None:
            typer.echo(f"To resume this session: baldric --session {resumable_session_id}")
        raise typer.Exit()

    prompt = _merge_stdin_prompt(initial_prompt or "")
    if not prompt:
        raise typer.BadParameter(
            'Usage: baldric --print "<prompt>" (or --mode text|json|transcript "<prompt>"); '
            "a prompt can also be piped in via stdin"
        )

    notice = _startup_update_notice()
    if notice is not None and effective_output is PrintOutputMode.text:
        typer.echo(notice.message, err=True)

    try:
        print_args = (
            prompt,
            model,
            cwd or Path.cwd(),
            effective_output,
            provider,
            None,
            extension_paths,
            not no_extensions,
            project_extensions,
            session_id,
            custom_system_prompt,
            resolved_append_system_prompt,
        )
        print_runner = (
            partial(run_openai_print_mode, thinking_level_override=thinking_level_override)
            if thinking_level_override is not None
            else run_openai_print_mode
        )
        if session is not None:
            ok = anyio.run(print_runner, *print_args, trust_override, session)
        else:
            ok = (
                anyio.run(print_runner, *print_args)
                if trust_override is None
                else anyio.run(print_runner, *print_args, trust_override)
            )
    except (RuntimeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    if not ok:
        raise typer.Exit(1)


def _startup_update_notice() -> UpdateNotice | None:
    return startup_update_notice(_current_version())


def _cached_startup_update_notice() -> UpdateNotice | None:
    """Return a cached update notice without contacting PyPI."""
    notice, _check_due = cached_update_notice(_current_version())
    return notice


def _resolve_prompt_input(value: str, *, option: str) -> str:
    """Resolve an existing UTF-8 file, otherwise preserve literal prompt text."""
    try:
        path = Path(value).expanduser()
    except RuntimeError:
        return value
    try:
        exists = path.exists()
    except OSError as exc:
        raise typer.BadParameter(
            f"Could not inspect {option} path {path}: {exc}",
            param_hint=option,
        ) from exc
    if not exists:
        return value
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise typer.BadParameter(
            f"Could not read {option} file {path}: {exc}",
            param_hint=option,
        ) from exc


def _resolve_append_system_prompts(values: tuple[str, ...] | list[str]) -> str | None:
    """Resolve repeated append inputs in order and separate them by one blank line."""
    if not values:
        return None
    return "\n\n".join(_resolve_prompt_input(value, option="--append-system-prompt") for value in values)


def _merge_stdin_prompt(prompt: str) -> str:
    """Merge piped stdin content into a print-mode prompt, mirroring Pi.

    When stdin is not a terminal (e.g. `cat file | baldric -p "..."`), its
    contents are prepended to the prompt text.
    """
    stdin = sys.stdin
    if stdin is None:
        return prompt
    try:
        if stdin.isatty():
            return prompt
    except (AttributeError, ValueError):
        return prompt
    try:
        piped = stdin.read()
    except (OSError, ValueError):
        return prompt
    if not piped:
        return prompt
    if not prompt:
        return piped
    return f"{piped}\n\n{prompt}"


__all__: list[str] = ["app", "main"]
