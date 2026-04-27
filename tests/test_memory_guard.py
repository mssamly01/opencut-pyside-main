"""Tests for MemoryGuard + VideoDecoder cache shrink helpers."""

from __future__ import annotations

from collections import OrderedDict

from infrastructure.video_decoder import VideoDecoder
from services import memory_guard
from services.memory_guard import MemoryGuard


class _FakeDecoder:
    """Minimal stand-in matching the protocol MemoryGuard expects."""

    def __init__(self, count: int) -> None:
        self._count = count
        self.shrink_calls: list[int] = []

    def cache_size(self) -> int:
        return self._count

    def shrink_cache_to(self, target_count: int) -> int:
        self.shrink_calls.append(target_count)
        evicted = max(0, self._count - target_count)
        self._count = min(self._count, target_count)
        return evicted


def _set_memory_percent(monkeypatch, percent: float | None) -> None:
    monkeypatch.setattr(memory_guard, "current_memory_percent", lambda: percent)


def test_video_decoder_shrink_cache_evicts_oldest(monkeypatch):
    decoder = VideoDecoder(max_cache_entries=10)
    # Fill the cache directly (bypass ffmpeg).
    for i in range(8):
        decoder._frame_cache[("path", 30000, i, "")] = b"frame-bytes"  # noqa: SLF001
    assert decoder.cache_size() == 8

    evicted = decoder.shrink_cache_to(3)

    assert evicted == 5
    assert decoder.cache_size() == 3
    # Oldest entries (0,1,2,3,4) evicted; newest (5,6,7) retained.
    cache: OrderedDict = decoder._frame_cache  # noqa: SLF001
    remaining_indices = sorted(key[2] for key in cache)
    assert remaining_indices == [5, 6, 7]


def test_video_decoder_shrink_cache_zero_target_clears_all():
    decoder = VideoDecoder(max_cache_entries=10)
    for i in range(4):
        decoder._frame_cache[("p", 30000, i, "")] = b"x"  # noqa: SLF001
    assert decoder.shrink_cache_to(0) == 4
    assert decoder.cache_size() == 0


def test_video_decoder_shrink_cache_below_size_is_noop():
    decoder = VideoDecoder(max_cache_entries=10)
    for i in range(2):
        decoder._frame_cache[("p", 30000, i, "")] = b"x"  # noqa: SLF001
    assert decoder.shrink_cache_to(50) == 0
    assert decoder.cache_size() == 2


def test_video_decoder_shrink_cache_clears_prefetched_until_on_eviction():
    """Regression: shrink_cache_to must invalidate the prefetch watermark.

    Without this, has_prefetched_until still reports True for indices whose
    payloads were just evicted, _prefetch_window short-circuits, and
    get_preview_frame falls through to slow single-frame decoding for every
    request after a memory-pressure event.
    """

    decoder = VideoDecoder(max_cache_entries=10)
    for i in range(8):
        decoder._frame_cache[("path", 30000, i, "")] = b"x"  # noqa: SLF001
    decoder._prefetched_until[("path", 30000, "")] = 7  # noqa: SLF001

    decoder.shrink_cache_to(3)

    # Watermark cleared so the next request triggers a fresh decode_window.
    assert decoder.has_prefetched_until("path", 30.0, 5) is False
    assert decoder._prefetched_until == {}  # noqa: SLF001


def test_video_decoder_shrink_cache_keeps_watermark_when_no_eviction():
    """If nothing was evicted, the prefetch watermark must stay intact."""

    decoder = VideoDecoder(max_cache_entries=10)
    for i in range(2):
        decoder._frame_cache[("path", 30000, i, "")] = b"x"  # noqa: SLF001
    decoder._prefetched_until[("path", 30000, "")] = 1  # noqa: SLF001

    decoder.shrink_cache_to(50)

    assert decoder._prefetched_until == {("path", 30000, ""): 1}  # noqa: SLF001


def test_memory_guard_no_shrink_when_under_threshold(monkeypatch):
    guard = MemoryGuard(threshold_percent=75.0, check_every_n_calls=1)
    _set_memory_percent(monkeypatch, 50.0)
    decoder = _FakeDecoder(count=200)

    evicted = guard.maybe_shrink(decoder)

    assert evicted == 0
    assert decoder.shrink_calls == []


def test_memory_guard_shrinks_when_over_threshold(monkeypatch):
    guard = MemoryGuard(
        threshold_percent=75.0,
        target_cache_factor=0.5,
        min_cache_floor=60,
        check_every_n_calls=1,
    )
    _set_memory_percent(monkeypatch, 90.0)
    decoder = _FakeDecoder(count=200)

    evicted = guard.maybe_shrink(decoder)

    # 200 * 0.5 = 100 → evict 100; floor of 60 not breached.
    assert decoder.shrink_calls == [100]
    assert evicted == 100


def test_memory_guard_respects_floor_when_factor_would_go_below(monkeypatch):
    guard = MemoryGuard(
        threshold_percent=75.0,
        target_cache_factor=0.1,
        min_cache_floor=60,
        check_every_n_calls=1,
    )
    _set_memory_percent(monkeypatch, 95.0)
    decoder = _FakeDecoder(count=80)

    guard.maybe_shrink(decoder)
    # 80 * 0.1 = 8 — clamped to floor 60.
    assert decoder.shrink_calls == [60]


def test_memory_guard_skips_when_cache_at_or_below_floor(monkeypatch):
    guard = MemoryGuard(
        threshold_percent=75.0,
        min_cache_floor=60,
        check_every_n_calls=1,
    )
    _set_memory_percent(monkeypatch, 95.0)
    decoder = _FakeDecoder(count=60)

    assert guard.maybe_shrink(decoder) == 0
    assert decoder.shrink_calls == []


def test_memory_guard_throttle_only_checks_every_n_calls(monkeypatch):
    guard = MemoryGuard(threshold_percent=75.0, check_every_n_calls=4)
    _set_memory_percent(monkeypatch, 90.0)
    decoder = _FakeDecoder(count=200)

    # First three calls should be skipped by the throttle.
    for _ in range(3):
        assert guard.maybe_shrink(decoder) == 0
    # The 4th call hits the modulo and shrinks.
    guard.maybe_shrink(decoder)
    assert len(decoder.shrink_calls) == 1


def test_memory_guard_no_op_when_psutil_returns_none(monkeypatch):
    guard = MemoryGuard(threshold_percent=75.0, check_every_n_calls=1)
    _set_memory_percent(monkeypatch, None)
    decoder = _FakeDecoder(count=500)

    assert guard.maybe_shrink(decoder) == 0
    assert decoder.shrink_calls == []
