"""Mechanics notes: components report special behaviour they actually used during a simulation.

The analysis lists these as "genutzte Sonderfälle"; they are evidence from the simulation, not guesses
from the layout. Kinds are stable identifiers (see MECHANICS for the German descriptions).
"""

from __future__ import annotations

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
    "quasi_connectivity": "Quasi-Connectivity: Ein Block wird über die Position über ihm gepowert",
    "bud": "BUD: Ein quasi-gepowerter Block reagiert erst bei einem späteren Block-Update",
    "piston_spit": "Klebriger Kolben lässt seinen Block bei einem kurzen Puls los",
    "zero_tick": "0-Tick-Puls: Ein Kolben fährt im selben Tick aus und wieder ein",
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


def notes_of(world: World) -> list[Note]:
    return list(world.__dict__.get("notes", []))
