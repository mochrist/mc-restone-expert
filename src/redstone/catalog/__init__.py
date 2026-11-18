"""Catalog of finished, simulator-checked builds that cannot be derived from a truth table or a timing spec
(piston doors, item sorters, ...).

Every entry builds a settled `Grid` (stored at rest, inputs off) and carries an acceptance check that runs the
build in the simulator (tests/catalog/test_catalog.py, both cores). `rsx catalog` lists and writes entries; the
GUI assistant finds them by keyword (`find`).
"""

from __future__ import annotations

from .entries import ENTRIES, Entry, find, get

__all__ = ["ENTRIES", "Entry", "find", "get"]
