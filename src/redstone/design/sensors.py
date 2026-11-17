"""Other things than a lever or button at the input of a design: a pressure plate or a daylight detector.

The search designs and proves circuits with levers and buttons as inputs. `with_input` swaps every input for a
pressure plate and checks in the simulator that the circuit reacts to the same presses as before: same state at
the end of every press and the same number of switch-ons (the pulse of a plate is longer than a button's, so the
times are not compared). A plate is a push button, not a switch: logic that needs an input to stay on
("A und B", "bleibt an") cannot be built with it, and `with_input` says so. Returns None (with a German reason)
when nothing fits or follows.

A daylight detector is a switch, not a push button: it stands in for a lever ("an, wenn es Tag ist" or, inverted,
"Nacht"). It reads the sky (nothing may be built above it) and gives an analog signal, so a repeater follows it
and powers what the lever powered. `with_input` checks it by setting the clock (scenario action `time`) instead
of flipping the lever, at several places and in all four rotations."""

from __future__ import annotations

import re
from dataclasses import replace

from ..model import BlockState, Grid, Pos
from .actuators import SETTLE, SIDES, _built, _on
from .candidate import Candidate
from .behaviour import START, BehaviourSpec, Trial

# name -> (German label, block)
SENSORS: dict[str, tuple[str, str]] = {
    "stone_pressure_plate": ("Steindruckplatte", "stone_pressure_plate[powered=false]"),
    "oak_pressure_plate": ("Holzdruckplatte", "oak_pressure_plate[powered=false]"),
    "daylight_detector": ("Tageslichtsensor", "daylight_detector[inverted=false,power=0]"),
    "daylight_detector_inverted": ("Tageslichtsensor (invertiert, für Nacht)",
                                   "daylight_detector[inverted=true,power=0]"),
}
# daylight kinds -> clock times (scenario action `time`) for "lever on" and "lever off": noon and midnight
DAYLIGHT = {"daylight_detector": (6000, 18000), "daylight_detector_inverted": (18000, 6000)}
DAY_ORIGINS = 6  # places (robust.origins) the daylight variant is checked at, in each rotation
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
    if kind in DAYLIGHT:
        return _with_daylight(cand, kind, spec)
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


# --- daylight detector ---------------------------------------------------------------------------------------


def _switch_traces(cand: Candidate, phases: list[bool], times: tuple[int, int] | None,
                   origin: Pos | None = None) -> list[tuple[tuple[bool, ...], tuple[int, ...]]]:
    """For the start and every phase (input on/off): the outputs' state at the end and how often each switched
    on. times None: the input is a lever, flipped when the phase changes. Else the clock is set to times[0]
    (input on) or times[1] (off); the detector reads it at its next 20 gt beat."""
    from ..sim import blocks  # noqa: F401  (registers block behaviours)
    from ..sim.core import World
    from ..sim.runner import ORACLE_ORIGIN, apply_input

    origin = ORACLE_ORIGIN if origin is None else origin
    world = World()
    world.place_grid(cand.grid, origin)
    outs = [p + origin for p in cand.outputs]
    at = cand.inputs[0] + origin
    if times is not None:
        apply_input(world, "time", at, None, times[1])
    last = [_on(world.get(p)) for p in outs]
    out = []
    state = False
    for on in [False] + phases:
        rises = [0] * len(outs)
        if on != state:
            state = on
            if times is None:
                apply_input(world, "use", at, None)
            else:
                apply_input(world, "time", at, None, times[0] if on else times[1])
        for _ in range(SETTLE + 25):
            world.tick()
            now = [_on(world.get(p)) for p in outs]
            for k, (a, b) in enumerate(zip(last, now)):
                rises[k] += (not a) and b
            last = now
        out.append((tuple(last), tuple(rises)))
    return out


def _daylight_variants(cand: Candidate, kind: str):
    """cand with the detector in place of its one lever, every way that fits: (a) a repeater in the lever's cell
    pointing away from the detector, (b) the lever removed and a repeater pointing into the block the lever
    was fixed to (which the lever powered strongly), the detector behind it."""
    from ..sim import blockdata

    block = SENSORS[kind][1]
    base = {tuple(p): str(s) for p, s in cand.grid.items() if s.id != "air"}
    lever = tuple(cand.inputs[0])
    state = cand.grid.get(cand.inputs[0])
    x, y, z = lever
    face = state.get("face")
    if face == "wall":
        dx, dz = {"north": (0, 1), "south": (0, -1), "west": (1, 0), "east": (-1, 0)}[state.get("facing")]
        fixed = (x + dx, y, z + dz)
    elif face == "ceiling":
        fixed = (x, y + 1, z)
    else:
        fixed = (x, y - 1, z)
    opposite = {"north": "south", "south": "north", "west": "east", "east": "west"}
    for target in (None, fixed):
        for side, (sx, sz) in SIDES.items():
            cells = dict(base)
            del cells[lever]
            free = lambda c: cells.get(c, "air") == "air"  # noqa: E731
            if target is None:  # (a) repeater at the lever, output towards `side`
                rep, det, facing = lever, (x - sx, y, z - sz), opposite[side]
            else:  # (b) repeater beside the fixed block, output into it
                tx, ty, tz = target
                rep, det, facing = (tx + sx, ty, tz + sz), (tx + 2 * sx, ty, tz + 2 * sz), side
            if not (free(rep) and free(det)):
                continue
            hi = max(c[1] for c in cells) if cells else det[1]
            if any(not free((det[0], yy, det[2])) for yy in range(det[1] + 1, hi + 1)):
                continue  # something above the detector would shade it
            floor = (rep[0], rep[1] - 1, rep[2])
            if free(floor):
                cells[floor] = "stone"
            elif not blockdata.is_conductor(BlockState.parse(cells[floor])):
                continue
            cells[rep] = f"repeater[delay=1,facing={facing},locked=false,powered=false]"
            cells[det] = block
            yield _built(cand, cells, [tuple(p) for p in cand.outputs], [det])


_HOURS: dict[bool, tuple[int, int]] = {}


def daylight_hours(inverted: bool) -> tuple[int, int]:
    """Clock times (open sky, clear weather) at which the detector's signal starts and stops (power >= 1),
    to 10 ticks."""
    if inverted not in _HOURS:
        from ..sim import blocks  # noqa: F401
        from ..sim.blocks.daylight import sky_darken_at, target_power
        from ..sim.world import World

        world = World()
        pos = Pos(0, 200, 0)
        st = BlockState.parse(f"daylight_detector[inverted={'true' if inverted else 'false'},power=0]")
        world.set_block(pos, st, 2)
        on = []
        for t in range(0, 24000, 10):
            world.day_time = t
            world.sky_darken = sky_darken_at(t)
            on.append(target_power(world, pos, st) > 0)
        start = next(i for i in range(len(on)) if on[i] and not on[i - 1]) * 10
        stop = next(i for i in range(len(on)) if not on[i] and on[i - 1]) * 10
        _HOURS[inverted] = (start, stop)
    return _HOURS[inverted]


def _clock(t: int) -> str:
    """Minecraft clock time as a wall clock (time 0 = 6 o'clock)."""
    minutes = ((t + 6000) % 24000) * 60 // 1000
    return f"{minutes // 60}:{minutes % 60:02d} Uhr"


def _with_daylight(cand: Candidate, kind: str, spec=None) -> tuple[Candidate | None, str]:
    from .compose import rotate
    from .robust import origins

    label = SENSORS[kind][0]
    night = kind.endswith("inverted")
    if len(cand.inputs) != 1:
        return None, f"{label} ersetzt den Eingang nur bei Entwürfen mit genau einem Hebel"
    if _input_kind(cand.grid.get(cand.inputs[0])) != "lever" or (
            isinstance(spec, BehaviourSpec) and any(k != "lever" for k in spec.input_kinds)):
        return None, (f"{label} ist ein Schalter (an, solange es {'Nacht' if night else 'Tag'} ist), kein "
                      "Taster; er passt nur an die Stelle eines Hebels")
    times = DAYLIGHT[kind]
    phases = [True, False, True, True, False, True, False, False]
    want = _switch_traces(cand, phases, None)
    places = origins(DAY_ORIGINS)
    for new in _daylight_variants(cand, kind):
        if _switch_traces(new, phases, times) != want:
            continue
        turned = [rotate(new, t) for t in range(4)]
        if all(_switch_traces(c, phases, times, o) == want for c in turned if c is not None for o in places):
            break
    else:
        return None, f"{label} schaltet an diesem Entwurf nicht wie der Hebel"
    start, stop = daylight_hours(night)
    note = (f"Eingang: {label} statt Hebel, dahinter ein Verstärker (der Sensor gibt ein je nach Sonnenstand "
            f"schwaches Signal). Der Hebel gilt als „{'nachts' if night else 'tagsüber'} an“: unter freiem Himmel "
            f"bei klarem Wetter schaltet der Sensor etwa um {_clock(start)} ein und um {_clock(stop)} aus "
            f"(Spielzeit {start} bis {stop}; er schaut nur einmal pro Sekunde nach). Über dem Sensor darf nichts "
            f"gebaut werden. Im Simulator gegen die Fassung mit Hebel geprüft (Mittag und Mitternacht, an "
            f"{len(places)} Orten, in allen Drehungen); wie der Sensor auf die Tageszeit reagiert, ist im echten "
            "Spiel aufgenommen.")
    return replace(new, description=f"{cand.description} {note}".strip()), note
