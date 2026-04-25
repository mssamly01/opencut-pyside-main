from __future__ import annotations

from app.domain.clips.base_clip import BaseClip
from app.domain.commands.base_command import BaseCommand
from app.domain.timeline import Timeline
from app.domain.track import Track


class AddClipCommand(BaseCommand):
    def __init__(self, timeline: Timeline, track_id: str, clip: BaseClip) -> None:
        self._timeline = timeline
        self._track_id = track_id
        self._clip = clip
        self._insert_index: int | None = None

    def execute(self) -> None:
        track = self._find_track(self._track_id)
        if self._insert_index is None:
            self._insert_index = len(track.clips)
        insert_index = min(self._insert_index, len(track.clips))
        track.clips.insert(insert_index, self._clip)

    def undo(self) -> None:
        if self._insert_index is None:
            raise RuntimeError("Cannot undo before command execution")

        track = self._find_track(self._track_id)
        for index, clip in enumerate(track.clips):
            if clip.clip_id == self._clip.clip_id:
                del track.clips[index]
                return
        raise RuntimeError(f"Clip '{self._clip.clip_id}' not found in track '{self._track_id}'")

    def _find_track(self, track_id: str) -> Track:
        for track in self._timeline.tracks:
            if track.track_id == track_id:
                return track
        raise ValueError(f"Track '{track_id}' not found in timeline")
