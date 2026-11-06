"""Shared, package-importable test helpers.

Kept importable under the ``tests`` package so sibling test modules can reuse
fakes/fixtures without relying on pytest's prepend-import rootdir mode or an
``isolate_home``-style helper being redefined in every module.
"""