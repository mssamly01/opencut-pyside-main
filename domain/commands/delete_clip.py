from __future__ import annotations

from app.domain.clips.base_clip import BaseClip
from app.domain.commands.base_command import BaseCommand
from app.domain.timeline import Timeline


class DeleteClipCommand(BaseCommand):
    def __init__(self, timeline: Timeline, clip_id: str) -> None:
        self._timeline = timeline
        self._clip_id = clip_id
        self._deleted_clip: BaseClip | None = None
        self._deleted_track_index: int | None = None
        self._deleted_clip_index: int | None = None

    def execute(self) -> None:
        track_index, clip_index = self._find_clip_location(self._clip_id)
        track = self._timeline.tracks[track_index]
        deleted_clip = track.clips.pop(clip_index)

        if self._deleted_clip is None:
            self._deleted_clip = deleted_clip
            self._deleted_track_index = track_index
            self._deleted_clip_index = clip_index

    def undo(self) -> None:
        if self._deleted_clip is None or self._deleted_track_index is None or self._deleted_clip_index is None:
            raise RuntimeError("Cannot undo before command execution")

        track = self._timeline.tracks[self._deleted_track_index]
        insert_index = min(self._deleted_clip_index, len(track.clips))
        track.clips.insert(insert_index, self._deleted_clip)

    def _find_clip_location(self, clip_id: str) -> tuple[int, int]:
        for track_index, track in enumerate(self._timeline.tracks):
            for clip_index, clip in enumerate(track.clips):
                if clip.clip_id == clip_id:
                    return track_index, clip_index
        raise ValueError(f"Clip '{clip_id}' not found in timeline")
