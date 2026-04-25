from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.clips.base_clip import BaseClip
from app.domain.keyframe import Keyframe


@dataclass(slots=True)
class AudioClip(BaseClip):
    gain_db: float = 0.0
    playback_speed: float = 1.0
    gain_db_keyframes: list[Keyframe] = field(default_factory=list)
