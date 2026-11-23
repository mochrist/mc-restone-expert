"""Parallel work of the design search in threads (Task 13).

The expensive part of a simulator run happens in the Rust core without the GIL (`run_recording`), so threads run
the simulations of one evaluation side by side. Results always come back in the order of the work, and a caller
that stops early (first wrong output) sees exactly what the serial loop would have seen: the search finds the
same designs with any number of threads.

The number of threads: `set_jobs`, else the environment variable RSX_JOBS, else half the logical cores. With 1
everything runs in the calling thread, as before. The Python core holds the GIL throughout, so it always runs
serially.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from typing import TypeVar

from . import observe

T = TypeVar("T")
R = TypeVar("R")

_jobs: int | None = None
_pool: ThreadPoolExecutor | None = None
_pool_size = 0
_lock = threading.Lock()
_worker = threading.local()


def default_jobs() -> int:
    env = os.environ.get("RSX_JOBS", "").strip()
    if env:
        return max(1, int(env))
    return max(1, (os.cpu_count() or 2) // 2)


def jobs() -> int:
    """Threads for parallel work (1 = serial)."""
    return _jobs if _jobs is not None else default_jobs()


def set_jobs(n: int | None) -> None:
    """Set the number of threads (None: back to RSX_JOBS or the default)."""
    global _jobs
    _jobs = None if n is None else max(1, int(n))


def _executor(n: int) -> ThreadPoolExecutor:
    global _pool, _pool_size
    with _lock:
        if _pool is None or _pool_size != n:
            if _pool is not None:
                _pool.shutdown(wait=False)
            _pool = ThreadPoolExecutor(max_workers=n, thread_name_prefix="rsx-search")
            _pool_size = n
        return _pool


def _uses_rust() -> bool:
    from ..sim import core

    return core.active() == "rust"


def ordered(fn: Callable[[T], R], items: Iterable[T]) -> Iterator[R]:
    """fn(item) for every item, in order. Serial (lazy, item by item) with one job, in the Python core and inside
    a worker; otherwise in windows of `jobs()` items at a time, so a caller that stops early wastes at most one
    window. The workers take over the caller's cancel event (`observe.cancelling`)."""
    n = jobs()
    if n <= 1 or getattr(_worker, "active", False) or not _uses_rust():
        for item in items:
            yield fn(item)
        return
    cancel = observe.cancel_event()

    def run(item: T) -> R:
        _worker.active = True
        try:
            with observe.cancelling(cancel):
                return fn(item)
        finally:
            _worker.active = False

    pool = _executor(n)
    todo = list(items)
    for start in range(0, len(todo), n):
        futures: list[Future] = [pool.submit(run, item) for item in todo[start:start + n]]
        try:
            for f in futures:
                yield f.result()
        finally:
            for f in futures:
                f.cancel()
