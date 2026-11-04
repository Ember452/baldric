"""Tests for the vendored five-field cron matcher used by scheduled subagents.

Covers every contract the upstream matcher documents, plus the branches its own
suite left unexercised (the `N/M` step form, an expression that can never match,
and the error types behind `validate_cron`).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from baldric_coding.extensions.builtins.subagents.cron import (
    CronExpression,
    validate_cron,
)


def test_star_matches_every_minute() -> None:
    expression = CronExpression("* * * * *")

    assert expression.matches(datetime(2026, 7, 4, 13, 37))
    assert expression.matches(datetime(2026, 1, 1, 0, 0))


def test_specific_minute_and_hour() -> None:
    expression = CronExpression("30 14 * * *")

    assert expression.matches(datetime(2026, 7, 4, 14, 30))
    assert not expression.matches(datetime(2026, 7, 4, 14, 31))
    assert not expression.matches(datetime(2026, 7, 4, 15, 30))


def test_step_range_and_list_forms() -> None:
    step = CronExpression("*/15 * * * *")
    assert {m for m in range(60) if step.matches(datetime(2026, 1, 1, 0, m))} == {
        0,
        15,
        30,
        45,
    }

    ranged = CronExpression("0 9-11 * * *")
    assert ranged.matches(datetime(2026, 1, 1, 10, 0))
    assert not ranged.matches(datetime(2026, 1, 1, 12, 0))

    listed = CronExpression("0,20,40 * * * *")
    assert listed.matches(datetime(2026, 1, 1, 5, 20))
    assert not listed.matches(datetime(2026, 1, 1, 5, 21))

    ranged_step = CronExpression("0-30/10 * * * *")
    assert {m for m in range(60) if ranged_step.matches(datetime(2026, 1, 1, 0, m))} == {
        0,
        10,
        20,
        30,
    }


def test_step_from_a_single_value_runs_to_the_field_maximum() -> None:
    """`N/M` means "from N, stepping by M, up to the maximum", not just N."""
    expression = CronExpression("5/15 * * * *")

    assert {m for m in range(60) if expression.matches(datetime(2026, 1, 1, 0, m))} == {
        5,
        20,
        35,
        50,
    }
    # A bare single value without a step stays a single value.
    single = CronExpression("5 * * * *")
    assert {m for m in range(60) if single.matches(datetime(2026, 1, 1, 0, m))} == {5}


def test_day_of_week_uses_cron_numbering_and_accepts_seven_as_sunday() -> None:
    # 2026-07-05 is a Sunday, 2026-07-06 a Monday.
    monday = CronExpression("0 0 * * 1")
    assert monday.matches(datetime(2026, 7, 6, 0, 0))
    assert not monday.matches(datetime(2026, 7, 7, 0, 0))

    assert CronExpression("0 0 * * 0").matches(datetime(2026, 7, 5, 0, 0))
    assert CronExpression("0 0 * * 7").matches(datetime(2026, 7, 5, 0, 0))


def test_day_of_month_and_day_of_week_combine_with_or_semantics() -> None:
    """Both fields restricted: Vixie cron matches if either one does."""
    expression = CronExpression("0 0 1 * 1")

    assert expression.matches(datetime(2026, 7, 1, 0, 0))  # the 1st, a Wednesday
    assert expression.matches(datetime(2026, 7, 6, 0, 0))  # a Monday
    assert not expression.matches(datetime(2026, 7, 7, 0, 0))  # neither


def test_next_after_is_strictly_after_the_given_instant() -> None:
    expression = CronExpression("0 9 * * 1")  # 09:00 every Monday

    assert expression.next_after(datetime(2026, 7, 4, 12, 0)) == datetime(2026, 7, 6, 9, 0)
    # An exact match does not return itself.
    assert expression.next_after(datetime(2026, 7, 6, 9, 0)) == datetime(2026, 7, 13, 9, 0)


def test_next_after_stops_instead_of_looping_on_an_impossible_expression() -> None:
    assert CronExpression("0 0 30 2 *").next_after(datetime(2026, 1, 1, 0, 0)) is None


def test_validation_accepts_supported_shapes() -> None:
    assert validate_cron("*/5 * * * *")
    assert validate_cron("0 9-17 * * 1,3,5")


@pytest.mark.parametrize(
    "expression",
    [
        "* * * *",  # too few fields
        "* * * * * *",  # seconds are not supported
        "99 * * * *",  # minute out of range
        "* 24 * * *",  # hour out of range
        "abc * * * *",  # not a number
        "*/0 * * * *",  # a zero step would re-arm forever
        "JAN * * * *",  # month and weekday names are out of scope
        "  * * * *",  # leading blanks collapse: whitespace-split yields 4 fields
    ],
)
def test_validation_rejects_unsupported_shapes(expression: str) -> None:
    assert validate_cron(expression) is False


def test_no_field_can_be_empty_because_split_drops_blanks() -> None:
    """`_parse_field`'s empty-field guard is unreachable from a public call."""
    assert validate_cron("   ") is False
    assert validate_cron("* * * * \t") is False


def test_parsing_rejects_with_value_error_not_a_custom_type() -> None:
    """`validate_cron` only catches (ValueError, TypeError); pin that contract."""
    with pytest.raises(ValueError, match="5 fields"):
        CronExpression("* * * *")
    with pytest.raises(ValueError, match="out of range"):
        CronExpression("99 * * * *")
    with pytest.raises(ValueError, match="matches nothing"):
        CronExpression("30-10 * * * *")
