from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.clips.base_clip import BaseClip
from app.domain.keyframe import Keyframe


@dataclass(slots=True)
class ImageClip(BaseClip):
    scale: float = 1.0
    position_x: float = 0.5
    position_y: float = 0.5
    rotation: float = 0.0
    brightness: float = 0.0
    contrast: float = 1.0
    saturation: float = 1.0
    hue: float = 0.0
    position_x_keyframes: list[Keyframe] = field(default_factory=list)
    position_y_keyframes: list[Keyframe] = field(default_factory=list)
    scale_keyframes: list[Keyframe] = field(default_factory=list)
    rotation_keyframes: list[Keyframe] = field(default_factory=list)
