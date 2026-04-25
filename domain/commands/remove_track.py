from __future__ import annotations

from app.domain.commands.base_command import BaseCommand
from app.domain.timeline import Timeline
from app.domain.track import Track


class RemoveTrackCommand(BaseCommand):
    def __init__(self, timeline: Timeline, track_id: str) -> None:
        self._timeline = timeline
        self._track_id = track_id
        self._removed_track: Track | None = None
        self._removed_index: int | None = None

    def execute(self) -> None:
        for index, track in enumerate(self._timeline.tracks):
            if track.track_id != self._track_id:
                continue
            removed_track = self._timeline.tracks.pop(index)
            if self._removed_track is None:
                self._removed_track = removed_track
                self._removed_index = index
            return
        raise ValueError(f"Track '{self._track_id}' not found in timeline")

    def undo(self) -> None:
        if self._removed_track is None or self._removed_index is None:
            raise RuntimeError("Cannot undo before command execution")

        safe_index = max(0, min(self._removed_index, len(self._timeline.tracks)))
        self._timeline.tracks.insert(safe_index, self._removed_track)

