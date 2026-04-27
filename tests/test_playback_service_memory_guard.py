"""Smoke test that PlaybackService consults the memory guard each request."""

from __future__ import annotations

from services.memory_guard import MemoryGuard
from services.playback_service import PlaybackService


class _RecordingGuard(MemoryGuard):
    def __init__(self) -> None:
        super().__init__(check_every_n_calls=1)
        self.calls = 0

    def maybe_shrink(self, decoder):  # type: ignore[override]
        self.calls += 1
        return 0


def test_playback_service_invokes_memory_guard_on_each_request():
    guard = _RecordingGuard()
    service = PlaybackService(memory_guard=guard)

    # The guard is consulted before any project lookup, so even a no-project
    # request should trigger the check (cheap to do).
    service.get_preview_frame(project=None, time_seconds=0.0)
    service.get_preview_frame(project=None, time_seconds=0.5)
    service.get_preview_frame(project=None, time_seconds=1.0)

    assert guard.calls == 3
