"""Responsiveness of the GUI server while a long design search runs (task 11).

Starts a search over the API, times GET /api/files a few times while it runs, then cancels the search (if the
server can) and reports how long the job took to stop.

    uv run rsx gui --no-browser &      # in another shell
    uv run python scripts/gui_latency.py [--spec .cache/gui/specs/addierer4.yaml] [--samples 8]
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request

ADDER4 = """inputs: [a0, a1, a2, a3, b0, b1, b2, b3]
function:
  s0: a0 ^ b0
  s1: a1 ^ b1 ^ (a0 and b0)
  s2: a2 ^ b2 ^ ((a1 and b1) or ((a1 ^ b1) and (a0 and b0)))
  s3: a3 ^ b3 ^ ((a2 and b2) or ((a2 ^ b2) and ((a1 and b1) or ((a1 ^ b1) and (a0 and b0)))))
  s4: (a3 and b3) or ((a3 ^ b3) and ((a2 and b2) or ((a2 ^ b2) and ((a1 and b1) or ((a1 ^ b1) and (a0 and b0))))))
"""


def call(base: str, path: str, body: dict | None = None, timeout: float = 120) -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8737")
    ap.add_argument("--spec", default=None, help="spec path known to the server (default: a 4-bit adder, uploaded)")
    ap.add_argument("--samples", type=int, default=8)
    args = ap.parse_args()
    spec = args.spec
    if spec is None:
        r = call(args.base, "/api/spec", {"name": "latency-adder4", "text": ADDER4})
        spec = r["path"]
    job = call(args.base, "/api/redesign", {"path": spec})["job"]
    print(f"search {job} for {spec} started")
    time.sleep(3)
    times = []
    for _ in range(args.samples):
        t = time.perf_counter()
        call(args.base, "/api/files")
        times.append(time.perf_counter() - t)
        time.sleep(1)
    print("GET /api/files during the search: " + ", ".join(f"{x:.2f}" for x in times)
          + f" s (median {statistics.median(times):.2f} s)")
    t = time.perf_counter()
    try:
        call(args.base, f"/api/job/{job}/cancel", {})
    except urllib.error.HTTPError as e:
        print(f"cancel not available ({e.code}); the search keeps running")
        return
    while not call(args.base, f"/api/job/{job}?since=999999")["done"]:
        time.sleep(0.2)
    snap = call(args.base, f"/api/job/{job}?since=999999")
    print(f"cancelled after {time.perf_counter() - t:.2f} s: {snap.get('error')}")


if __name__ == "__main__":
    main()
