"""Bash tool implementation."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from pathlib import Path
from time import monotonic
from typing import Any

from baldric_coding.tools.base import (
    DEFAULT_MAX_OUTPUT_BYTES,
    DEFAULT_MAX_OUTPUT_LINES,
    ToolDefinition,
    ToolInputError,
    _optional_float_arg,
    _str_arg,
)
from baldric_coding.tools.output_accumulator import _write_temp_output, append_status_block, format_size
from baldric_coding.tools.shell import kill_process_tree, resolve_shell
from baldric_coding.tools.truncate import truncate_tail
from baldric_protocol.messages import TextContent
from baldric_protocol.tools import AgentTool, AgentToolResult, ToolCancellationToken
from baldric_protocol.types import JSONValue


def create_bash_tool_definition(
    *,
    cwd: str | Path | None = None,
    shell_command_prefix: str | None = None,
    shell: str = "auto",
) -> ToolDefinition:
    """Create a definition for the `bash` tool.

    The tool runs a shell command with `cwd` as the subprocess working
    directory, disconnects stdin, and combines stdout and stderr into one UTF-8
    decoded output stream. Disconnecting stdin keeps interactive programs from
    competing with Baldric for terminal input. The shell is resolved once per
    tool instance: bash/sh on POSIX, and PowerShell (pwsh, then Windows
    PowerShell) or cmd.exe on Windows. The tool description names the resolved
    shell so the model writes the right syntax. The optional `timeout` argument
    must be positive when supplied. On timeout or cancellation the whole process
    tree is terminated (process group on POSIX, `taskkill /T` on Windows), so
    shell children from pipelines or compound commands do not continue running.

    Output is tail-truncated to `DEFAULT_MAX_OUTPUT_LINES` lines or
    `DEFAULT_MAX_OUTPUT_BYTES` bytes. When truncation occurs, the full output is
    written to a temporary log file and that path is reported in `data`.
    Successful and failed command results both include exit code, timeout state,
    duration, truncation metadata, and full-output path metadata.
    """
    root = Path.cwd() if cwd is None else Path(cwd)
    prefix = shell_command_prefix.strip() if shell_command_prefix else None
    shell_spec = resolve_shell(shell)

    async def execute(
        arguments: Mapping[str, JSONValue],
        signal: ToolCancellationToken | None = None,
    ) -> AgentToolResult:
        command = _str_arg(arguments, "command")
        shell_command = _prefixed_shell_command(command, prefix)
        timeout = _optional_float_arg(arguments, "timeout")
        if timeout is not None and timeout <= 0:
            raise ToolInputError("timeout must be greater than 0")
        if signal is not None and signal.is_cancelled():
            raise ToolInputError("Command cancelled")

        start = monotonic()
        process = await asyncio.create_subprocess_exec(
            *shell_spec.command_line(shell_command),
            cwd=root,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            # Ignored on Windows; the process tree is terminated through taskkill.
            start_new_session=os.name == "posix",
        )
        output_bytes, _stderr, timed_out, cancelled = await _communicate_with_cancellation(
            process,
            timeout=timeout,
            signal=signal,
        )

        output = output_bytes.decode(errors="replace")
        truncation = truncate_tail(output)
        full_output_path: str | None = None
        output_text = truncation.content or "(no output)"
        if truncation.truncated:
            full_output_path = _write_temp_output(output)
            start_line = truncation.total_lines - truncation.output_lines + 1
            end_line = truncation.total_lines
            if truncation.last_line_partial:
                output_text += (
                    f"\n\n[Showing last {format_size(truncation.output_bytes)} of line {end_line}. "
                    f"Full output: {full_output_path}]"
                )
            elif truncation.truncated_by == "lines":
                output_text += (
                    f"\n\n[Showing lines {start_line}-{end_line} of {truncation.total_lines}. "
                    f"Full output: {full_output_path}]"
                )
            else:
                output_text += (
                    f"\n\n[Showing lines {start_line}-{end_line} of {truncation.total_lines} "
                    f"({format_size(DEFAULT_MAX_OUTPUT_BYTES)} limit). "
                    f"Full output: {full_output_path}]"
                )

        exit_code = process.returncode
        status: str | None = None
        if timed_out:
            status = f"Command timed out after {timeout:g} seconds" if timeout else "Command timed out"
        elif cancelled:
            status = "Command cancelled"
        elif exit_code not in (0, None):
            status = f"Command exited with code {exit_code}"
        if status:
            output_text = append_status_block(output_text, status)

        return AgentToolResult(
            content=[TextContent(text=output_text)],
            details={
                "command": command,
                "exit_code": exit_code,
                "timed_out": timed_out,
                "cancelled": cancelled,
                "duration_seconds": round(monotonic() - start, 3),
                "truncation": truncation.to_json(),
                "full_output_path": full_output_path,
                "shell": shell_spec.name,
                "shell_command_prefix_applied": prefix is not None,
            },
        )

    return ToolDefinition(
        name="bash",
        description=(
            f"Execute a command with {shell_spec.label} in the current working directory. "
            "Returns stdout and stderr. "
            f"Output is truncated to last {DEFAULT_MAX_OUTPUT_LINES} lines or "
            f"{DEFAULT_MAX_OUTPUT_BYTES // 1024}KB (whichever is hit first). If truncated, "
            "full output is saved to a temp file. Optionally provide a timeout in seconds."
        ),
        prompt_snippet=f"Execute {shell_spec.label} commands",
        prompt_guidelines=(
            "When using bash, include a brief present-participle description of the "
            "command's purpose (for example, 'Running tests').",
        ),
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": f"Command to execute with {shell_spec.label}"},
                "description": {
                    "type": "string",
                    "description": (
                        "Brief present-participle summary of the command's purpose, such as "
                        "'Running tests' or 'Validating and committing changes'"
                    ),
                },
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds (optional, no default timeout)",
                },
            },
            # `description` only labels the call, so a call without it still runs.
            "required": ["command"],
        },
        executor=execute,
    )


def create_bash_tool(
    *,
    cwd: str | Path | None = None,
    shell_command_prefix: str | None = None,
    shell: str = "auto",
) -> AgentTool:
    """Create an `AgentTool` for executing shell commands with captured output."""
    return create_bash_tool_definition(
        cwd=cwd,
        shell_command_prefix=shell_command_prefix,
        shell=shell,
    ).to_agent_tool()


def _prefixed_shell_command(command: str, prefix: str | None) -> str:
    """Return a shell command with an opt-in setup prefix applied."""
    if prefix is None:
        return command
    return f"{prefix}\n{command}"


async def _communicate_with_cancellation(
    process: asyncio.subprocess.Process,
    *,
    timeout: float | None,
    signal: ToolCancellationToken | None,
) -> tuple[bytes, bytes | None, bool, bool]:
    communicate = asyncio.create_task(process.communicate())
    cancel_watch: asyncio.Task[None] | None = None
    try:
        wait_for: set[asyncio.Task[Any]] = {communicate}
        if signal is not None:
            cancel_watch = asyncio.create_task(_wait_for_cancel(signal))
            wait_for.add(cancel_watch)

        done, _pending = await asyncio.wait(
            wait_for,
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if communicate in done:
            output_bytes, stderr = communicate.result()
            return output_bytes, stderr, False, False

        cancelled = cancel_watch is not None and cancel_watch in done
        _kill_process_tree(process)
        try:
            output_bytes, stderr = await communicate
        except asyncio.CancelledError:
            output_bytes = b""
            stderr_result: bytes | None = None
        else:
            stderr_result = stderr
        return output_bytes, stderr_result, not cancelled, cancelled
    except asyncio.CancelledError:
        _kill_process_tree(process)
        if not communicate.done():
            communicate.cancel()
        raise
    finally:
        if cancel_watch is not None:
            cancel_watch.cancel()


async def _wait_for_cancel(signal: ToolCancellationToken) -> None:
    while not signal.is_cancelled():
        await asyncio.sleep(0.05)


def _kill_process_tree(process: asyncio.subprocess.Process) -> None:
    kill_process_tree(process.pid)
