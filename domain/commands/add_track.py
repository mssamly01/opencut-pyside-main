from __future__ import annotations

from app.domain.commands.base_command import BaseCommand
from app.domain.timeline import Timeline
from app.domain.track import Track


class AddTrackCommand(BaseCommand):
    def __init__(self, timeline: Timeline, track: Track, insert_index: int | None = None) -> None:
        self._timeline = timeline
        self._track = track
        self._insert_index = insert_index

    def execute(self) -> None:
        if self._insert_index is None:
            self._insert_index = len(self._timeline.tracks)

        safe_index = max(0, min(self._insert_index, len(self._timeline.tracks)))
        if any(track.track_id == self._track.track_id for track in self._timeline.tracks):
            return
        self._timeline.tracks.insert(safe_index, self._track)

    def undo(self) -> None:
        for index, track in enumerate(self._timeline.tracks):
            if track.track_id == self._track.track_id:
                del self._timeline.tracks[index]
                return
        raise RuntimeError(f"Track '{self._track.track_id}' not found in timeline")

