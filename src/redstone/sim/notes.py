"""Mechanics notes: components report special behaviour they actually used during a simulation.

The analysis lists these as "genutzte Sonderfälle"; they are evidence from the simulation, not guesses
from the layout. Kinds are stable identifiers (see MECHANICS for the German descriptions).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..model import Pos

if TYPE_CHECKING:
    from .world import World

MECHANICS = {
    "repeater_lock": "Repeater-Sperre: Ein Repeater hält seinen Zustand, weil eine Diode von der Seite in ihn zeigt",
    "repeater_pulse_extend": "Pulsverlängerung: Ein Repeater verlängert einen Puls, der kürzer als sein Delay ist",
    "comparator_subtract": "Comparator im Subtraktionsmodus zieht ein Seitensignal vom Eingang ab",
    "comparator_compare_block": "Comparator im Vergleichsmodus sperrt, weil das Seitensignal stärker ist",
    "comparator_container": "Comparator liest den Füllstand eines Blocks mit analogem Ausgang (Container o. ä.)",
    "comparator_through_block": "Comparator liest einen analogen Ausgang durch einen Leiterblock hindurch",
    "torch_burnout": "Fackel-Burnout: Eine Redstone-Fackel brennt nach 8 Abschaltungen in 60 gt durch",
    "observer_pulse": "Observer erkennt eine Zustandsänderung (Shape-Update) und gibt einen 2-gt-Puls",
    "quasi_connectivity": "Quasi-Connectivity: Ein Kolben fährt aus, weil die Position über ihm gepowert ist, "
                          "nicht er selbst",
    "bud": "BUD: Ein Kolben ist (quasi-)bestromt bzw. unbestromt, reagiert aber erst bei einem späteren "
           "Block-Update",
    "piston_spit": "Block-Dropping: Ein klebriger Kolben lässt seinen Block bei einem kurzen Puls an der "
                   "ausgefahrenen Position liegen",
    "zero_tick": "0-Tick: Ein Kolben fährt in derselben Block-Event-Phase aus und wieder ein",
    "wire_locational": "Positionsabhängige Update-Reihenfolge von Redstone-Staub beeinflusst das Ergebnis",
}


@dataclass(frozen=True)
class Note:
    tick: int
    kind: str
    pos: Pos
    detail: str = ""


def note(world: World, kind: str, pos: Pos, detail: str = "") -> None:
    if kind not in MECHANICS:
        raise KeyError(f"unknown mechanics note {kind!r}")
    seen: set[tuple[str, Pos]] = world.__dict__.setdefault("_notes_seen", set())
    if (kind, pos) in seen:  # first occurrence per block is enough evidence
        return
    seen.add((kind, pos))
    world.__dict__.setdefault("notes", []).append(Note(world.game_time, kind, pos, detail))


# Checks of resting states (e.g. a piston in a BUD state), run whenever the notes are collected. They only
# read the world and call note(); block modules register them at import time.
_STATE_CHECKS: list[Callable[[World], None]] = []


def register_state_check(check: Callable[[World], None]) -> None:
    if check not in _STATE_CHECKS:
        _STATE_CHECKS.append(check)


def notes_of(world: World) -> list[Note]:
    """All notes so far, including those from the state checks applied to the current state of the world."""
    collect = getattr(world, "collect_notes", None)  # Rust core: notes and state checks live in the core
    if collect is not None:
        return collect()
    for check in _STATE_CHECKS:
        check(world)
    return list(world.__dict__.get("notes", []))
