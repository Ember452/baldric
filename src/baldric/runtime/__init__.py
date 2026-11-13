"""Baldric coding-agent application package.

This package root deliberately exports almost nothing. It used to re-export a
139-name aggregate facade that pulled the entire application (156 modules: auth
flows, session, tools, frontends) into ``sys.modules`` on a bare
``import baldric.runtime``. Consumers import the owning submodule instead
(``baldric.runtime.session.session``, ``baldric.runtime.providers.config``, …);
extension authors use the stable ``baldric.api`` facade. Only the package version
lives here, and ``tests/test_public_surface.py`` pins that.
"""

from __future__ import annotations

from baldric.runtime.version import current_version

__version__ = current_version()

__all__ = ["__version__"]
