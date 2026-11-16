"""Other things than a lever or button at the input of a design: a pressure plate.

The search designs and proves circuits with levers and buttons as inputs. `with_input` swaps every input for a
pressure plate and checks in the simulator that the circuit reacts to the same presses as before: same state at
the end of every press and the same number of switch-ons (the pulse of a plate is longer than a button's, so the
times are not compared). A plate is a push button, not a switch: logic that needs an input to stay on
("A und B", "bleibt an") cannot be built with it, and `with_input` says so. Returns None (with a German reason)
when nothing fits or follows."""

from __future__ import annotations

import re
from dataclasses import replace

from ..model import BlockState, Grid, Pos
from .actuators import SETTLE, _built, _on
from .candidate import Candidate
from .behaviour import START, BehaviourSpec, Trial

# name -> (German label, block)
SENSORS: dict[str, tuple[str, str]] = {
    "stone_pressure_plate": ("Steindruckplatte", "stone_pressure_plate[powered=false]"),
    "oak_pressure_plate": ("Holzdruckplatte", "oak_pressure_plate[powered=false]"),
}
# Behaviours (BehaviourSpec.kind) that react to a single press: a plate is as good as a button there
IMPULSE_KINDS = ("Monoflop", "Pulsverlängerer", "T-Flip-Flop", "RS-Latch")
PLATE_GT = 20  # a plate releases 20 gt after the last entity stepped on it


def _input_kind(state: BlockState) -> str | None:
    if state.id == "lever":
        return "lever"
    if state.id.endswith("_button"):
        return "button"
    if state.id.endswith("_pressure_plate"):
        return "plate"
    return None


def button_spec(spec):
    """The same behaviour with a press instead of a lever pulse per input (what a plate delivers); None if
    that cannot be derived."""
    if not isinstance(spec, BehaviourSpec) or spec.gate is not None or not spec.inputs:
        return None
    if all(k == "button" for k in spec.input_kinds):
        return spec
    if not spec.kind.startswith(IMPULSE_KINDS) or any(t.periodic for t in spec.trials):
        return None
    if spec.kind.startswith("Pulsverl"):  # output stays on for max(press, length): a plate presses for PLATE_GT
        m = re.search(r"mindestens (\d+) gt", spec.kind)
        if not m or spec.nominal_delay is None:
            return None
        d = spec.nominal_delay
        trial = Trial("Tastendruck", [(START, 0)], [[(START + d, START + d + max(PLATE_GT, int(m.group(1))))]])
        return replace(spec, input_kinds=["button"] * len(spec.inputs), trials=[trial])
    trials: list[Trial] = []
    seen = set()
    for t in spec.trials:
        actions = []
        for i in range(len(spec.inputs)):
            mine = sorted(a for a in t.actions if a[1] == i)
            if len(mine) % 2:
                return None
            actions += mine[::2]  # the press is the first of every on/off pair
        actions.sort()
        key = (tuple(actions), repr(t.expected))
        if key not in seen:
            seen.add(key)
            trials.append(replace(t, actions=actions))
    return replace(spec, input_kinds=["button"] * len(spec.inputs), trials=trials)


def _presses(n: int) -> list[int]:
    """Which input is pressed in every phase: each one twice in a row, then in turn, then backwards."""
    return [i for i in range(n) for _ in range(2)] + list(range(n)) * 2 + list(reversed(range(n))) * 2


def _traces(cand: Candidate, seq: list[int]) -> list[tuple[tuple[bool, ...], tuple[int, ...]]]:
    """For every press: the outputs' state after SETTLE ticks and how often each switched on."""
    from ..sim import blocks  # noqa: F401  (registers block behaviours)
    from ..sim.core import World
    from ..sim.runner import ORACLE_ORIGIN, apply_input

    world = World()
    world.place_grid(cand.grid, ORACLE_ORIGIN)
    outs = [p + ORACLE_ORIGIN for p in cand.outputs]
    out = []
    last = [_on(world.get(p)) for p in outs]
    for i in seq:
        at = cand.inputs[i] + ORACLE_ORIGIN
        kind = _input_kind(world.get(at))
        rises = [0] * len(outs)

        def run(n: int) -> None:
            nonlocal last
            for _ in range(n):
                world.tick()
                now = [_on(world.get(p)) for p in outs]
                for k, (a, b) in enumerate(zip(last, now)):
                    rises[k] += (not a) and b
                last = now

        if kind == "plate":
            apply_input(world, "step", at, None)
        elif kind == "lever":  # a press of a lever: on, a moment, off
            apply_input(world, "use", at, None)
            run(6)
            apply_input(world, "use", at, None)
        else:
            apply_input(world, "use", at, None)
        run(SETTLE)
        out.append((tuple(last), tuple(rises)))
    return out


def _variant(cand: Candidate, kind: str) -> Candidate:
    """cand with a plate in place of every input. A floor input: the plate takes its cell. A wall input: the
    plate lies on top of the block it hung at (which it powers just like the button did)."""
    from ..sim import blockdata

    label, block = SENSORS[kind]
    cells = {tuple(p): str(s) for p, s in cand.grid.items() if s.id != "air"}
    inputs = []
    for p in cand.inputs:
        state = cand.grid.get(p)
        if _input_kind(state) is None:
            raise ValueError(f"der Eingang bei {tuple(p)} ist weder Hebel noch Knopf")
        x, y, z = p
        face = state.get("face")
        if face == "wall":
            dx, dz = {"north": (0, 1), "south": (0, -1), "west": (1, 0), "east": (-1, 0)}[state.get("facing")]
            base = (x + dx, y, z + dz)  # the block the lever or button hangs at
            at = (base[0], y + 1, base[2])
            if base not in cells or not blockdata.is_conductor(BlockState.parse(cells[base])):
                raise ValueError(f"{label} passt nicht an den Eingang bei {(x, y, z)}")
            if cells.get(at, "air") != "air":
                raise ValueError(f"über dem Block am Eingang ist kein Platz für {label}")
            del cells[(x, y, z)]
        elif face == "ceiling":
            raise ValueError("an der Decke lässt sich keine Druckplatte anbringen")
        else:
            at = (x, y, z)
            below = cells.get((x, y - 1, z), "air")
            if below == "air" or not blockdata.is_conductor(BlockState.parse(below)):
                raise ValueError(f"unter dem Eingang bei {(x, y, z)} ist kein fester Block für {label}")
        cells[at] = block
        inputs.append(at)
    return _built(cand, cells, [tuple(p) for p in cand.outputs], inputs)


def with_input(cand: Candidate, kind: str, spec=None) -> tuple[Candidate | None, str]:
    """cand with `kind` (a key of SENSORS) at its inputs, checked against the lever/button version.

    spec: the behaviour the design was made for. Without it only designs whose inputs are all buttons count."""
    if kind not in SENSORS:
        return None, f"unbekannter Eingang {kind!r}"
    label = SENSORS[kind][0]
    kinds = [_input_kind(cand.grid.get(p)) for p in cand.inputs]
    if not cand.inputs or None in kinds:
        return None, f"{label} braucht einen Entwurf mit Hebel oder Knopf als Eingang"
    if "plate" in kinds:
        return None, "der Entwurf hat schon eine Druckplatte"
    pulse = all(k == "button" for k in kinds) or (
        isinstance(spec, BehaviourSpec) and spec.gate is None and spec.kind.startswith(IMPULSE_KINDS))
    if not pulse:
        return None, (f"{label} ist ein Taster und schaltet sich nach kurzer Zeit wieder ab; für Schaltungen, bei "
                      "denen ein Eingang eingeschaltet bleiben muss (z. B. „A und B“), braucht es Hebel")
    try:
        new = _variant(cand, kind)
    except ValueError as e:
        return None, str(e)
    seq = _presses(len(cand.inputs))
    if _traces(new, seq) != _traces(cand, seq):
        return None, f"{label} schaltet an diesem Entwurf nicht wie der Knopf"
    note = (f"Eingang: {label} statt Hebel oder Knopf; im Simulator gegen die Fassung mit Knopf geprüft (im "
            "echten Spiel nicht aufgenommen). Eine Druckplatte löst aus, wenn jemand darauf tritt"
            + (" (Holzplatten auch bei Gegenständen)." if kind.startswith("oak") else "."))
    return replace(new, description=f"{cand.description} {note}".strip()), note
