"""Command-line entry point for Baldric."""

from __future__ import annotations

import contextlib
import faulthandler
import sys
from collections.abc import Callable
from functools import partial
from os import environ
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
from baldric.runtime.config.paths import BaldricPaths
from baldric.runtime.config.shell_config import load_shell_settings
from baldric.runtime.context.thinking import THINKING_LEVELS, ThinkingLevel, normalize_thinking_level
from baldric.runtime.frontends.print import run_openai_print_mode
from baldric.runtime.frontends.rpc import RpcServer
from baldric.runtime.frontends.session_records import resolve_mode_session_record
from baldric.runtime.frontends.tui import run_tui_app
from baldric.runtime.observability.doctor import render_doctor_report
from baldric.runtime.platform import StderrUiBridge
from baldric.runtime.platform.installer import (
    ExtensionInstallError,
    install_extension,
    read_extension_registry,
    remove_extension,
    update_extension,
)
from baldric.runtime.providers.auth.credentials import FileCredentialStore
from baldric.runtime.providers.config import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER_NAME,
    CredentialReader,
    OpenAICompatibleProviderConfig,
    ProviderConfig,
    ProviderConfigError,
    ProviderSettings,
    load_provider_settings,
    provider_kind,
    resolve_provider_selection,
    resolve_startup_thinking_level,
    save_provider_settings,
    upsert_openai_compatible_provider,
)
from baldric.runtime.providers.loader import user_catalog_path
from baldric.runtime.providers.runtime import create_model_provider
from baldric.runtime.providers.stores.models_dev_store import (
    ModelsDevRefreshError,
    ModelsDevRefreshResult,
    refresh_models_dev_catalog,
)
from baldric.runtime.rendering import PrintOutputMode
from baldric.runtime.session import JsonlSessionStorage
from baldric.runtime.session.export import (
    default_session_export_artifact_path,
    export_session_artifact,
    normalize_export_format,
)
from baldric.runtime.session.manager import CodingSessionRecord, SessionManager, validate_session_id
from baldric.runtime.session.session import (
    CodingSession,
    CodingSessionConfig,
    jsonl_session_storage,
)
from baldric.runtime.trust.policy import TrustOverride
from baldric.runtime.update.check import (
    UpdateNotice,
    cached_update_notice,
    startup_release_notes_notice,
    startup_update_notice,
)
from baldric.runtime.update.updater import update_baldric
from baldric.runtime.version import current_version as _current_version


def _is_utf8_encoding(encoding: str | None) -> bool:
    """Return whether a stream encoding name represents UTF-8."""
    if encoding is None:
        return False
    return encoding.lower().replace("-", "").replace("_", "") == "utf8"


def _force_utf8_streams() -> None:
    """Reconfigure stdout/stderr to UTF-8 when they are not already UTF-8.

    Windows consoles default these streams to the system codepage (e.g.
    cp1252), which raises UnicodeEncodeError on model output containing
    characters outside that codepage.
    """
    for stream in (sys.stdout, sys.stderr):
        if _is_utf8_encoding(getattr(stream, "encoding", None)):
            continue
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]


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


def providers_command() -> None:
    """List configured model providers."""
    render_provider_settings(load_provider_settings(), credential_reader=FileCredentialStore())


def install_command(args: list[str]) -> None:
    """Install an extension into Baldric's user extension directory."""
    source: str | None = None
    force = False
    for arg in args:
        if arg == "--force":
            force = True
        elif arg.startswith("-"):
            raise typer.BadParameter(f"Unknown option for `baldric install`: {arg}")
        elif source is None:
            source = arg
        else:
            raise typer.BadParameter("Usage: baldric install <source> [--force]")
    if source is None:
        raise typer.BadParameter("Usage: baldric install <source> [--force]")

    typer.echo(
        "Warning: extensions execute arbitrary Python with your user permissions. "
        "Only install sources you trust.",
        err=True,
    )
    try:
        destination = install_extension(source, force=force)
    except ExtensionInstallError as exc:
        typer.echo(f"Could not install extension: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Installed {source} to {destination}")


def extensions_command(args: list[str]) -> None:
    """List, update, or remove Baldric-managed extensions."""
    subcommand = args[0] if args else None
    if subcommand == "list" or subcommand is None:
        _extensions_list_command()
        return
    name: str | None = None
    force = False
    for arg in args[1:]:
        if arg == "--force":
            force = True
        elif arg.startswith("-"):
            raise typer.BadParameter(f"Unknown option for `baldric extensions {subcommand}`: {arg}")
        elif name is None:
            name = arg
        else:
            raise typer.BadParameter(f"Usage: baldric extensions {subcommand} <name> [--force]")
    if name is None:
        raise typer.BadParameter(f"Usage: baldric extensions {subcommand} <name> [--force]")
    if subcommand == "update":
        try:
            destination = update_extension(name, force=force)
        except ExtensionInstallError as exc:
            typer.echo(f"Could not update extension: {exc}", err=True)
            raise typer.Exit(1) from exc
        typer.echo(f"Updated {name} at {destination}")
        return
    if subcommand == "remove":
        try:
            destination = remove_extension(name)
        except ExtensionInstallError as exc:
            typer.echo(f"Could not remove extension: {exc}", err=True)
            raise typer.Exit(1) from exc
        typer.echo(f"Removed {name} from {destination}")
        return
    raise typer.BadParameter("Usage: baldric extensions [list] | update <name> [--force] | remove <name>")


def _extensions_list_command() -> None:
    extensions_dir = BaldricPaths().user_extensions_dir
    records = read_extension_registry(extensions_dir)
    installed = sorted(path for path in extensions_dir.glob("*") if path.is_dir() or path.is_file())
    if not installed:
        typer.echo("No extensions installed.")
        return
    for path in installed:
        record = records.get(path.name)
        if record is None:
            typer.echo(f"{path.name}  unmanaged (manual, project, or explicit-path install)")
        elif record.kind == "git":
            ref = f" @ {record.ref}" if record.ref else ""
            commit = f" ({record.commit[:12]})" if record.commit else ""
            typer.echo(f"{path.name}  managed  git {record.source}{ref}{commit}")
        else:
            typer.echo(f"{path.name}  managed  local {record.source}")


def setup_command(
    *,
    provider_name: str = DEFAULT_PROVIDER_NAME,
    base_url: str = DEFAULT_OPENAI_COMPATIBLE_BASE_URL,
    api_key_env: str = "OPENAI_API_KEY",
    model: str = DEFAULT_MODEL,
    timeout_seconds: float = DEFAULT_OPENAI_COMPATIBLE_TIMEOUT_SECONDS,
    max_retries: int = DEFAULT_OPENAI_COMPATIBLE_MAX_RETRIES,
    max_retry_delay_seconds: float = DEFAULT_OPENAI_COMPATIBLE_MAX_RETRY_DELAY_SECONDS,
    set_default: bool = True,
) -> None:
    """Create or update an OpenAI-compatible provider entry."""
    settings = load_provider_settings()
    provider = OpenAICompatibleProviderConfig(
        name=provider_name,
        base_url=base_url.rstrip("/"),
        api_key_env=api_key_env,
        models=(model,),
        default_model=model,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        max_retry_delay_seconds=max_retry_delay_seconds,
    )
    updated = upsert_openai_compatible_provider(settings, provider, set_default=set_default)
    path = save_provider_settings(updated)
    typer.echo(f"Saved provider '{provider.name}' to {user_catalog_path()} and preferences to {path}")
    if provider.api_key_env not in environ:
        typer.echo(f"Set {provider.api_key_env} before running Baldric with this provider.", err=True)


def _cli_preflight(*, doctor: bool) -> None:
    """Start best-effort crash diagnostics, then honor the `--doctor` early exit."""
    # CliRunner and other embedded hosts use fileno-less streams where
    # faulthandler cannot attach; diagnostics stay best-effort there.
    with contextlib.suppress(ValueError, OSError):
        faulthandler.enable()
    if doctor:
        render_doctor_report()
        raise typer.Exit()


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


async def run_openai_tui(
    model: str | None,
    cwd: Path,
    session_id: str | None = None,
    new_session: bool = False,
    provider_name: str | None = None,
    auto_compact_token_threshold: int | None = None,
    initial_prompt: str | None = None,
    update_notice: UpdateNotice | None = None,
    extension_paths: tuple[Path, ...] = (),
    extensions_enabled: bool = True,
    project_extensions_enabled: bool = False,
    custom_system_prompt: str | None = None,
    append_system_prompt: str | None = None,
    trust_override: TrustOverride | None = None,
    *,
    thinking_level_override: ThinkingLevel | None = None,
    show_full_output: bool = False,
) -> str | None:
    """Run the Textual TUI and return its resumable session id, if any."""
    release_notes_notice = startup_release_notes_notice(_current_version())
    startup_notices = (release_notes_notice.message,) if release_notes_notice is not None else ()
    deferred_update_notice = _deferred_startup_update_notice() if update_notice is None else None
    return await run_tui_app(
        model=model,
        cwd=cwd,
        session_id=session_id,
        new_session=new_session,
        provider_name=provider_name,
        auto_compact_token_threshold=auto_compact_token_threshold,
        initial_prompt=initial_prompt,
        startup_update_notice=update_notice.message if update_notice is not None else None,
        deferred_startup_update_notice=deferred_update_notice,
        startup_notices=startup_notices,
        extension_paths=extension_paths,
        extensions_enabled=extensions_enabled,
        project_extensions_enabled=project_extensions_enabled,
        custom_system_prompt=custom_system_prompt,
        append_system_prompt=append_system_prompt,
        trust_override=trust_override,
        thinking_level_override=thinking_level_override,
        show_full_output=show_full_output,
    )


def _startup_update_notice() -> UpdateNotice | None:
    return startup_update_notice(_current_version())


def _cached_startup_update_notice() -> UpdateNotice | None:
    """Return a cached update notice without contacting PyPI."""
    notice, _check_due = cached_update_notice(_current_version())
    return notice


def _deferred_startup_update_notice() -> Callable[[], str | None] | None:
    """Return a blocking PyPI check for the TUI to run when the cache is stale."""
    _notice, check_due = cached_update_notice(_current_version())
    if not check_due:
        return None

    def check() -> str | None:
        notice = _startup_update_notice()
        return notice.message if notice is not None else None

    return check


def update_models_command() -> None:
    """Force-refresh and persist the runtime model catalog."""

    async def refresh() -> ModelsDevRefreshResult:
        return await refresh_models_dev_catalog(force=True)

    try:
        result = anyio.run(refresh)
    except ModelsDevRefreshError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    status = "refreshed" if result.refreshed else "unchanged"
    typer.echo(f"Model catalogs {status}: {result.model_count} models cached at {result.cache_path}")


def update_command() -> None:
    """Upgrade Baldric using the installer that manages the current environment."""
    result = update_baldric()
    if not result.succeeded:
        typer.echo("Could not safely update Baldric:", err=True)
        for failure in result.failures:
            typer.echo(f"- {failure}", err=True)
        raise typer.Exit(1)
    if result.stdout:
        typer.echo(result.stdout)
    if result.stderr:
        typer.echo(result.stderr, err=True)
    if result.deferred:
        typer.echo(f"Baldric update handed off with: {' '.join(result.command or ())}")
    else:
        typer.echo(f"Baldric update completed with: {' '.join(result.command or ())}")


def render_session_list(records: list[CodingSessionRecord]) -> None:
    """Render indexed sessions for the CLI."""
    if not records:
        typer.echo("No sessions found.")
        return

    for record in records:
        title = record.title or "Untitled"
        typer.echo(f"{record.id}\t{title}\t{record.model}\t{record.cwd}")


async def export_session_command(
    session_ref: str,
    output_path: Path | None = None,
    export_format: str | None = None,
    session_manager: SessionManager | None = None,
) -> Path:
    """Export an indexed session id or JSONL file path."""
    session_path, title = _resolve_export_source(session_ref, session_manager)
    entries = await JsonlSessionStorage(session_path).read_all()
    normalized_format = normalize_export_format(
        export_format or (output_path.suffix.removeprefix(".") if output_path else "html")
    )
    destination = _resolve_export_destination(
        output_path,
        session_path=session_path,
        format=normalized_format,
    )
    return export_session_artifact(
        entries,
        destination,
        title=title,
        source=str(session_path),
        format=normalized_format,
    )


def _run_export_cli(args: list[str]) -> None:
    """Run `baldric export`/`baldric --export` and exit."""
    try:
        session_ref, output_path, export_format = _parse_export_cli_args(args)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    try:
        exported_path = anyio.run(
            export_session_command,
            session_ref,
            output_path,
            export_format,
        )
    except (RuntimeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Exported session to {exported_path}")
    raise typer.Exit()


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


def _parse_export_cli_args(args: list[str]) -> tuple[str, Path | None, str | None]:
    if not args:
        raise RuntimeError("Usage: baldric export <session-id-or-jsonl> [--format html|jsonl] [output]")
    session_ref = args[0]
    output_path: Path | None = None
    export_format: str | None = None
    index = 1
    while index < len(args):
        arg = args[index]
        if arg == "--format":
            index += 1
            if index >= len(args):
                raise RuntimeError(
                    "Usage: baldric export <session-id-or-jsonl> [--format html|jsonl] [output]"
                )
            export_format = args[index]
        elif arg.startswith("--format="):
            export_format = arg.partition("=")[2]
        elif arg.startswith("-"):
            raise RuntimeError(f"Unknown export option: {arg}")
        elif output_path is None:
            output_path = Path(arg).expanduser()
        else:
            raise RuntimeError("Usage: baldric export <session-id-or-jsonl> [--format html|jsonl] [output]")
        index += 1
    return session_ref, output_path, export_format


def _resolve_export_destination(
    output_path: Path | None,
    *,
    session_path: Path,
    format: str,
) -> Path:
    if output_path is None:
        return default_session_export_artifact_path(
            session_path,
            destination_dir=Path.cwd(),
            format=format,
        )
    if output_path.suffix:
        return output_path
    return default_session_export_artifact_path(
        session_path,
        destination_dir=output_path,
        format=format,
    )


def _resolve_export_source(
    session_ref: str,
    session_manager: SessionManager | None = None,
) -> tuple[Path, str]:
    candidate_path = Path(session_ref).expanduser()
    if candidate_path.exists():
        if candidate_path.is_dir():
            raise RuntimeError(f"Session export source is a directory: {candidate_path}")
        return candidate_path, f"Baldric session {candidate_path.stem}"

    manager = session_manager or SessionManager()
    record = manager.get_session(session_ref)
    if record is None:
        raise RuntimeError(f"Unknown session or file: {session_ref}")

    title = record.title or f"Baldric session {record.id}"
    return record.path, title


def render_provider_settings(
    settings: ProviderSettings,
    *,
    credential_reader: CredentialReader | None = None,
) -> None:
    """Render configured providers for the CLI."""
    for provider in settings.providers:
        marker = "*" if provider.name == settings.default_provider else " "
        models = ",".join(provider.models)
        typer.echo(
            f"{marker}\t{provider.name}\t{provider_kind(provider)}\t"
            f"{provider.default_model}\t{models}\t{provider.api_key_env}\t"
            f"{_provider_credential_status(provider, credential_reader=credential_reader)}\t"
            f"{provider.base_url}\t{provider.timeout_seconds:g}s\t"
            f"retries={provider.max_retries}\t"
            f"retry_delay={provider.max_retry_delay_seconds:g}s"
        )


def _provider_credential_status(
    provider: ProviderConfig,
    *,
    credential_reader: CredentialReader | None,
) -> str:
    if provider.credential_name and credential_reader is not None:
        if provider_kind(provider) == "openai-codex":
            get_oauth = getattr(credential_reader, "get_oauth", None)
            if get_oauth is not None and get_oauth(provider.credential_name) is not None:
                return f"stored:{provider.credential_name}"
        elif credential_reader.get(provider.credential_name):
            return f"stored:{provider.credential_name}"
    if environ.get(provider.api_key_env):
        return f"env:{provider.api_key_env}"
    return "missing"


async def run_openai_rpc_mode(
    model: str | None,
    cwd: Path,
    provider_name: str | None = None,
    resume_session_id: str | None = None,
    extension_paths: tuple[Path, ...] = (),
    extensions_enabled: bool = True,
    project_extensions_enabled: bool = False,
    custom_system_prompt: str | None = None,
    append_system_prompt: str | None = None,
    trust_override: TrustOverride | None = None,
    *,
    thinking_level_override: ThinkingLevel | None = None,
) -> None:
    """Run a persistent Pi-compatible JSONL RPC session."""
    settings = load_provider_settings()
    shell_settings = load_shell_settings()
    manager = SessionManager()
    record = resolve_mode_session_record(
        manager,
        resume_session_id=resume_session_id,
        cwd=cwd,
        settings=settings,
        provider_name=provider_name,
        model=model,
        session_id=None,
    )
    explicit_selection = provider_name is not None or model is not None
    selected_provider = provider_name if explicit_selection else record.provider_name
    selected_model = model if explicit_selection else record.model
    try:
        selection = resolve_provider_selection(
            settings, provider_name=selected_provider, model=selected_model
        )
    except ProviderConfigError:
        if (selected_provider or settings.default_provider) != "openai-codex":
            raise
        # Bootstrap with the static default; the staged loader discovers and
        # validates the requested/resumed live-only model before activating it.
        selection = resolve_provider_selection(settings, provider_name="openai-codex")
    inference_provider = (
        record.inference_provider
        if resume_session_id is not None
        and record.provider_name == "huggingface"
        and selection.provider.name == "huggingface"
        and record.model == selection.model
        else selection.provider.inference_providers.get(selection.model)
        or selection.provider.default_inference_provider
        if isinstance(selection.provider, OpenAICompatibleProviderConfig)
        and selection.provider.name == "huggingface"
        else None
    )
    inference_provider_mode = (
        record.inference_provider_mode
        if resume_session_id is not None
        and record.provider_name == "huggingface"
        and selection.provider.name == "huggingface"
        and record.model == selection.model
        else "fixed"
        if inference_provider is not None
        else "automatic"
    )
    provider = create_model_provider(
        selection.provider,
        model=selection.model,
        inference_provider=inference_provider,
        thinking_level=resolve_startup_thinking_level(
            selection.provider,
            selection.model,
            cli_override=thinking_level_override,
        ),
    )
    session = await CodingSession.load(
        CodingSessionConfig(
            provider=provider,
            model=selected_model or selection.model,
            requested_provider=selected_provider if explicit_selection else None,
            requested_model=selected_model if explicit_selection else None,
            session_provider_name=record.provider_name,
            thinking_level_override=thinking_level_override,
            cwd=record.cwd,
            storage=jsonl_session_storage(record.path),
            session_id=record.id,
            session_manager=manager,
            provider_name=selection.provider.name,
            inference_provider=inference_provider,
            inference_provider_mode=inference_provider_mode,
            provider_settings=settings,
            runtime_provider_config=selection.provider,
            shell_command_prefix=shell_settings.shell_command_prefix,
            shell=shell_settings.shell,
            extension_paths=extension_paths,
            extensions_enabled=extensions_enabled,
            project_extensions_enabled=project_extensions_enabled,
            custom_system_prompt=custom_system_prompt,
            append_system_prompt=append_system_prompt,
            trust_override=trust_override,
            trust_default=shell_settings.default_project_trust,
        )
    )
    session.extension_runtime.set_ui_bridge(StderrUiBridge())
    try:
        await RpcServer(session).run()
    finally:
        await provider.aclose()
