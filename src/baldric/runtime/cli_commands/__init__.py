"""CLI subcommand implementations.

``cli.py`` keeps argument parsing and mode dispatch (< 600 lines target); the
subcommands it dispatches to live here, one module per command family. They are
plain functions (the CLI routes manually rather than using typer subcommands) and
``cli`` imports them into its namespace, so tests that patch a command on the CLI
module keep working.
"""
