"""Memory-pressure watchdog for the preview frame cache.

Translated from ``MainWindow._check_memory_usage`` /
``MainWindow._clear_frame_cache`` in the reference ``editor_app.py``. The
guard shrinks the :class:`VideoDecoder` cache when overall system memory
crosses a configurable threshold so long-running edits on multi-hour 4K
footage don't OOM the process.

``psutil`` is a soft dependency: when it is unavailable the guard logs a
debug line once and degrades to a no-op so the rest of the app keeps
working.
"""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)

try:  # pragma: no cover - import resolution depends on environment
    import psutil  # type: ignore[import-untyped]

    _PSUTIL_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised in degraded envs
    psutil = None  # type: ignore[assignment]
    _PSUTIL_AVAILABLE = False


class _SupportsCacheShrink(Protocol):
    def cache_size(self) -> int: ...
    def shrink_cache_to(self, target_count: int) -> int: ...


def current_memory_percent() -> float | None:
    """Return overall system memory utilisation as a percentage (0-100).

    Returns ``None`` when ``psutil`` is missing so callers can degrade to a
    no-op without raising.
    """

    if not _PSUTIL_AVAILABLE:
        return None
    try:
        return float(psutil.virtual_memory().percent)
    except Exception:  # pragma: no cover - psutil failures are non-fatal
        logger.debug("psutil.virtual_memory() failed; skipping memory check", exc_info=True)
        return None


class MemoryGuard:
    """Decides when to shrink the frame cache based on system memory load.

    The guard is throttled so it doesn't ask psutil on every frame request
    (querying ``virtual_memory`` is cheap but not free). Set
    ``check_every_n_calls`` to 1 in tests if you want every call to consult
    psutil.
    """

    def __init__(
        self,
        *,
        threshold_percent: float = 75.0,
        target_cache_factor: float = 0.5,
        min_cache_floor: int = 60,
        check_every_n_calls: int = 12,
    ) -> None:
        self._threshold_percent = float(threshold_percent)
        self._target_cache_factor = max(0.0, min(1.0, float(target_cache_factor)))
        self._min_cache_floor = max(0, int(min_cache_floor))
        self._check_every_n_calls = max(1, int(check_every_n_calls))
        self._call_count = 0

    @property
    def threshold_percent(self) -> float:
        return self._threshold_percent

    def maybe_shrink(self, decoder: _SupportsCacheShrink) -> int:
        """Evict frames if system memory is above the threshold.

        Returns the number of cache entries evicted (``0`` when nothing was
        done — either because we are under the threshold, the cache is
        already small, or psutil isn't available).
        """

        self._call_count += 1
        if self._call_count % self._check_every_n_calls != 0:
            return 0

        percent = current_memory_percent()
        if percent is None or percent < self._threshold_percent:
            return 0

        cache_size = decoder.cache_size()
        if cache_size <= self._min_cache_floor:
            return 0
        target = max(self._min_cache_floor, int(cache_size * self._target_cache_factor))
        if target >= cache_size:
            return 0
        return decoder.shrink_cache_to(target)
