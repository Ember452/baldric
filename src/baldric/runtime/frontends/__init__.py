"""Frontends: the surfaces that render and drive one agent session.

Each subpackage is one frontend (for example ``tui``). Frontends consume the
core session and the platform contracts; the core and platform layers never
import a frontend (enforced by ``scripts/check_import_graph.py``). A feature that
ships its own widgets (``features/subagents/ui``) imports this toolkit directly —
a documented, deliberate exception to "features do not depend on frontends".
"""
