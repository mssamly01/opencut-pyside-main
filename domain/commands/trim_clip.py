from __future__ import annotations

from app.domain.clips.base_clip import BaseClip
from app.domain.commands.base_command import BaseCommand
from app.domain.timeline import Timeline


class TrimClipCommand(BaseCommand):
    def __init__(
        self,
        timeline: Timeline,
        clip_id: str,
        new_timeline_start: float,
        new_duration: float,
    ) -> None:
        if new_timeline_start < 0:
            raise ValueError("new_timeline_start must be >= 0")
        if new_duration <= 0:
            raise ValueError("new_duration must be > 0")

        self._timeline = timeline
        self._clip_id = clip_id
        self._new_timeline_start = new_timeline_start
        self._new_duration = new_duration
        self._previous_timeline_start: float | None = None
        self._previous_duration: float | None = None

    def execute(self) -> None:
        clip = self._find_clip(self._clip_id)
        if self._previous_timeline_start is None:
            self._previous_timeline_start = clip.timeline_start
            self._previous_duration = clip.duration
        clip.timeline_start = self._new_timeline_start
        clip.duration = self._new_duration

    def undo(self) -> None:
        if self._previous_timeline_start is None or self._previous_duration is None:
            raise RuntimeError("Cannot undo before command execution")

        clip = self._find_clip(self._clip_id)
        clip.timeline_start = self._previous_timeline_start
        clip.duration = self._previous_duration

    def _find_clip(self, clip_id: str) -> BaseClip:
        for track in self._timeline.tracks:
            for clip in track.clips:
                if clip.clip_id == clip_id:
                    return clip
        raise ValueError(f"Clip '{clip_id}' not found in timeline")
