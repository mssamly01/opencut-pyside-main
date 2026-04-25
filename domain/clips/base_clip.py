from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class BaseClip:
    clip_id: str
    name: str
    track_id: str
    timeline_start: float
    duration: float
    media_id: str | None = None
    source_start: float = 0.0
    source_end: float | None = None
    opacity: float = 1.0
    is_locked: bool = False
    is_muted: bool = False
    fade_in_seconds: float = 0.0
    fade_out_seconds: float = 0.0

    @property
    def timeline_end(self) -> float:
        return self.timeline_start + self.duration
