"""Baldric core runtime: session orchestration, tools, commands, and context.

This package is the target home for the application core extracted from the
original ``baldric.runtime`` during the structural rearchitecture. It is created
incrementally; today it holds the persisted-session JSONL codec, which is
behaviour (parse + migrate + validate) and therefore does not belong in the
``baldric.protocol`` contract package.
"""
