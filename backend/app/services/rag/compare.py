"""
What the compare endpoint adds around `pipeline.run()` (docs/design-rag.md
§5.3): the time budget, VM-wide CPU use for the request, and a record of
compare traffic so live answering can pause itself during a harness run.

Activity is kept in process memory, which is fine because the design assumes
one backend process (§5.4).
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

import psutil

from ...config import settings

_active = 0
_last_ended: float | None = None


def deadline(arrival: float) -> float:
    """The `time.monotonic()` value a compare call must finish by.

    A total budget from arrival, kept under the harness's 180 s timeout: on
    expiry the pipeline returns the partial answer instead of failing.
    """
    return arrival + settings.RAG_COMPARE_BUDGET_S


@contextmanager
def tracking() -> Iterator[None]:
    """Marks a compare call in progress, and when it ended (even on error)."""
    global _active, _last_ended
    _active += 1
    try:
        yield
    finally:
        _active -= 1
        _last_ended = time.monotonic()


def active_or_ended_within(seconds: float) -> bool:
    """True while a compare call runs, or if one ended in the last `seconds`."""
    if _active:
        return True
    return _last_ended is not None and time.monotonic() - _last_ended < seconds


class CpuWindow:
    """
    CPU use between creation and `percent()`: busy time over total time from
    `psutil.cpu_times()`. Not `psutil.cpu_percent()`, whose one baseline per
    process would be reset by a concurrent request. Docker doesn't namespace
    `/proc/stat`, so this is the whole VM, Ollama and Infinity included.
    """

    def __init__(self) -> None:
        self._start = _busy_and_total()

    def percent(self) -> float:
        busy0, total0 = self._start
        busy1, total1 = _busy_and_total()
        elapsed = total1 - total0
        if elapsed <= 0:
            return 0.0
        return round(min(100.0, max(0.0, 100.0 * (busy1 - busy0) / elapsed)), 1)


def _busy_and_total() -> tuple[float, float]:
    times = psutil.cpu_times()._asdict()
    # On Linux, guest time is already counted in user and nice.
    total = sum(v for k, v in times.items() if k not in ("guest", "guest_nice"))
    idle = times.get("idle", 0.0) + times.get("iowait", 0.0)
    return total - idle, total
