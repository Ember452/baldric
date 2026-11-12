"""Product features: self-contained capabilities built on the agent core.

Each subpackage is one product capability (for example ``subagents``). A feature
owns its implementation files, registers itself through the extension API, and
is loaded by the platform layer by *string path* (never a static import) so that
``core`` / ``platform`` / ``frontends`` never import a feature implementation
directly. This is the S1a rule enforced by
``tests/guards/test_import_boundaries.py``.

Note on UI: a feature that ships Textual widgets (``subagents/ui``) imports the
TUI widget toolkit directly. That is a documented, deliberate exception to the
"features do not depend on frontends" aspiration (see the structural plan §4.3):
building a real widget requires the toolkit; the *host wiring* still goes through
the ``ComponentBridge`` protocol.
"""
