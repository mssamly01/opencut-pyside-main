from __future__ import annotations

from app.domain.commands._keyframe_utils import (
    clone_keyframe,
    clone_keyframes,
    find_keyframe_index,
    insertion_index,
    keyframe_list,
    resolve_keyframe_attr,
    sort_keyframes_in_place,
)
from app.domain.commands.base_command import BaseCommand
from app.domain.keyframe import Keyframe


class AddKeyframeCommand(BaseCommand):
    def __init__(self, clip: object, property_name: str, keyframe: Keyframe) -> None:
        self._clip = clip
        self._attr_name = resolve_keyframe_attr(clip, property_name)
        self._keyframe = clone_keyframe(keyframe)
        self._before: list[Keyframe] | None = None
        self._after: list[Keyframe] | None = None

    def execute(self) -> None:
        if self._before is None:
            current = keyframe_list(self._clip, self._attr_name)
            self._before = clone_keyframes(current)
            working = clone_keyframes(current)

            index = find_keyframe_index(working, self._keyframe.time_seconds)
            if index is None:
                working.insert(insertion_index(working, self._keyframe.time_seconds), clone_keyframe(self._keyframe))
            else:
                working[index] = clone_keyframe(self._keyframe)
            sort_keyframes_in_place(working)
            self._after = working

        if self._after is None:
            raise RuntimeError("AddKeyframeCommand state is invalid")
        self._apply_snapshot(self._after)

    def undo(self) -> None:
        if self._before is None:
            raise RuntimeError("Cannot undo before command execution")
        self._apply_snapshot(self._before)

    def _apply_snapshot(self, snapshot: list[Keyframe]) -> None:
        target = keyframe_list(self._clip, self._attr_name)
        target[:] = clone_keyframes(snapshot)
