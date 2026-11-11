"""Specification of a combinational circuit: a truth table plus timing limits.

A spec comes from the analysis of an existing circuit (`from_analysis`) or from a YAML file:

    inputs: [a, b]
    outputs: [y]
    function:            # Python boolean expressions over the inputs ...
      y: a and not b
    table:               # ... or an explicit table "inputs -> outputs" (bits in the order above)
      "00": "0"
      "10": "1"
    max_delay: 6         # optional, game ticks from the input change to the last output change
    others: dont_care    # optional with `table`: combinations missing from the table do not matter

Only combinational behaviour is described for now (outputs depend only on the current inputs).
"""

from __future__ import annotations

import ast
import itertools
from dataclasses import dataclass, field
from pathlib import Path

import yaml

Combo = tuple[bool, ...]

_ALLOWED_NODES = (ast.Expression, ast.BoolOp, ast.UnaryOp, ast.BinOp, ast.Compare, ast.Name, ast.Load,
                  ast.And, ast.Or, ast.Not, ast.BitXor, ast.BitAnd, ast.BitOr, ast.Eq, ast.NotEq,
                  ast.Constant, ast.Add, ast.Sub, ast.Mod, ast.Gt, ast.GtE, ast.Lt, ast.LtE)  # arithmetic on bools: (a + b + c) % 2


@dataclass
class Spec:
    inputs: list[str]
    outputs: list[str]
    table: dict[Combo, Combo]  # input combination -> output states (every combination, or exactly `care`)
    max_delay: int | None = None
    source: str = ""  # where the spec came from, German
    notes: list[str] = field(default_factory=list)
    care: frozenset[Combo] | None = None  # the combinations that matter (None: all); the others are "egal"

    def __post_init__(self) -> None:
        if self.care is None:
            want = set(itertools.product([False, True], repeat=len(self.inputs)))
            if set(self.table) != want:
                raise ValueError(f"truth table must cover all {len(want)} input combinations")
        else:
            self.care = frozenset(self.care)
            if set(self.table) != set(self.care):
                raise ValueError("a partial truth table must list exactly the combinations that matter")
        if any(len(v) != len(self.outputs) for v in self.table.values()):
            raise ValueError("every table row needs one value per output")

    @property
    def partial(self) -> bool:
        return self.care is not None

    def combos(self) -> list[Combo]:
        """The combinations that matter, in itertools.product order."""
        if self.care is None:
            return list(itertools.product([False, True], repeat=len(self.inputs)))
        return sorted(self.care)  # False < True: same order as itertools.product

    def output_column(self, i: int) -> tuple[bool, ...]:
        """Values of output i for all combinations that matter, in itertools.product order."""
        return tuple(self.table[c][i] for c in self.combos())

    def describe(self) -> str:
        """German one-line summary per output, e.g. 'y = AND(a, b)'."""
        if self.partial:
            return self._describe_partial()
        lines = []
        for i, name in enumerate(self.outputs):
            ones = [c for c in itertools.product([False, True], repeat=len(self.inputs)) if self.table[c][i]]
            if not ones:
                lines.append(f"{name} = immer aus")
            elif len(ones) == 2 ** len(self.inputs):
                lines.append(f"{name} = immer an")
            else:
                terms = [" ∧ ".join(n if b else f"¬{n}" for n, b in zip(self.inputs, c)) for c in ones]
                lines.append(f"{name} = " + " ∨ ".join(f"({t})" if len(self.inputs) > 1 else t for t in terms))
        return "; ".join(lines)

    def _describe_partial(self) -> str:
        def side(names: list[str], bits: tuple[bool, ...], none: str, every: str) -> str:
            on = [n for n, b in zip(names, bits) if b]
            off = [n for n, b in zip(names, bits) if not b]
            if not on:
                return none
            if not off:
                return every
            return "+".join(on) if len(on) <= len(off) else f"alle außer {'+'.join(off)}"

        rows = [f"{side(self.inputs, c, 'alle aus', 'alle an')} → {side(self.outputs, self.table[c], '–', 'alle')}"
                for c in self.combos()]
        return (f"Teiltabelle ({len(rows)} von {2 ** len(self.inputs)} Kombinationen, die übrigen egal): "
                + "; ".join(rows))

    def to_dict(self) -> dict:
        d: dict = {"inputs": self.inputs, "outputs": self.outputs,
                   "table": {_bits(c): _bits(o) for c, o in sorted(self.table.items())}}
        if self.partial:
            d["others"] = "dont_care"
        if self.max_delay is not None:
            d["max_delay"] = self.max_delay
        return d


def _bits(c: Combo) -> str:
    return "".join("1" if b else "0" for b in c)


def _parse_bits(s: str | int, n: int) -> Combo:
    s = str(s).zfill(n)
    if len(s) != n or set(s) - {"0", "1"}:
        raise ValueError(f"expected {n} bits, got {s!r}")
    return tuple(ch == "1" for ch in s)


def evaluate_expression(expr: str, env: dict[str, bool]) -> bool:
    """Evaluate a boolean expression ('a and not b', 'a ^ b', 'a != b') without eval of arbitrary code."""
    tree = ast.parse(expr, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"not allowed in a spec expression: {type(node).__name__} in {expr!r}")
        if isinstance(node, ast.Name) and node.id not in env:
            raise ValueError(f"unknown input {node.id!r} in {expr!r}")
    return bool(eval(compile(tree, "<spec>", "eval"), {"__builtins__": {}}, dict(env)))  # noqa: S307


def from_functions(inputs: list[str], functions: dict[str, str], max_delay: int | None = None,
                   source: str = "") -> Spec:
    outputs = list(functions)
    table = {}
    for combo in itertools.product([False, True], repeat=len(inputs)):
        env = dict(zip(inputs, combo))
        table[combo] = tuple(evaluate_expression(functions[o], env) for o in outputs)
    return Spec(inputs, outputs, table, max_delay, source)


def from_dict(d: dict, source: str = "") -> Spec:
    inputs = [str(x) for x in d["inputs"]]
    max_delay = d.get("max_delay")
    if "function" in d:
        return from_functions(inputs, {str(k): str(v) for k, v in d["function"].items()}, max_delay, source)
    outputs = [str(x) for x in d["outputs"]]
    table = {_parse_bits(k, len(inputs)): _parse_bits(v, len(outputs)) for k, v in d["table"].items()}
    others = d.get("others")
    if others not in (None, "dont_care"):
        raise ValueError(f"others: {others!r} (only 'dont_care' is supported)")
    care = frozenset(table) if others == "dont_care" else None
    return Spec(inputs, outputs, table, max_delay, source, care=care)


def load(path: str | Path) -> Spec:
    path = Path(path)
    return from_dict(yaml.safe_load(path.read_text(encoding="utf-8")), source=path.name)


def from_analysis(analysis, title: str = "") -> Spec:
    """Spec of an analysed circuit: its lever truth table, or for one lever the steady reaction.

    The delay limit is the slowest output change the original shows, so a redesign is never slower."""
    from ..analysis.analyze import Analysis

    a: Analysis = analysis
    levers = [p for p in a.inputs if p.kind == "lever"]
    if not levers or not a.outputs:
        raise ValueError("Die Schaltung hat keine Hebel-Eingänge oder keine Ausgänge; keine Spezifikation möglich")
    if a.oscillates:
        raise ValueError("Die Schaltung schwingt ohne Eingabe; nur kombinatorische Schaltungen werden unterstützt")
    names_in = [p.name for p in levers]
    names_out = [o.name for o in a.outputs]
    if a.truth_table:
        table = {combo: outs for combo, outs in a.truth_table}
    elif len(levers) == 1 and a.responses:
        r = a.responses[0]
        table = {(False,): tuple(x.steady_after[1] for x in r.reactions),
                 (True,): tuple(x.steady_after[0] for x in r.reactions)}
    else:
        raise ValueError("Keine vollständige Wahrheitstabelle vorhanden (zu viele Hebel?)")
    delays = [d for r in a.responses for x in r.reactions for d in x.delays if d is not None]
    spec = Spec(names_in, names_out, table, max(delays) if delays else None,
                source=f"Analyse von {title}" if title else "Analyse")
    constant = [n for i, n in enumerate(names_out) if len(set(spec.output_column(i))) == 1]
    if constant:
        spec.notes.append("Ausgänge ohne Abhängigkeit von den Hebeln: " + ", ".join(constant))
    return spec
