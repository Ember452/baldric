"""Append structured, always-on instructions to Baldric's system prompt."""

from baldric_coding.extensions import ExtensionAPI


def setup(baldric: ExtensionAPI) -> None:
    """Add a labeled procedure while this extension generation is active."""
    baldric.add_prompt_section(
        "Review procedure",
        """Read the complete diff before editing.

Run the relevant checks before reporting success:

```bash
uv run pytest
uv run ruff check .
```
""",
    )
