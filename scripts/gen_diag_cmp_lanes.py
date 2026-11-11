"""Generate diag-cmp-lanes*.yaml: many closely spaced comparator lanes (M2 diagnosis)."""
import json
from pathlib import Path


def W(p):
    return f"redstone_wire[east=none,north=none,power={p},south=none,west=none]"


OUT = Path(__file__).resolve().parent.parent / "scenarios"


def gen(name, desc, lanes, spacing, between, mode_use, stored, late_dust, tail, ticks=24):
    blocks, bes, inputs, probes = [], [], [], {}
    zmax = (lanes - 1) * spacing + 1
    fill = [[0, 0, 0, 5, 0, zmax, "stone"]]
    for i in range(lanes):
        z = i * spacing
        out = (i % 15) + 1 if stored else 0
        powered = "true" if stored and i % 2 else "false"
        if not late_dust:
            blocks.append([0, 1, z, W(7)])
        else:
            inputs.append({"tick": 2, "pos": [0, 1, z], "action": "setblock", "state": W(7)})
        mode = "subtract" if (i % 3 == 2 and mode_use == "mixed") else "compare"
        blocks.append([1, 1, z, f"comparator[facing=west,mode={mode},powered={powered}]"])
        bes.append([1, 1, z, f'{{id:"minecraft:comparator",OutputSignal:{out}}}'])
        if tail == "stone-rep":
            blocks += [[2, 1, z, "stone"], [3, 1, z, "repeater[delay=1,facing=west,locked=false,powered=false]"],
                       [4, 1, z, "redstone_lamp[lit=false]"]]
            probes[f"l{i}_rep"] = [3, 1, z]
        elif tail == "dust":
            blocks.append([2, 1, z, W(0)])
            probes[f"l{i}_dust"] = [2, 1, z]
        probes[f"l{i}_cmp"] = [1, 1, z]
        if mode_use in ("use", "mixed") and (mode_use == "use" or i % 2 == 0):
            inputs.append({"tick": 2, "pos": [1, 1, z], "action": "use"})
        if between and i < lanes - 1:
            for dz in range(1, spacing):
                blocks.append([0, 1, z + dz, W(0)])
    return {"name": name, "description": desc, "build": {"size": [6, 3, zmax + 1], "fill": fill,
            "blocks": blocks, "block_entities": bes}, "ticks": ticks, "inputs": inputs, "probes": probes}


def inline(d):
    return "{" + ", ".join(f"{k}: {json.dumps(v)}" for k, v in d.items()) + "}"


def dump(d):
    L = [f"name: {d['name']}", "description: >", f"  {d['description']}", "build:",
         f"  size: {json.dumps(d['build']['size'])}", "  fill:"]
    L += [f"    - {json.dumps(f)}" for f in d["build"]["fill"]]
    L.append("  blocks:")
    L += [f"    - {json.dumps(b)}" for b in d["build"]["blocks"]]
    L.append("  block_entities:")
    L += [f"    - [{b[0]}, {b[1]}, {b[2]}, '{b[3]}']" for b in d["build"]["block_entities"]]
    L.append(f"ticks: {d['ticks']}")
    L.append("inputs:")
    L += [f"  - {inline(i)}" for i in d["inputs"]]
    L.append("probes:")
    L += [f"  {k}: {json.dumps(v)}" for k, v in d["probes"].items()]
    return "\n".join(L) + "\n"


V = [
    ("diag-cmp-lanes1", "36 Lanes Abstand 2, Staub dazwischen, use bei Tick 2, Stein+Repeater.", 36, 2, True, "use", False, False, "stone-rep"),
    ("diag-cmp-lanes2", "36 Lanes Abstand 2, Staub dazwischen, gespeicherte Ausgaenge, Staub bei Tick 2 gesetzt, use.", 36, 2, True, "use", True, True, "stone-rep"),
    ("diag-cmp-lanes3", "36 Lanes Abstand 2, ohne Staub dazwischen, gemischt use/subtract, Staub bei Tick 2.", 36, 2, False, "mixed", True, True, "stone-rep"),
    ("diag-cmp-lanes4", "36 Lanes Abstand 3, Staub dazwischen, Comparator zu Staub, gespeichert, use.", 36, 3, True, "use", True, False, "dust"),
    ("diag-cmp-lanes5", "20 Lanes Abstand 1 (dicht), use, Staub bei Tick 2, Stein+Repeater.", 20, 1, False, "use", False, True, "stone-rep"),
]
def gen_random(name, seed, lanes=36, spacing=2):
    """Per-lane random mix of mode, use, stored output, late dust, tail, dust between lanes."""
    import random
    r = random.Random(seed)
    blocks, bes, inputs, probes = [], [], [], {}
    zmax = (lanes - 1) * spacing + 1
    for i in range(lanes):
        z = i * spacing
        if r.random() < 0.5:
            blocks.append([0, 1, z, W(r.choice([3, 7, 15]))])
        else:
            inputs.append({"tick": r.choice([1, 2, 3]), "pos": [0, 1, z], "action": "setblock", "state": W(r.choice([5, 7, 12]))})
        out = r.choice([0, 0, r.randint(1, 15)])
        mode = r.choice(["compare", "subtract"])
        blocks.append([1, 1, z, f"comparator[facing=west,mode={mode},powered={r.choice(['true', 'false'])}]"])
        bes.append([1, 1, z, f'{{id:"minecraft:comparator",OutputSignal:{out}}}'])
        tail = r.choice(["stone-rep", "dust", "stone-rep"])
        if tail == "stone-rep":
            blocks += [[2, 1, z, "stone"], [3, 1, z, f"repeater[delay={r.randint(1, 4)},facing=west,locked=false,powered=false]"],
                       [4, 1, z, "redstone_lamp[lit=false]"]]
            probes[f"l{i}_rep"] = [3, 1, z]
        else:
            blocks.append([2, 1, z, W(0)])
            probes[f"l{i}_dust"] = [2, 1, z]
        probes[f"l{i}_cmp"] = [1, 1, z]
        if r.random() < 0.6:
            inputs.append({"tick": r.choice([1, 2, 3, 6]), "pos": [1, 1, z], "action": "use"})
        if r.random() < 0.7 and i < lanes - 1:
            blocks.append([0, 1, z + 1, W(0)])
    inputs.sort(key=lambda d: d["tick"])
    return {"name": name, "description": f"Zufallsmix je Lane (Seed {seed}): Modus, use, gespeicherter Ausgang, Staub, Schwanz.",
            "build": {"size": [6, 3, zmax + 1], "fill": [[0, 0, 0, 5, 0, zmax, "stone"]], "blocks": blocks, "block_entities": bes},
            "ticks": 30, "inputs": inputs, "probes": probes}


if __name__ == "__main__":
    for n, seed in (("diag-cmp-lanes-rnd1", 1), ("diag-cmp-lanes-rnd2", 2), ("diag-cmp-lanes-rnd3", 3)):
        (OUT / f"{n}.yaml").write_text(dump(gen_random(n, seed)), encoding="utf-8")
    for v in V:
        (OUT / f"{v[0]}.yaml").write_text(dump(gen(*v)), encoding="utf-8")
