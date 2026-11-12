"""Generate the kb3-* knowledge-verification scenarios (scenarios/kb3-*.yaml).

Usage: uv run python scripts/gen_kb3_scenarios.py
"""

from __future__ import annotations

from pathlib import Path

import yaml

OUT = Path(__file__).resolve().parent.parent / "scenarios"

DETECTOR = "repeater[delay=1,facing=north,locked=false,powered=true]"
LEVER_F = "lever[face=floor,facing=east,powered=false]"


class Sc:
    def __init__(self, name: str, size, description: str, ticks: int):
        self.d = {"name": name, "description": description,
                  "build": {"size": list(size), "fill": [], "blocks": []},
                  "ticks": ticks, "inputs": [], "probes": {}}

    def fill(self, x1, y1, z1, x2, y2, z2, state):
        self.d["build"]["fill"].append([x1, y1, z1, x2, y2, z2, state])

    def block(self, x, y, z, state):
        self.d["build"]["blocks"].append([x, y, z, state])

    def inp(self, tick, pos, action, state=None):
        e = {"tick": tick, "pos": list(pos), "action": action}
        if state:
            e["state"] = state
        self.d["inputs"].append(e)

    def probe(self, name, pos):
        self.d["probes"][name] = list(pos)

    def save(self):
        text = yaml.dump(self.d, sort_keys=False, allow_unicode=True, width=110, default_flow_style=None)
        (OUT / f"{self.d['name']}.yaml").write_text(text, encoding="utf-8")


def torch_burnout():
    """TRCH-010: entries older than 60 gt are dropped, an entry of exactly 60 gt still counts."""
    desc = ("Fackel-Burnout und das 60-gt-Fenster. Ein Hebel an der Seite des Blocks unter einer Fackel schaltet die "
            "Fackel 7-mal im Abstand von 8 gt aus (Eintraege bei 4, 12, ..., 52). Der 8. Hebelimpuls kommt in jeder "
            "Bahn zu einer anderen Zeit, sodass der erste Eintrag (4) beim 8. Ausschalten 58 bis 63 gt alt ist. Bis "
            "genau 60 gt zaehlt er mit (Burnout, die Fackel bleibt aus), ab 61 wird er vorher entfernt "
            "(kein Burnout, die Fackel geht nach dem Hebel wieder an).")
    ds = [58, 59, 60, 61, 62, 63]
    sc = Sc("kb3-torch-burnout", (3, 3, 4 * len(ds)), desc, 90)
    sc.fill(0, 0, 0, 2, 0, 4 * len(ds) - 1, "stone")
    for i, d in enumerate(ds):
        z = 4 * i
        sc.block(0, 1, z, "stone")
        sc.block(0, 2, z, "redstone_torch[lit=true]")
        sc.block(1, 1, z, "lever[face=wall,facing=east,powered=false]")
        sc.probe(f"torch-d{d}", (0, 2, z))
        for k in range(7):
            sc.inp(2 + 8 * k, (1, 1, z), "use")
            sc.inp(6 + 8 * k, (1, 1, z), "use")
        sc.inp(2 + d, (1, 1, z), "use")
        sc.inp(6 + d, (1, 1, z), "use")
    sc.save()


def diode_side_inputs():
    """PWR-014: side inputs of repeaters (diodes only) and comparators (any source)."""
    desc = ("Seiteneingaenge von Dioden. Jede Bahn hat ein Ziel (Repeater bzw. Comparator im Subtraktionsmodus) mit "
            "Hebel dahinter und einer Quelle an der Nordseite. Quelle: Redstone-Block (RB), Hebel (LEV), Staub "
            "(DUST), gespeister Repeater (DIODE), von einem Hebel angetriebener Stein (STONE). Bei 2 wird die "
            "Quelle aktiviert, bei 6 der Hebel hinter dem Ziel. Repeater sperren nur bei DIODE (powered bleibt "
            "aus), Redstone-Block, Staub, Hebel und Stein sperren nicht. Comparatoren ziehen die Seitenstaerke ab bei "
            "RB, DUST und DIODE (Ausgang 0), nicht bei STONE (nur schwach geladen) und nicht bei LEV (ein "
            "Bodenhebel gibt nur dem Block unter sich starkes Signal).")
    kinds_r = ["rb", "lev", "dust", "diode", "stone"]
    kinds_c = ["rb", "lev", "dust", "diode", "stone", "none"]
    lane_h = 6
    n = len(kinds_r) + len(kinds_c)
    sc = Sc("kb3-diode-side-inputs", (4, 3, lane_h * n), desc, 14)
    sc.fill(0, 0, 0, 3, 0, lane_h * n - 1, "stone")

    def lane(i, kind, dev):
        z0 = lane_h * i + 3  # device row
        tag = f"{dev}-{kind}"
        # rear lever west of the device; device reads west
        sc.block(0, 1, z0, LEVER_F)
        if dev == "r":
            sc.block(1, 1, z0, "repeater[delay=1,facing=west,locked=false,powered=false]")
        else:
            sc.block(1, 1, z0, "comparator[facing=west,mode=subtract,powered=false]")
        sc.inp(6, (0, 1, z0), "use")
        sc.probe(tag, (1, 1, z0))
        n1 = (1, 1, z0 - 1)
        if kind == "rb":
            sc.inp(2, n1, "setblock", "redstone_block")
        elif kind == "lev":
            sc.block(*n1, LEVER_F)
            sc.inp(2, n1, "use")
        elif kind == "dust":
            sc.block(*n1, "redstone_wire[east=none,north=none,power=0,south=none,west=none]")
            sc.block(1, 1, z0 - 2, LEVER_F)
            sc.inp(2, (1, 1, z0 - 2), "use")
        elif kind == "diode":
            sc.block(*n1, "repeater[delay=1,facing=north,locked=false,powered=true]")
            sc.inp(2, (1, 1, z0 - 2), "setblock", "redstone_block")
        elif kind == "stone":
            sc.block(*n1, "stone")
            sc.block(1, 1, z0 - 2, "lever[face=wall,facing=north,powered=false]")
            sc.inp(2, (1, 1, z0 - 2), "use")

    i = 0
    for k in kinds_r:
        lane(i, k, "r")
        i += 1
    for k in kinds_c:
        lane(i, k, "c")
        i += 1
    sc.save()


def signal_dirs():
    """PWR-012, SIG-002: lamps next to sources in all six directions, torches by direction."""
    desc = ("Lampen neben Signalquellen. Zeile z=1: ein Redstone-Block (bei 2 gesetzt) auf je einer der sechs Seiten "
            "einer Lampe, alle sechs Lampen gehen an (hasNeighborSignal prueft alle Richtungen). Zeile z=5: "
            "Bodenfackeln (bei 2 gesetzt): neben der Lampe und unter der Lampe speisen sie, eine Fackel auf der Lampe "
            "nicht (die Lampe fragt die Fackel mit Richtung UP, SIG-002).")
    sc = Sc("kb3-signal-dirs", (28, 5, 9), desc, 8)
    sc.fill(0, 0, 0, 27, 0, 8, "stone")
    dirs = {"down": (0, -1, 0), "up": (0, 1, 0), "north": (0, 0, -1), "south": (0, 0, 1), "west": (-1, 0, 0),
            "east": (1, 0, 0)}
    for i, (nm, (dx, dy, dz)) in enumerate(dirs.items()):
        x, y, z = 3 + 4 * i, 2, 2
        sc.block(x, y, z, "redstone_lamp[lit=false]")
        sc.inp(2, (x + dx, y + dy, z + dz), "setblock", "redstone_block")
        sc.probe(f"lamp-{nm}", (x, y, z))
    # torches
    x = 3
    sc.block(x, 1, 6, "redstone_lamp[lit=false]")
    sc.inp(2, (x + 1, 1, 6), "setblock", "redstone_torch[lit=true]")
    sc.probe("lamp-torch-side", (x, 1, 6))
    x = 7
    sc.block(x, 2, 6, "redstone_lamp[lit=false]")
    sc.inp(2, (x, 1, 6), "setblock", "redstone_torch[lit=true]")
    sc.probe("lamp-torch-below", (x, 2, 6))
    x = 11
    sc.block(x, 1, 6, "redstone_lamp[lit=false]")
    sc.inp(2, (x, 2, 6), "setblock", "redstone_torch[lit=true]")
    sc.probe("lamp-torch-above", (x, 1, 6))
    sc.probe("torch-above", (x, 2, 6))
    sc.save()


def signal_range():
    """SIG-001: dust strength 15 down to 0 along a line."""
    desc = "Signalstaerke 0 bis 15: Ein Hebel speist eine Staubleitung; der erste Staub hat 15, der 16. hat 0."
    sc = Sc("kb3-signal-range", (19, 2, 1), desc, 6)
    sc.fill(0, 0, 0, 18, 0, 0, "stone")
    sc.block(0, 1, 0, LEVER_F)
    for i in range(17):
        sc.block(1 + i, 1, 0, "redstone_wire[east=side,north=none,power=0,south=none,west=side]")
        sc.probe(f"dust{i}", (1 + i, 1, 0))
    sc.inp(2, (0, 1, 0), "use")
    sc.save()


def bud_reach():
    """BUD-001: which neighbors get an update when a block changes."""
    desc = ("Reichweite von Block-Updates. In jeder Zelle wird ein Stein bei 2 durch Bruchstein ersetzt (Flag 3) und "
            "genau ein Detektor (Repeater powered=true ohne Eingang schaltet bei jedem Neighbor-Update aus) steht "
            "an einer anderen Stelle: die vier Seiten und der Block darueber gehen bei 4 aus; Diagonale und "
            "Abstand 2 bzw. 3 bleiben an.")
    spots = {"east": (1, 0, 0), "west": (-1, 0, 0), "north": (0, 0, -1), "south": (0, 0, 1), "up": (0, 1, 0),
             "diag": (1, 0, 1), "diag-up": (1, 1, 0), "far-east": (2, 0, 0), "far-south": (0, 0, 3)}
    sc = Sc("kb3-bud-reach", (7, 4, 6 * len(spots)), desc, 8)
    sc.fill(0, 0, 0, 6, 0, 6 * len(spots) - 1, "stone")
    for i, (nm, (dx, dy, dz)) in enumerate(spots.items()):
        cx, cz = 3, 6 * i + 2
        sc.block(cx, 1, cz, "stone")
        sc.inp(2, (cx, 1, cz), "setblock", "cobblestone")
        p = (cx + dx, 1 + dy, cz + dz)
        sc.block(*p, DETECTOR)
        sc.probe(nm, p)
        if dy == 1 and dx == 1:  # diagonal above needs a support block beside the stone
            sc.block(cx + 1, 1, cz, "stone")
    sc.save()


def dust_toggle():
    """DUST-009: toggling dot/cross updates conductors next to changed connections."""
    desc = ("Staub umschalten. Staub ohne Verbindung (Punkt) wird bei 2 per Rechtsklick zum Kreuz, Kreuz zum Punkt. "
            "Detektoren hinter einem Stein neben dem Staub (Leiter) gehen aus, hinter Glas (kein Leiter) nicht. "
            "Zeilen z=1 (Punkt->Kreuz) und z=6 (Kreuz->Punkt).")
    sc = Sc("kb3-dust-toggle", (9, 3, 11), desc, 8)
    sc.fill(0, 0, 0, 8, 0, 10, "stone")
    dot = "redstone_wire[east=none,north=none,power=0,south=none,west=none]"
    cross = "redstone_wire[east=side,north=side,power=0,south=side,west=side]"
    for tag, z, st in (("dot", 2, dot), ("cross", 7, cross)):
        sc.block(4, 1, z, st)
        sc.block(5, 1, z, "stone")   # conductor east
        sc.block(6, 1, z, DETECTOR)
        sc.block(3, 1, z, "glass")   # non-conductor west
        sc.block(2, 1, z, DETECTOR)
        sc.inp(2, (4, 1, z), "use")
        sc.probe(f"{tag}-dust", (4, 1, z))
        sc.probe(f"{tag}-det-stone", (6, 1, z))
        sc.probe(f"{tag}-det-glass", (2, 1, z))
    sc.save()


def shape_update():
    """UPD-009: shape update destroys / reshapes the receiver."""
    desc = ("Shape-Updates. z=1: Der Stein unter einem Repeater wird bei 2 entfernt, der Repeater wird zerstoert "
            "(updateShape liefert Luft) und aktualisiert die Nachbarn (Detektor daneben geht aus). z=5: zwei "
            "Staubstuecke verbinden sich, wenn das zweite bei 2 gesetzt wird (setBlock mit neuem Zustand). "
            "z=8: ein Detektor ohne Bezug bleibt an.")
    sc = Sc("kb3-shape-update", (6, 3, 10), desc, 8)
    sc.fill(0, 0, 0, 5, 0, 9, "stone")
    sc.block(1, 0, 1, "stone")
    sc.block(1, 1, 1, "repeater[delay=1,facing=north,locked=false,powered=false]")
    sc.block(2, 1, 1, DETECTOR)
    sc.inp(2, (1, 0, 1), "setblock", "air")
    sc.probe("rep", (1, 1, 1))
    sc.probe("rep-neighbor-det", (2, 1, 1))
    sc.block(1, 1, 5, "redstone_wire[east=none,north=none,power=0,south=none,west=none]")
    sc.inp(2, (2, 1, 5), "setblock", "redstone_wire[east=none,north=none,power=0,south=none,west=none]")
    sc.probe("dust1", (1, 1, 5))
    sc.probe("dust2", (2, 1, 5))
    sc.block(4, 1, 8, DETECTOR)
    sc.probe("control-det", (4, 1, 8))
    sc.save()


def diode_tick():
    """REP-008: neighbor update schedules a tick only if state and input differ."""
    desc = ("Repeater-Zustand gegen Eingang. Ein Stein neben jedem Repeater wird bei 2 ersetzt (Neighbor-Update). "
            "a: an, Eingang an (Redstone-Block dahinter): bleibt an. b: an, kein Eingang: aus bei 4. c: aus, "
            "Eingang an: an bei 4. d: aus, kein Eingang: bleibt aus. e: gesperrt (Seiten-Repeater), aus, Eingang an: "
            "bleibt aus.")
    sc = Sc("kb3-diode-tick", (4, 3, 30), desc, 10)
    sc.fill(0, 0, 0, 3, 0, 29, "stone")
    cases = {"a": (True, True), "b": (True, False), "c": (False, True), "d": (False, False)}
    for i, (nm, (pw, inp)) in enumerate(cases.items()):
        z = 3 + 5 * i
        sc.block(2, 1, z, f"repeater[delay=1,facing=north,locked=false,powered={str(pw).lower()}]")
        if inp:
            sc.block(2, 1, z - 1, "redstone_block")
        sc.block(3, 1, z, "stone")
        sc.inp(2, (3, 1, z), "setblock", "cobblestone")
        sc.probe(nm, (2, 1, z))
    z = 3 + 5 * 4
    sc.block(2, 1, z, "repeater[delay=1,facing=north,locked=true,powered=false]")
    sc.block(2, 1, z - 1, "redstone_block")
    sc.block(1, 1, z, "repeater[delay=1,facing=west,locked=false,powered=true]")
    sc.block(0, 1, z, "redstone_block")
    sc.block(3, 1, z, "stone")
    sc.inp(2, (3, 1, z), "setblock", "cobblestone")
    sc.probe("e", (2, 1, z))
    sc.probe("e-side", (1, 1, z))
    sc.save()


def piston_retract():
    """PIS-017: retracting piston updates neighbors immediately."""
    desc = ("Einfahrender Kolben. Ein Hebel faehrt den Kolben bei 2 aus. Bei 10 werden zwei Detektoren gesetzt (Repeater "
            "powered=true ohne Eingang, einer neben der Kolbenbasis, ein Kontroll-Detektor weit weg). Bei 14 "
            "faehrt der Kolben wieder ein; der Detektor neben der Basis geht nur durch das Update der Basis aus. "
            "Der Zeitpunkt zeigt, ob die Basis ihre Nachbarn sofort (beim Einfahr-Event) aktualisiert (PIS-017).")
    sc = Sc("kb3-piston-retract", (5, 3, 5), desc, 26)
    sc.fill(0, 0, 0, 4, 0, 4, "stone")
    sc.block(0, 1, 2, LEVER_F)
    sc.block(1, 1, 2, "piston[extended=false,facing=east]")
    sc.inp(2, (0, 1, 2), "use")
    sc.inp(10, (1, 1, 1), "setblock", "repeater[delay=1,facing=south,locked=false,powered=true]")
    sc.inp(10, (3, 1, 4), "setblock", "repeater[delay=1,facing=north,locked=false,powered=true]")
    sc.inp(14, (0, 1, 2), "use")
    sc.probe("lever", (0, 1, 2))
    sc.probe("piston", (1, 1, 2))
    sc.probe("head", (2, 1, 2))
    sc.probe("det-base", (1, 1, 1))
    sc.probe("det-control", (3, 1, 4))
    sc.save()


if __name__ == "__main__":
    torch_burnout()
    diode_side_inputs()
    signal_dirs()
    signal_range()
    bud_reach()
    dust_toggle()
    shape_update()
    diode_tick()
    piston_retract()
