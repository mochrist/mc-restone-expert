"""Run the GUI assistant with the real API on plain-language requests and write a report (costs API credit).

    uv run python scripts/assistant_eval.py [--only N,M] [--out report.md]

Each case: the request, what we expect (spec kind, honesty), the tool calls Claude made, the search results and
the final answer. Checks are rough (keywords in the spec / answer); read the report."""

from __future__ import annotations

import argparse
import json
import threading
import time
import urllib.request
from pathlib import Path

from redstone.gui.server import make_server

CASES = [
    # (name, request, expected spec substrings (any of each group), expectation for the answer)
    ("codeschloss", "Ich möchte eine Eisentür, die nur aufgeht, wenn von vier Hebeln genau der erste und der dritte an sind.",
     [["function", "table"], ["iron_door"]], "Logik 4 Eingänge, Ausgang Eisentür"),
    ("tuerklingel", "Eine Türklingel: Wenn man einen Knopf drückt, soll ein Notenblock einen Ton spielen.",
     [["monostable", "behaviour"], ["note_block"]], "Monoflop mit Knopf, Notenblock"),
    ("alarmanlage", "Eine Alarmanlage: Ein Knopf löst den Alarm aus, eine Lampe bleibt an, bis man einen zweiten Knopf "
                    "zum Zurücksetzen drückt.", [["rs-latch"]], "RS-Latch"),
    ("leuchtturm", "Ein Leuchtturm: Eine Lampe soll von selbst blinken, etwa jede Sekunde kurz aufleuchten.",
     [["clock"]], "Takt, Periode 20 oder 24"),
    ("treppenlicht", "Treppenhauslicht: Ich drücke unten einen Knopf und die Lampe soll dann ungefähr zwei Sekunden "
                     "anbleiben.", [["pulse-extender", "monostable"]], "Pulsverlängerer/Monoflop 40 Ticks"),
    ("wechselschalter", "Ich will eine Lampe von zwei Stellen aus an- und ausschalten können, mit je einem Hebel, "
                        "wie ein Wechselschalter im Flur.", [["^", "!=", "xor", "table"]], "XOR"),
    ("mehrheit", "Drei Freunde stimmen mit Hebeln ab. Die Lampe soll angehen, wenn mindestens zwei dafür sind.",
     [["function", "table"]], "Mehrheit von 3"),
    ("kolben-toggle", "Ein Kolben soll mit einem Knopf ausfahren und beim nächsten Druck wieder einfahren.",
     [["t-flip-flop"], ["piston"]], "T-Flipflop mit Knopf, Kolben"),
    ("druckplatte", "Eine Tür, die aufgeht, wenn ich auf eine Druckplatte trete.",
     [["monostable", "pulse-extender"], ["pressure_plate"]],
     "Impuls (Monoflop/Pulsverlängerer) mit Druckplatte als input, Tür; Hinweis: nur im Simulator geprüft"),
    ("nachtlicht", "Eine Lampe an meinem Haus soll nachts von selbst angehen und morgens wieder aus.",
     [["function"], ["daylight_detector_inverted"]], "Tageslichtsensor invertiert als input, Lampe"),
    ("itemsortierer", "Bau mir einen Itemsortierer, der Diamanten aus meiner Truhe aussortiert.",
     [], "Katalog-Eintrag item-sorter geladen, Hinweis: Bruchstein im Filter durch 41 Diamanten ersetzen"),
    ("kolbentuer", "Ich hätte gern eine Kolbentür für den Eingang meiner Burg, zwei Blöcke breit und zwei hoch.",
     [], "Katalog-Eintrag piston-door-2x2 geladen, Bedienung mit Hebel"),
]
# cases answered from the catalog: the catalog key that load_example must load
LOADS = {"itemsortierer": "item-sorter", "kolbentuer": "piston-door-2x2"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default=".cache/assistant-eval/report.md")
    args = ap.parse_args()
    only = {s.strip() for s in args.only.split(",") if s.strip()}

    srv = make_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    state = srv.RequestHandlerClass.app_state

    def call(path, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                     data=None if body is None else json.dumps(body).encode(),
                                     method="GET" if body is None else "POST")
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Assistent mit echtem Schlüssel", ""]
    summary = []
    for name, text, groups, expect in CASES:
        if only and name not in only:
            continue
        t0 = time.monotonic()
        r = call("/api/chat", {"message": text, "current": None})
        cid = r["chat"]
        while True:
            snap = call(f"/api/chat/{cid}?since=0")
            if not snap["busy"]:
                break
            time.sleep(1)
        secs = time.monotonic() - t0
        chat = state.chats[cid]
        events = snap["events"]
        tools, specs = [], []
        for m in chat.messages:
            if m["role"] == "assistant":
                for b in m["content"]:
                    if getattr(b, "type", "") == "tool_use":
                        tools.append((b.name, dict(b.input or {})))
                        if b.name == "design_circuit":
                            specs.append(json.dumps(b.input, ensure_ascii=False))
        results = [c for m in chat.messages if m["role"] == "user" and isinstance(m["content"], list)
                   for c in m["content"] if isinstance(c, dict) and c.get("type") == "tool_result"]
        answer = "\n\n".join(e["text"] for e in events if e["type"] == "text")
        errors = [e["text"] for e in events if e["type"] == "error"]
        found = any(not c["is_error"] and "Gefunden:" in str(c["content"]) for c in results)
        spec_text = " ".join(specs).lower()
        if name in LOADS:
            loaded = [inp.get("path", "") for n, inp in tools if n == "load_example"]
            found = spec_ok = any(LOADS[name] in p for p in loaded)
        else:
            spec_ok = all(any(k.lower() in spec_text for k in g) for g in groups) if groups else not specs or found
        summary.append(f"| {name} | {'ja' if found else 'nein'} | {'ok' if spec_ok else 'PRÜFEN'} | "
                       f"{len(tools)} | {secs:.0f} s | {expect} |")
        lines += [f"## {name}", "", f"**Wunsch:** {text}", "", f"**Erwartung:** {expect}", "",
                  f"Dauer {secs:.0f} s, Werkzeuge: " + (", ".join(n for n, _ in tools) or "keine"), ""]
        for n, inp in tools:
            lines += [f"- `{n}`: ```{json.dumps(inp, ensure_ascii=False)}```"]
        for c in results:
            lines += ["", "<details><summary>Ergebnis " + ("(Fehler)" if c["is_error"] else "") + "</summary>", "",
                      "```", str(c["content"])[:1500], "```", "</details>"]
        lines += ["", "**Antwort:**", "", answer or "(keine)", ""]
        if errors:
            lines += ["**Fehler:** " + " / ".join(errors), ""]
        out.write_text("\n".join(lines), encoding="utf-8")
        print(f"{name}: gefunden={found} spec={spec_ok} tools={len(tools)} {secs:.0f}s", flush=True)
    head = ["| Fall | Entwurf gefunden | Vorgabe | Werkzeugaufrufe | Dauer | Erwartung |", "|---|---|---|---|---|---|"]
    out.write_text("\n".join(lines[:2] + head + summary + [""] + lines[2:]), encoding="utf-8")
    print(f"Bericht: {out}")
    srv.shutdown()


if __name__ == "__main__":
    main()
