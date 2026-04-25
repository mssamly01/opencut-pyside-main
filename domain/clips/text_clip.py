from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.clips.base_clip import BaseClip
from app.domain.keyframe import Keyframe
from app.domain.word_timing import WordTiming


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
    position_x_keyframes: list[Keyframe] = field(default_factory=list)
    position_y_keyframes: list[Keyframe] = field(default_factory=list)
    scale_keyframes: list[Keyframe] = field(default_factory=list)
    rotation_keyframes: list[Keyframe] = field(default_factory=list)
    word_timings: list[WordTiming] = field(default_factory=list)
    highlight_color: str = "#ffd166"

    def split_words_evenly(self) -> list[WordTiming]:
        """Return clip-relative word timings split evenly over clip duration."""
        words = [token for token in (self.content or "").split() if token.strip()]
        if not words:
            return []

        total_duration = max(1e-6, float(self.duration))
        per_word = total_duration / len(words)
        return [
            WordTiming(
                start_seconds=index * per_word,
                end_seconds=(index + 1) * per_word if index + 1 < len(words) else total_duration,
                text=word,
            )
            for index, word in enumerate(words)
        ]
