from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.clips.base_clip import BaseClip
from app.domain.transition import Transition


@dataclass(slots=True)
class Track:
    track_id: str
    name: str
    track_type: str
    track_role: str = "music"
    clips: list[BaseClip] = field(default_factory=list)
    is_muted: bool = False
    is_locked: bool = False
    is_hidden: bool = False
    is_main: bool = False
    height: float = 58.0
    transitions: list[Transition] = field(default_factory=list)

    def sorted_clips(self) -> tuple[BaseClip, ...]:
        return tuple(sorted(self.clips, key=lambda clip: clip.timeline_start))
