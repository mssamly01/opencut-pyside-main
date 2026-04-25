from __future__ import annotations

from app.domain.clips.base_clip import BaseClip
from app.domain.commands.base_command import BaseCommand
from app.domain.timeline import Timeline
from app.domain.track import Track


class MoveClipToTrackCommand(BaseCommand):
    def __init__(self, timeline: Timeline, clip_id: str, target_track_id: str) -> None:
        self._timeline = timeline
        self._clip_id = clip_id
        self._target_track_id = target_track_id
        self._source_track_id: str | None = None
        self._source_index: int | None = None
        self._target_index: int | None = None
        self._clip: BaseClip | None = None

    def execute(self) -> None:
        source_track, source_index, clip = self._find_clip_location(self._clip_id)
        target_track = self._find_track(self._target_track_id)
        if source_track.track_id == target_track.track_id:
            return

        removed = source_track.clips.pop(source_index)
        removed.track_id = target_track.track_id
        target_index = len(target_track.clips)
        target_track.clips.insert(target_index, removed)

        if self._clip is None:
            self._clip = removed
            self._source_track_id = source_track.track_id
            self._source_index = source_index
            self._target_index = target_index

    def undo(self) -> None:
        if (
            self._clip is None
            or self._source_track_id is None
            or self._source_index is None
            or self._target_index is None
        ):
            raise RuntimeError("Cannot undo before command execution")

        target_track = self._find_track(self._target_track_id)
        source_track = self._find_track(self._source_track_id)
        current_index = self._find_clip_index(target_track, self._clip.clip_id)
        clip = target_track.clips.pop(current_index)
        clip.track_id = source_track.track_id
        insert_index = max(0, min(self._source_index, len(source_track.clips)))
        source_track.clips.insert(insert_index, clip)

    def _find_clip_location(self, clip_id: str) -> tuple[Track, int, BaseClip]:
        for track in self._timeline.tracks:
            for clip_index, clip in enumerate(track.clips):
                if clip.clip_id == clip_id:
                    return track, clip_index, clip
        raise ValueError(f"Clip '{clip_id}' not found in timeline")

    def _find_track(self, track_id: str) -> Track:
        for track in self._timeline.tracks:
            if track.track_id == track_id:
                return track
        raise ValueError(f"Track '{track_id}' not found in timeline")

    @staticmethod
    def _find_clip_index(track: Track, clip_id: str) -> int:
        for clip_index, clip in enumerate(track.clips):
            if clip.clip_id == clip_id:
                return clip_index
        raise ValueError(f"Clip '{clip_id}' not found in track '{track.track_id}'")

