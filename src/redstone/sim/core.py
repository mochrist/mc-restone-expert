"""Choice of the simulator core: the Python reference (``world.World``) or the Rust port (``rust_world``).

The environment variable ``RSX_SIM_CORE`` (``python``, ``rust`` or ``auto``) sets the default; ``auto`` takes
the Rust core when the extension module ``rsx_core`` is installed. ``use()`` switches at run time; worlds
that already exist keep their core.
"""

from __future__ import annotations

import os

from ..model import Grid
from .world import World as PythonWorld

CORES = ("python", "rust")
_rust_error: str | None = None
_active: str | None = None


def _rust_world_class():
    from .rust_world import RustWorld

    return RustWorld


def rust_available() -> bool:
    """True if the Rust core can be imported (see ``rust_error()`` for the reason if not)."""
    global _rust_error
    try:
        _rust_world_class()
    except ImportError as e:
        _rust_error = str(e)
        return False
    return True


def rust_error() -> str | None:
    return _rust_error


def use(name: str) -> str:
    """Select the core for new worlds: "python", "rust" or "auto". Returns the name of the active core."""
    global _active
    if name == "auto":
        name = "rust" if rust_available() else "python"
    if name not in CORES:
        raise ValueError(f"unknown simulator core {name!r}; expected python, rust or auto")
    if name == "rust" and not rust_available():
        raise RuntimeError(f"the Rust simulator core is not available: {_rust_error}")
    _active = name
    return name


def active() -> str:
    """Name of the core new worlds use."""
    if _active is None:
        use(os.environ.get("RSX_SIM_CORE", "auto").strip().lower() or "auto")
    assert _active is not None
    return _active


def world_class() -> type:
    return _rust_world_class() if active() == "rust" else PythonWorld


class World:
    """``World()`` creates a world of the active core (``redstone.sim.world.World`` or ``RustWorld``)."""

    def __new__(cls, *args, **kwargs):
        return world_class()(*args, **kwargs)

    @staticmethod
    def from_grid(grid: Grid, *args, **kwargs):
        return world_class().from_grid(grid, *args, **kwargs)
