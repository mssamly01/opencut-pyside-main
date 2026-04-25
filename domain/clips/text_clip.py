from __future__ import annotations

from dataclasses import dataclass

from app.domain.clips.base_clip import BaseClip


@dataclass(slots=True)
class TextClip(BaseClip):
    content: str = ""
    font_size: int = 48
    color: str = "#ffffff"
    position_x: float = 0.5
    position_y: float = 0.5
    font_family: str = "Arial"
    bold: bool = False
    italic: bool = False
    alignment: str = "center"
    outline_color: str = "#000000"
    outline_width: float = 0.0
    background_color: str = "#000000"
    background_opacity: float = 0.0
    shadow_color: str = "#000000"
    shadow_offset_x: float = 0.0
    shadow_offset_y: float = 0.0
    scale: float = 1.0
    rotation: float = 0.0
