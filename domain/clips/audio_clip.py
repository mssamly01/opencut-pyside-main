from __future__ import annotations

from dataclasses import dataclass

from app.domain.clips.base_clip import BaseClip


@dataclass(slots=True)
class AudioClip(BaseClip):
    gain_db: float = 0.0
    playback_speed: float = 1.0
