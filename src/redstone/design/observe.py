"""Frames of a design search for the GUI (docs/gui-api.md, "Job"): every candidate the search evaluates and
every compaction attempt. Without an observer (the default) `frame` does nothing.

The observer belongs to the calling thread, so the GUI server can run several searches at once."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager

Observer = Callable[[object, str, str, bool], None]  # candidate, phase, label, accepted

_local = threading.local()


def frame(candidate, phase: str, label: str, accepted: bool = True) -> None:
    """Report one step of the search: phase "compose" (a finished candidate) or "compact" (an attempt)."""
    fn = getattr(_local, "observer", None)
    if fn is not None and candidate is not None:
        fn(candidate, phase, label, accepted)


def active() -> bool:
    return getattr(_local, "observer", None) is not None


@contextmanager
def observing(fn: Observer) -> Iterator[None]:
    """Send the frames of this thread to `fn` while the block runs."""
    old = getattr(_local, "observer", None)
    _local.observer = fn
    try:
        yield
    finally:
        _local.observer = old
