"""Generate scenarios/sculk-{wool,simultaneous,calibrated,resonance}.yaml (run from the repository root).

    uv run python scripts/gen_sculk_scenarios.py
"""

from __future__ import annotations

from pathlib import Path

SENSOR = "sculk_sensor[power=0,sculk_sensor_phase=inactive,waterlogged=false]"
LEVER_OFF = "lever[face=floor,facing=east,powered=false]"
LEVER_ON = "lever[face=floor,facing=east,powered=true]"
COMPARATOR = "comparator[facing={f},mode=compare,powered=false]"
OUT = Path(__file__).resolve().parents[1] / "scenarios"


def cal(facing: str = "east") -> str:
    return f"calibrated_sculk_sensor[facing={facing},power=0,sculk_sensor_phase=inactive,waterlogged=false]"


def wire(power: int, east: str = "side", west: str = "side") -> str:
    return f"redstone_wire[east={east},north=none,power={power},south=none,west={west}]"


class Scenario:
    def __init__(self, name: str, description: str, size: tuple[int, int, int]) -> None:
        self.name, self.description, self.size = name, description, size
        self.blocks: list[tuple] = []
        self.fills: list[tuple] = []
        self.entities: list[tuple] = []
        self.inputs: list[tuple] = []
        self.probes: dict[str, tuple] = {}

    def block(self, x, y, z, state):
        self.blocks.append((x, y, z, state))

    def comparator(self, x, y, z, facing):
        self.block(x, y, z, COMPARATOR.format(f=facing))
        self.entities.append((x, y, z, '{id:"minecraft:comparator",OutputSignal:0}'))

    def use(self, tick, x, y, z):
        self.inputs.append((tick, x, y, z, "use", None))

    def setblock(self, tick, x, y, z, state):
        self.inputs.append((tick, x, y, z, "setblock", state))

    def write(self, ticks: int) -> None:
        lines = [f"name: {self.name}", "description: >"]
        lines += [f"  {line}" for line in self.description.strip().splitlines()]
        lines += ["build:", f"  size: [{self.size[0]}, {self.size[1]}, {self.size[2]}]", "  fill:"]
        for f in self.fills:
            lines.append(f'    - [{f[0]}, {f[1]}, {f[2]}, {f[3]}, {f[4]}, {f[5]}, "{f[6]}"]')
        lines.append("  blocks:")
        for x, y, z, state in self.blocks:
            lines.append(f'    - [{x}, {y}, {z}, "{state}"]')
        if self.entities:
            lines.append("  block_entities:")
            for x, y, z, snbt in self.entities:
                lines.append(f"    - [{x}, {y}, {z}, '{snbt}']")
        lines += [f"ticks: {ticks}", "inputs:"]
        for tick, x, y, z, action, state in sorted(self.inputs, key=lambda i: i[0]):
            extra = f', state: "{state}"' if state else ""
            lines.append(f"  - {{tick: {tick}, pos: [{x}, {y}, {z}], action: {action}{extra}}}")
        lines.append("probes:")
        for name, (x, y, z) in self.probes.items():
            lines.append(f"  {name}: [{x}, {y}, {z}]")
        (OUT / f"{self.name}.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def wool() -> None:
    s = Scenario(
        "sculk-wool",
        """
        Wolle zwischen Hebel (8,1,8) und Sculk-Sensoren (alle im Radius 8): Wollbloecke schirmen die Vibration ab
        (Gerade, von oben), Teppich nicht, Wolle neben der Linie nicht. Diagonale Linien laufen genau durch
        Blockecken; dort entscheidet die Verschiebung des Startpunkts um 1e-5 in die sechs Richtungen, ob die
        Vibration abgeschirmt ist (Wolle nur auf einer der beiden Seiten, auf beiden Seiten, auf der Diagonalen).
        Der Hebel schaltet bei 2 ein und bei 70 aus.
        """,
        (17, 8, 17),
    )
    s.fills.append((0, 0, 0, 16, 0, 16, "stone"))
    s.block(8, 1, 8, LEVER_OFF)
    cases = {
        # name: (sensor position, wool positions, carpet positions)
        "straight_blocked": ((12, 1, 8), [(10, 1, 8)], []),
        "straight_beside": ((4, 1, 8), [(6, 1, 9), (6, 1, 7)], []),
        "above": ((8, 5, 8), [(8, 3, 8)], []),
        "carpet": ((8, 1, 2), [], [(8, 1, 5)]),
        "free": ((8, 1, 13), [], []),
        # horizontal diagonals pass exactly through block corners; wool on the alternative cells at a corner
        "diag_se_one": ((12, 1, 12), [(10, 1, 9)], []),
        "diag_sw_both": ((4, 1, 12), [(6, 1, 9), (7, 1, 10)], []),
        "diag_nw_one": ((4, 1, 4), [(6, 1, 7)], []),
        "diag_ne_both": ((12, 1, 4), [(10, 1, 7), (9, 1, 6)], []),
        # diagonals in the x-y plane
        "diag_xy_on_line": ((11, 4, 8), [(10, 3, 8)], []),
        "diag_xy_one": ((5, 4, 8), [(8, 2, 8)], []),
    }
    for name, (sensor, wools, carpets) in cases.items():
        s.block(*sensor, SENSOR)
        for w in wools:
            s.block(*w, "white_wool")
        for c in carpets:
            s.block(*c, "white_carpet")
        s.probes[name] = sensor
    s.use(2, 8, 1, 8)
    s.use(70, 8, 1, 8)
    s.write(130)


def simultaneous() -> None:
    s = Scenario(
        "sculk-simultaneous",
        """
        Mehrere Vibrationen am selben Sensor. Gruppe 0/1: Hebel in Abstand 2 und 5 im selben Tick (die naehere
        gewinnt, egal in welcher Reihenfolge die Eingaben kommen). Gruppe 2/3: gleicher Abstand 3, Hebel aus (9) und
        Hebel an (10) im selben Tick: die hoehere Frequenz gewinnt, egal in welcher Reihenfolge. Gruppe 4: eine
        Vibration aus Abstand 7 ist unterwegs, die naehere bei Tick 5 wird ignoriert, ebenso die bei 12 (Sensor aktiv).
        Komparatoren zeigen die Frequenz.
        """,
        (100, 2, 12),
    )
    s.fills.append((0, 0, 0, 99, 0, 11, "stone"))
    for g in range(5):
        ox = 20 * g
        sx = ox + 8
        s.block(sx, 1, 4, SENSOR)
        s.comparator(sx + 1, 1, 4, "west")
        s.probes[f"g{g}_sensor"] = (sx, 1, 4)
        s.probes[f"g{g}_cmp"] = (sx + 1, 1, 4)
    # group 0/1: A (distance 2), B (distance 5)
    for g, order in ((0, "AB"), (1, "BA")):
        sx = 20 * g + 8
        s.block(sx - 2, 1, 4, LEVER_OFF)  # A
        s.block(sx, 1, 9, LEVER_OFF)  # B
        pos = {"A": (sx - 2, 1, 4), "B": (sx, 1, 9)}
        for c in order:
            s.use(2, *pos[c])
    # group 2/3: X (powered, off -> 9) and Y (on -> 10), both at distance 3
    for g, order in ((2, "YX"), (3, "XY")):
        sx = 20 * g + 8
        s.block(sx - 3, 1, 4, LEVER_ON)  # X
        s.block(sx, 1, 1, LEVER_OFF)  # Y
        pos = {"X": (sx - 3, 1, 4), "Y": (sx, 1, 1)}
        for c in order:
            s.use(2, *pos[c])
    # group 4: far lever F (7) first, near lever N (2) later
    sx = 20 * 4 + 8
    s.block(sx + 7, 1, 4, LEVER_OFF)
    s.block(sx - 2, 1, 4, LEVER_OFF)
    s.use(2, sx + 7, 1, 4)
    s.use(5, sx - 2, 1, 4)
    s.use(12, sx - 2, 1, 4)
    s.write(80)


def calibrated() -> None:
    s = Scenario(
        "sculk-calibrated",
        """
        Kalibrierter Sculk-Sensor (Radius 16, aktiv 10 gt, Abkuehlung 10 gt). Gruppe 0: ohne Eingang hinter dem Sensor
        nimmt er jede Vibration an, auch aus Abstand 12 (der normale Sensor daneben nicht); Lampen an drei Seiten
        leuchten, die Lampe auf der Eingangsseite nicht. Gruppe 1: Eingang 10 (Staub mit Staerke 10): Hebel an (10)
        wird angenommen, aus (9) nicht. Gruppe 2: Eingang 9: umgekehrt. Gruppe 3: Eingang 15 (Redstone-Block): nichts.
        Der Hebel schaltet bei 2, 70, 140 und 210. Komparatoren zeigen die Frequenz.
        """,
        (160, 2, 10),
    )
    s.fills.append((0, 0, 0, 159, 0, 9, "stone"))
    # group 0: free input, lever at distance 12, lamps
    ox = 0
    sx = ox + 8
    s.block(sx, 1, 4, cal())
    s.block(sx + 12, 1, 4, LEVER_OFF)
    s.block(sx, 1, 3, "redstone_lamp[lit=false]")
    s.block(sx + 1, 1, 4, "redstone_lamp[lit=false]")
    s.block(sx, 1, 5, "redstone_lamp[lit=false]")
    s.block(sx - 1, 1, 4, "redstone_lamp[lit=false]")
    s.block(sx, 1, 7, SENSOR)  # plain sensor at distance 12.4: out of range
    s.probes.update({"g0_sensor": (sx, 1, 4), "g0_lamp_n": (sx, 1, 3), "g0_lamp_e": (sx + 1, 1, 4),
                     "g0_lamp_s": (sx, 1, 5), "g0_lamp_back": (sx - 1, 1, 4), "g0_plain": (sx, 1, 7)})
    s.use(2, sx + 12, 1, 4)
    s.use(70, sx + 12, 1, 4)
    s.use(140, sx + 12, 1, 4)
    # groups 1-3: input from a dust line (power 10 / 9) or a redstone block (15), lever at distance 3
    for g, power in ((1, 10), (2, 9), (3, 15)):
        ox = 40 * g
        sx = ox + 8
        s.block(sx, 1, 4, cal())
        s.comparator(sx, 1, 5, "north")
        s.block(sx + 3, 1, 4, LEVER_OFF)
        s.probes[f"g{g}_sensor"] = (sx, 1, 4)
        s.probes[f"g{g}_cmp"] = (sx, 1, 5)
        if power == 15:
            s.block(sx - 1, 1, 4, "redstone_block")
        else:
            n = 16 - power  # wires; the one next to the redstone block has power 15, the n-th power 16 - n
            block_x = sx - 1 - n
            s.block(block_x, 1, 4, "redstone_block")
            for j in range(1, n + 1):
                x = block_x + j
                s.block(x, 1, 4, wire(16 - j))
            s.probes[f"g{g}_input"] = (sx - 1, 1, 4)
        for t in (2, 70, 140, 210):
            s.use(t, sx + 3, 1, 4)
    s.write(280)


def resonance() -> None:
    s = Scenario(
        "sculk-resonance",
        """
        Amethyst-Resonanz: Der Hebel (0,1,4) aktiviert Sensor A (2,1,4); der Amethystblock (3,1,4) neben A wiederholt
        die Vibration als resonate_10 an seiner Position, die Sensor B (9,1,4, ausser Reichweite des Hebels, Abstand 6
        zum Amethyst) empfaengt; B hat seinen eigenen Amethystblock (10,1,4), der Sensor C (16,1,4) erreicht.
        Komparatoren zeigen die Frequenz.
        """,
        (18, 2, 8),
    )
    s.fills.append((0, 0, 0, 17, 0, 7, "stone"))
    s.block(0, 1, 4, LEVER_OFF)
    for name, x in (("a", 2), ("b", 9), ("c", 16)):
        s.block(x, 1, 4, SENSOR)
        s.comparator(x, 1, 5, "north")
        s.probes[f"{name}_sensor"] = (x, 1, 4)
        s.probes[f"{name}_cmp"] = (x, 1, 5)
    s.block(3, 1, 4, "amethyst_block")
    s.block(10, 1, 4, "amethyst_block")
    s.use(2, 0, 1, 4)
    s.use(100, 0, 1, 4)
    s.write(180)


def placement() -> None:
    s = Scenario(
        "sculk-placement",
        """
        Platzieren und Entfernen von Sculk-Sensoren per setblock (Flags 3, mit onPlace). Gruppe 0: ein Sensor mit
        power=7, phase=active ohne geplanten Tick wird bei Tick 2 gesetzt; onPlace setzt die Staerke auf 0 zurueck
        (die Phase bleibt active, der Sensor nimmt danach nichts an). Gruppe 1: ein Hebel aktiviert einen Sensor mit
        Staub und Lampe daneben, der aktive Sensor wird bei Tick 12 durch Luft ersetzt (Nachbar-Updates). Gruppe 2:
        ein inaktiver Sensor wird bei Tick 2 durch einen kalibrierten Sensor mit power=0 und phase=cooldown ersetzt
        (bleibt ohne Tick fuer immer in der Abkuehlung). Gruppe 3: der aktive Sensor wird durch einen inaktiven
        ersetzt, der den naechsten Hebel annimmt. Gruppe 4: im Aufbau gesetzt (ohne onPlace) behaelt der aktive
        Sensor die Staerke 7.
        """,
        (100, 4, 10),
    )
    s.fills.append((0, 0, 0, 99, 0, 9, "stone"))
    active = "sculk_sensor[power=7,sculk_sensor_phase=active,waterlogged=false]"
    # group 0: placed active with power 7
    ox = 0
    s.block(ox + 5, 1, 4, wire(0, east="side", west="side"))
    s.block(ox + 6, 1, 4, "redstone_lamp[lit=false]")
    s.block(ox + 2, 1, 4, LEVER_OFF)
    s.setblock(2, ox + 4, 1, 4, active)
    s.use(20, ox + 2, 1, 4)
    s.probes.update({"g0_sensor": (ox + 4, 1, 4), "g0_dust": (ox + 5, 1, 4), "g0_lamp": (ox + 6, 1, 4)})
    # group 1: active sensor removed
    ox = 20
    s.block(ox + 4, 1, 4, SENSOR)
    s.block(ox + 5, 1, 4, wire(0, east="side", west="side"))
    s.block(ox + 6, 1, 4, "redstone_lamp[lit=false]")
    s.block(ox + 2, 1, 4, LEVER_OFF)
    s.use(2, ox + 2, 1, 4)
    s.setblock(12, ox + 4, 1, 4, "air")
    s.probes.update({"g1_sensor": (ox + 4, 1, 4), "g1_dust": (ox + 5, 1, 4), "g1_lamp": (ox + 6, 1, 4)})
    # group 2: replaced by a calibrated sensor in cooldown
    ox = 40
    s.block(ox + 4, 1, 4, SENSOR)
    s.block(ox + 2, 1, 4, LEVER_OFF)
    s.setblock(2, ox + 4, 1, 4,
               "calibrated_sculk_sensor[facing=east,power=0,sculk_sensor_phase=cooldown,waterlogged=false]")
    s.use(10, ox + 2, 1, 4)
    s.probes.update({"g2_sensor": (ox + 4, 1, 4)})
    # group 3: active sensor replaced by an inactive one
    ox = 60
    s.block(ox + 4, 1, 4, SENSOR)
    s.block(ox + 5, 1, 4, wire(0, east="side", west="side"))
    s.block(ox + 6, 1, 4, "redstone_lamp[lit=false]")
    s.block(ox + 2, 1, 4, LEVER_OFF)
    s.use(2, ox + 2, 1, 4)
    s.setblock(12, ox + 4, 1, 4, SENSOR)
    s.use(20, ox + 2, 1, 4)
    s.probes.update({"g3_sensor": (ox + 4, 1, 4), "g3_dust": (ox + 5, 1, 4), "g3_lamp": (ox + 6, 1, 4)})
    # group 4: built (no onPlace) active with power 7, no scheduled tick
    ox = 80
    s.block(ox + 4, 1, 4, active)
    s.block(ox + 5, 1, 4, wire(0, east="side", west="side"))
    s.block(ox + 6, 1, 4, "redstone_lamp[lit=false]")
    s.probes.update({"g4_sensor": (ox + 4, 1, 4), "g4_dust": (ox + 5, 1, 4), "g4_lamp": (ox + 6, 1, 4)})
    s.write(40)


def signal_up() -> None:
    s = Scenario(
        "sculk-signal-up",
        """
        Direktes Signal: getDirectSignal des Sensors gilt nur fuer Direction.UP, also fuer den Block UNTER dem Sensor
        (der Block fragt seinen oberen Nachbarn). Gruppen 0-2: Stein unter dem Sensor, Hebel in Abstand 1, 3 und 6
        (Staerke 14, 11 und 4 bei Radius 8); Staub auf dem Boden neben dem Stein und eine Lampe daneben zeigen das
        Signal. Gleichzeitig steht ein Stein ueber dem Sensor mit Staub und Lampe: der bekommt nichts.
        Gruppe 3: Glas unter dem Sensor leitet nichts. Gruppe 4: Staub direkt neben dem Sensor bekommt das schwache
        Signal (alle Gruppen, Probe dust_side).
        """,
        (100, 6, 10),
    )
    s.fills.append((0, 0, 0, 99, 0, 9, "stone"))
    for g, dist, below in ((0, 1, "stone"), (1, 3, "stone"), (2, 6, "stone"), (3, 1, "glass")):
        ox = 20 * g
        sx = ox + 8
        s.block(sx, 2, 4, SENSOR)
        s.block(sx - dist, 1, 4, "stone")
        s.block(sx - dist, 2, 4, LEVER_OFF)
        s.block(sx, 1, 4, below)
        s.block(sx + 1, 1, 4, wire(0, east="none", west="side"))
        s.block(sx, 1, 3, "redstone_lamp[lit=false]")
        s.block(sx, 3, 4, "stone")  # above the sensor: gets nothing
        s.block(sx + 1, 2, 4, "stone")
        s.block(sx + 1, 3, 4, wire(0, east="none", west="side"))
        s.block(sx, 3, 3, "redstone_lamp[lit=false]")
        s.block(sx, 2, 5, wire(0, east="none", west="none"))  # dust beside the sensor (weak signal)
        s.block(sx, 1, 5, "stone")
        s.use(2, sx - dist, 2, 4)
        s.probes.update({f"g{g}_sensor": (sx, 2, 4), f"g{g}_dust_below": (sx + 1, 1, 4),
                         f"g{g}_lamp_below": (sx, 1, 3), f"g{g}_dust_above": (sx + 1, 3, 4),
                         f"g{g}_lamp_above": (sx, 3, 3), f"g{g}_dust_side": (sx, 2, 5)})
    s.write(60)


if __name__ == "__main__":
    wool()
    simultaneous()
    calibrated()
    resonance()
    placement()
    signal_up()
