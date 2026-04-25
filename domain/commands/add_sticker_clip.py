from __future__ import annotations

from app.domain.clips.sticker_clip import StickerClip
from app.domain.commands.base_command import BaseCommand
from app.domain.track import Track


class AddStickerClipCommand(BaseCommand):
    def __init__(self, track: Track, clip: StickerClip) -> None:
        self._track = track
        self._clip = clip

    def execute(self) -> None:
        if any(existing.clip_id == self._clip.clip_id for existing in self._track.clips):
            return
        self._track.clips.append(self._clip)

    def undo(self) -> None:
        self._track.clips = [
            clip for clip in self._track.clips if clip.clip_id != self._clip.clip_id
        ]
