"""JSON API of the GUI server (docs/gui-api.md) against a real server on a free port."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from redstone.design import observe
from redstone.gui.server import make_server


@pytest.fixture(scope="module")
def api():
    server = make_server(0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]

    def call(path: str, body: dict | None = None):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                     data=None if body is None else json.dumps(body).encode(),
                                     method="GET" if body is None else "POST")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    yield call
    server.shutdown()
    server.server_close()
    for sim in list(server.RequestHandlerClass.app_state.sims.values()):
        sim.close()


def test_files_and_model(api):
    status, files = api("/api/files")
    assert status == 200
    assert "scenarios/cmp-cmp3.yaml" in files["scenarios"]
    assert "examples/specs/xor.yaml" in files["specs"]
    status, model = api("/api/model?path=scenarios/cmp-cmp3.yaml")
    assert status == 200
    assert model["name"] == "cmp-cmp3"
    assert {o["name"] for o in model["outputs"]} == {"gt", "lt"}
    assert len(model["build_order"]) == len(model["blocks"])
    assert all(not b["s"].startswith("minecraft:") for b in model["blocks"])


def test_errors(api):
    assert api("/api/model?path=../outside.yaml")[0] == 403
    assert api("/api/model?path=scenarios/missing.yaml")[0] == 404
    status, body = api("/api/model?path=examples/specs/xor.yaml")
    assert status == 400 and "Szenario" in body["error"]
    assert api("/api/nothing")[0] == 404
    assert api("/api/sim/999/tick", {"n": 1})[0] == 404


def test_simulation(api):
    _, model = api("/api/model?path=scenarios/cmp-cmp3.yaml")
    status, sim = api("/api/sim", {"path": "scenarios/cmp-cmp3.yaml"})
    assert status == 200 and sim["tick"] == 0
    sid = sim["sim"]
    a1 = next(i["p"] for i in model["inputs"] if i["name"] == "a1")
    _, r = api(f"/api/sim/{sid}/use", {"p": a1})
    assert any(c["p"] == a1 and "powered=true" in c["s"] for c in r["changed"])
    _, r = api(f"/api/sim/{sid}/tick", {"n": 30})
    assert r["tick"] == 30
    gt = next(o["p"] for o in model["outputs"] if o["name"] == "gt")
    assert {"p": gt, "s": "redstone_lamp[lit=true]"} in r["changed"]
    assert api(f"/api/sim/{sid}/tick", {"n": 0})[0] == 400
    assert api(f"/api/sim/{sid}/use", {"p": [0, 0, 0]})[0] == 400


def test_redesign_job(api):
    status, body = api("/api/redesign", {"path": "examples/specs/xor.yaml", "compact": 10})
    assert status == 200
    job = body["job"]
    deadline = time.time() + 120
    while True:
        _, st = api(f"/api/job/{job}?since=0")
        if st["done"] or time.time() > deadline:
            break
        time.sleep(0.2)
    assert st["done"] and st["error"] is None
    assert st["frames"] and st["frames"][0]["phase"] == "compose"
    assert [f["i"] for f in st["frames"]] == list(range(len(st["frames"])))
    assert st["result"]["inputs"][0]["name"] == "a" and "Redesign" in st["result"]["summary"]
    _, later = api(f"/api/job/{job}?since={len(st['frames'])}")
    assert later["frames"] == []
    status, sim = api("/api/sim", {"job": job})
    assert status == 200 and sim["model"]["size"] == st["result"]["size"]


def test_observer_is_per_thread():
    seen = []
    with observe.observing(lambda *a: seen.append(a)):
        observe.frame(object(), "compose", "x")
        t = threading.Thread(target=observe.frame, args=(object(), "compose", "other thread"))
        t.start()
        t.join()
    observe.frame(object(), "compose", "after")
    assert [a[2] for a in seen] == ["x"]
