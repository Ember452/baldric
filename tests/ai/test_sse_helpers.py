"""Equivalence tests for the shared tolerant JSON helper.

``baldric_ai._sse.loads_object`` replaced six near-identical per-adapter copies.
These tests pin the behaviour those copies shared so a future change to the one
helper cannot silently alter what an adapter accepts from an SSE connection.
"""

from __future__ import annotations

import pytest

from baldric_ai._sse import loads_object


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"a": 1}', {"a": 1}),
        ("{}", {}),
        ('{"a": {"b": [1, 2]}}', {"a": {"b": [1, 2]}}),
        # Non-object JSON decodes fine but is not a mapping -> None.
        ("[1, 2, 3]", None),
        ('"a string"', None),
        ("42", None),
        ("null", None),
        ("true", None),
        # Malformed input -> None, never raises.
        ("{not json", None),
        ("", None),
        ("   ", None),
        ("{", None),
    ],
)
def test_loads_object_matches_previous_adapter_behaviour(text: str, expected: object) -> None:
    assert loads_object(text) == expected


def test_loads_object_never_raises_on_malformed() -> None:
    for bad in ("{", "}", "[", "}{", "not json at all", "\x00"):
        assert loads_object(bad) is None
