from __future__ import annotations

from dataclasses import replace

from app.domain.clips.base_clip import BaseClip
from app.domain.commands.base_command import BaseCommand
from app.domain.timeline import Timeline
from app.domain.track import Track


class SplitClipCommand(BaseCommand):
    def __init__(self, timeline: Timeline, clip_id: str, split_timeline_position: float) -> None:
        self._timeline = timeline
        self._clip_id = clip_id
        self._split_timeline_position = split_timeline_position

        self._track_id: str | None = None
        self._original_clip: BaseClip | None = None
        self._left_clip: BaseClip | None = None
        self._right_clip: BaseClip | None = None

    @property
    def left_clip_id(self) -> str:
        if self._left_clip is None:
            raise RuntimeError("Split command has not been executed yet")
        return self._left_clip.clip_id

    @property
    def right_clip_id(self) -> str:
        if self._right_clip is None:
            raise RuntimeError("Split command has not been executed yet")
        return self._right_clip.clip_id

    def execute(self) -> None:
        track, clip_index, original_clip = self._find_clip_location(self._clip_id)
        if self._original_clip is None:
            self._original_clip = original_clip
            self._track_id = track.track_id
            self._left_clip, self._right_clip = self._build_split_clips(original_clip)

        if self._left_clip is None or self._right_clip is None:
            raise RuntimeError("Split clips were not initialized")

        track.clips[clip_index : clip_index + 1] = [self._left_clip, self._right_clip]

    def undo(self) -> None:
        if self._track_id is None or self._original_clip is None or self._left_clip is None or self._right_clip is None:
            raise RuntimeError("Cannot undo before command execution")

        track = self._find_track(self._track_id)
        left_index = self._find_clip_index(track, self._left_clip.clip_id)
        right_index = self._find_clip_index(track, self._right_clip.clip_id)
        if left_index == right_index:
            raise RuntimeError("Split clip state is invalid")

        first = min(left_index, right_index)
        second = max(left_index, right_index)
        del track.clips[second]
        del track.clips[first]
        track.clips.insert(first, self._original_clip)

    def _build_split_clips(self, clip: BaseClip) -> tuple[BaseClip, BaseClip]:
        split_offset = self._split_timeline_position - clip.timeline_start
        if split_offset <= 0.0 or split_offset >= clip.duration:
            raise ValueError("Split position must be inside the clip")

        left_duration = split_offset
        right_duration = clip.duration - split_offset

        if clip.source_end is None:
            source_split_point = clip.source_start + left_duration
            left_source_end: float | None = None
            right_source_end: float | None = None
        else:
            source_span = clip.source_end - clip.source_start
            source_split_point = clip.source_start + (source_span * (left_duration / clip.duration))
            left_source_end = source_split_point
            right_source_end = clip.source_end

        used_ids = self._all_clip_ids()
        left_clip_id = self._build_unique_clip_id(f"{clip.clip_id}_L", used_ids)
        used_ids.add(left_clip_id)
        right_clip_id = self._build_unique_clip_id(f"{clip.clip_id}_R", used_ids)

        left_clip = replace(
            clip,
            clip_id=left_clip_id,
            duration=left_duration,
            source_end=left_source_end,
        )
        right_clip = replace(
            clip,
            clip_id=right_clip_id,
            timeline_start=self._split_timeline_position,
            duration=right_duration,
            source_start=source_split_point,
            source_end=right_source_end,
        )
        return left_clip, right_clip

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

    def _all_clip_ids(self) -> set[str]:
        clip_ids: set[str] = set()
        for track in self._timeline.tracks:
            for clip in track.clips:
                clip_ids.add(clip.clip_id)
        return clip_ids

    @staticmethod
    def _build_unique_clip_id(base_id: str, used_ids: set[str]) -> str:
        if base_id not in used_ids:
            return base_id

        counter = 1
        while True:
            candidate = f"{base_id}_{counter}"
            if candidate not in used_ids:
                return candidate
            counter += 1
