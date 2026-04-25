from __future__ import annotations

from dataclasses import dataclass

from app.domain.clips.base_clip import BaseClip


@dataclass(slots=True)
class VideoClip(BaseClip):
    playback_speed: float = 1.0
    is_reversed: bool = False
    position_x: float = 0.5
    position_y: float = 0.5
    scale: float = 1.0
    rotation: float = 0.0
    brightness: float = 0.0
    contrast: float = 0.0
    saturation: float = 0.0
    blur: float = 0.0
    vignette: float = 0.0
    color_preset: str = "none"
