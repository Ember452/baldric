"""Tests for the ``baldric --doctor`` capability report."""

import io

import pytest
from rich.console import Console

from baldric_coding.observability import doctor


def _render_report(env: dict[str, str]) -> str:
    console = Console(record=True, width=140, force_terminal=False, color_system=None)
    console.print(doctor.build_doctor_report(env))
    return console.export_text()


def test_doctor_report_lists_core_capability_rows() -> None:
    env = {"WT_SESSION": "abc", "COLORTERM": "truecolor", "TERM": "xterm-256color"}

    report = _render_report(env)

    for label in (
        "baldric",
        "python",
        "platform",
        "terminal",
        "truecolor",
        "mouse",
        "OSC 9;4 progress",
        "OSC 9/99 notify",
        "CJK width",
        "git",
        "textual",
        "rich",
        "session storage",
    ):
        assert label in report, label
    assert "Windows Terminal" in report
    assert "yes" in report
    assert "double-width detected" in report


def test_doctor_report_reports_missing_git(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)

    report = _render_report({})

    assert "not found" in report


def test_render_doctor_report_prints_to_the_console() -> None:
    console = Console(file=io.StringIO(), width=120)

    doctor.render_doctor_report(console)

    assert "baldric --doctor" in console.file.getvalue()
