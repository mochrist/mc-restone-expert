"""Assistant of the GUI (gui/assistant.py): tool loop with a mocked Anthropic client, endpoints without a key."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from redstone.gui import assistant
from redstone.gui.server import make_server


def text(t):
    return SimpleNamespace(type="text", text=t)


def tool(i, name, inp):
    return SimpleNamespace(type="tool_use", id=i, name=name, input=inp)


class FakeClient:
    """Answers with scripted responses and records every request."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append({**kw, "messages": list(kw["messages"])})
        content, stop = self.script.pop(0)
        return SimpleNamespace(content=content, stop_reason=stop)


@pytest.fixture()
def server(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(assistant, "KEY_FILE", tmp_path / "key")
    srv = make_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]

    def call(path, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                     data=None if body is None else json.dumps(body).encode(),
                                     method="GET" if body is None else "POST")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    yield call, srv.RequestHandlerClass.app_state
    srv.shutdown()
    srv.server_close()


def wait(call, cid, since=0, timeout=120):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        _, snap = call(f"/api/chat/{cid}?since={since}")
        if not snap["busy"]:
            return snap["events"]
        time.sleep(0.2)
    raise AssertionError("chat turn did not finish")


def test_without_key(server):
    call, _ = server
    status, info = call("/api/assistant")
    assert status == 200 and info["configured"] is False
    status, r = call("/api/chat", {"message": "Hallo"})
    assert status == 200
    events = wait(call, r["chat"])
    assert events[-1]["type"] == "error" and "API-Schlüssel" in events[-1]["text"]
    assert call("/api/chat", {"message": " "})[0] == 400
    assert call("/api/chat/999")[0] == 404


def test_key_storage(server):
    call, _ = server
    assert call("/api/assistant/key", {"key": "hallo"})[0] == 400
    status, r = call("/api/assistant/key", {"key": "sk-ant-test"})
    assert status == 200 and r == {"configured": True, "source": "file"}
    assert assistant.KEY_FILE.read_text(encoding="utf-8") == "sk-ant-test"
    assert call("/api/assistant/key", {"key": ""})[1]["configured"] is False
    assert not assistant.KEY_FILE.exists()


def test_tool_loop(server):
    call, state = server
    fake = FakeClient([
        ([text("Ich suche ein Beispiel."), tool("t1", "find_examples", {"query": "xor2"})], "tool_use"),
        ([tool("t2", "load_example", {"path": "scenarios/tpl-xor2-comparator.yaml"})], "tool_use"),
        ([tool("t3", "design_circuit", {"name": "tuer", "spec_yaml": "inputs: [a, b]\nfunction:\n  tuer: a and b\n"}),
          ], "tool_use"),
        ([tool("t4", "explain_circuit", {}), tool("t5", "load_example", {"path": "nope.yaml"})], "tool_use"),
        ([text("Fertig: zwei Hebel öffnen die Tür.")], "end_turn"),
    ])
    state.client_factory = lambda: fake
    status, r = call("/api/chat", {"message": "Eine Tür mit zwei Hebeln", "current": None})
    assert status == 200
    events = wait(call, r["chat"])
    kinds = [e["type"] for e in events]
    assert "load" in kinds and "job" in kinds and kinds[-1] == "text"
    assert events[-1]["text"].startswith("Fertig")
    load = next(e for e in events if e["type"] == "load")
    assert load["path"] == "scenarios/tpl-xor2-comparator.yaml"
    job = next(e for e in events if e["type"] == "job")
    assert state.jobs[job["job"]].done and state.jobs[job["job"]].grid is not None

    # every request: model, fallbacks, tools; history alternates and carries the tool results
    c = fake.calls
    assert all(x["model"] == "claude-opus-5-5" and x["fallbacks"] == "default" for x in c)
    assert {t["name"] for t in c[0]["tools"]} == {"design_circuit", "explain_circuit", "shrink_circuit",
                                                   "find_examples", "load_example"}
    found = c[1]["messages"][-1]["content"][0]
    assert found["tool_use_id"] == "t1" and "tpl-xor2-comparator" in found["content"]
    designed = c[3]["messages"][-1]["content"][0]
    assert not designed["is_error"] and "Blöcke" in designed["content"]
    explained, missing = c[4]["messages"][-1]["content"]
    assert not explained["is_error"] and missing["is_error"]  # both results in one user message
    assert [m["role"] for m in c[4]["messages"]] == ["user", "assistant"] * 4 + ["user"]

    # next turn in the same chat continues the history
    fake.script.append(([text("Gern.")], "end_turn"))
    status, r2 = call("/api/chat", {"chat": r["chat"], "message": "Danke"})
    assert r2["chat"] == r["chat"]
    events = wait(call, r["chat"], r2["since"])
    assert events[-1] == {"i": events[-1]["i"], "type": "text", "text": "Gern."}
    assert len(fake.calls[-1]["messages"]) == 11
