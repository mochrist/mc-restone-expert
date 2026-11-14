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


@pytest.fixture(scope="module")
def raw():
    """Like `api`, but returns status, headers and the raw body (downloads, uploads)."""
    server = make_server(0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]

    def call(path: str, data: bytes | None = None):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
                                     method="GET" if data is None else "POST")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    yield call
    server.shutdown()
    server.server_close()


def test_explain_dump_and_scenario(api):
    status, r = api("/api/explain", {"path": "scenarios/tpl-xor2-comparator.yaml"})
    assert status == 200 and "**XOR**" in r["markdown"]
    assert set(r["svgs"]) == {"in1.svg", "in2.svg"} and "](svg/in1.svg)" in r["markdown"]
    assert all(s.lstrip().startswith("<svg") for s in r["svgs"].values())
    status, r = api("/api/dump", {"path": "scenarios/tpl-xor2-comparator.yaml", "layers": [1], "states": True})
    assert status == 200 and "Blockzustände" in r["text"] and "comparator" in r["text"]
    status, r = api("/api/scenario", {"path": "scenarios/tpl-xor2-comparator.yaml"})
    assert status == 200 and r["golden"] == {"matches": True, "count": 0, "mismatches": []}
    assert "#" in r["diagram"] and r["svg"].lstrip().startswith("<svg")
    assert api("/api/scenario", {"path": "examples/specs/xor.yaml"})[0] == 400
    assert api("/api/oracle", {"path": "examples/specs/xor.yaml"})[0] == 400
    status, info = api("/api/info")
    assert status == 200 and info["core"] in ("python", "rust")
    assert api("/api/core", {"core": info["core"]}) == (200, {"core": info["core"]})
    assert api("/api/core", {"core": "java"})[0] == 400
    status, r = api("/api/text?path=examples/specs/xor.yaml")
    assert status == 200 and "a != b" in r["text"]


def test_export_and_upload(raw, tmp_path):
    from redstone import io
    from redstone.gui.server import ROOT, WORK_DIR

    status, headers, body = raw("/api/export?path=scenarios/tpl-xor2-comparator.yaml&format=litematic")
    assert status == 200 and 'filename="tpl-xor2-comparator.litematic"' in headers["Content-Disposition"]
    target = tmp_path / "x.litematic"
    target.write_bytes(body)
    assert io.load(target).size == (5, 2, 5)
    for fmt, needle in (("materials", "Gesamt"), ("guide", "Bauanleitung"), ("dump", "y=0"), ("scenario", '"probes"')):
        status, _, text = raw(f"/api/export?path=scenarios/tpl-xor2-comparator.yaml&format={fmt}")
        assert status == 200 and needle in text.decode("utf-8"), fmt
    assert raw("/api/export?path=scenarios/tpl-xor2-comparator.yaml&format=exe")[0] == 400

    name = "gui-test-upload.litematic"
    try:
        status, _, answer = raw(f"/api/upload?name=../{name}", body)
        assert status == 200
        up = json.loads(answer)
        assert up == {"path": f"{WORK_DIR.as_posix()}/uploads/{name}", "group": "schematics"}
        status, _, files = raw("/api/files")
        assert up["path"] in json.loads(files)["schematics"]
        status, _, model = raw(f"/api/model?path={up['path']}")
        assert status == 200 and json.loads(model)["size"] == [5, 2, 5]
        assert raw("/api/upload?name=bad.litematic", b"not a schematic")[0] == 400
        assert raw("/api/upload?name=virus.exe", b"MZ")[0] == 400
    finally:
        (ROOT / WORK_DIR / "uploads" / name).unlink(missing_ok=True)


def test_spec_from_text_with_constraints(api):
    from redstone.gui.server import ROOT

    assert api("/api/spec", {"name": "x", "text": "- a\n- b\n"})[0] == 400
    status, spec = api("/api/spec", {"name": "gui test/and", "text": "inputs: [a, b]\nfunction:\n  y: a and b\n"})
    assert status == 200 and spec["group"] == "specs" and spec["path"].endswith("specs/and.yaml")
    try:
        assert api("/api/redesign", {"path": spec["path"], "max_size": "1,2"})[0] == 400
        assert api("/api/redesign", {"path": spec["path"], "time": 0})[0] == 400
        status, body = api("/api/redesign", {"path": spec["path"], "compact": 0, "forbid": "redstone_torch, repeater",
                                             "max_size": "6x4x6", "time": 20, "top": 3})
        assert status == 200
        deadline = time.time() + 120
        while True:
            _, st = api(f"/api/job/{body['job']}?since=0")
            if st["done"] or time.time() > deadline:
                break
            time.sleep(0.2)
        assert st["done"] and st["kind"] == "redesign"
        summary = st["result"]["summary"]
        assert "ohne redstone_torch, repeater" in summary and "max. 6×4×6" in summary
        if st["error"] is None:
            assert not any(b["s"].startswith(("redstone_torch", "redstone_wall_torch", "repeater"))
                           for b in st["result"]["blocks"])
            status, r = api("/api/explain", {"job": body["job"]})
            assert status == 200 and "Wahrheitstabelle" in r["markdown"]
    finally:
        (ROOT / spec["path"]).unlink(missing_ok=True)
