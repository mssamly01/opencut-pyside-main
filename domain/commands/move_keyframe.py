from __future__ import annotations

from app.domain.commands._keyframe_utils import (
    clone_keyframe,
    clone_keyframes,
    find_keyframe_index,
    keyframe_list,
    resolve_keyframe_attr,
    sort_keyframes_in_place,
)
from app.domain.commands.base_command import BaseCommand
from app.domain.keyframe import Keyframe


class MoveKeyframeCommand(BaseCommand):
    def __init__(
        self,
        clip: object,
        property_name: str,
        old_time_seconds: float,
        new_time_seconds: float,
    ) -> None:
        self._clip = clip
        self._attr_name = resolve_keyframe_attr(clip, property_name)
        self._old_time_seconds = float(old_time_seconds)
        self._new_time_seconds = float(new_time_seconds)
        self._before: list[Keyframe] | None = None
        self._after: list[Keyframe] | None = None

    def execute(self) -> None:
        if self._before is None:
            current = keyframe_list(self._clip, self._attr_name)
            self._before = clone_keyframes(current)
            working = clone_keyframes(current)

            index = find_keyframe_index(working, self._old_time_seconds)
            if index is None:
                raise ValueError(
                    f"No keyframe found near {self._old_time_seconds:.6f}s "
                    f"for property '{self._attr_name}'"
                )

            moving = clone_keyframe(working[index])
            moving.time_seconds = self._new_time_seconds
            del working[index]

            destination = find_keyframe_index(working, self._new_time_seconds)
            if destination is not None:
                working[destination] = moving
            else:
                working.append(moving)
            sort_keyframes_in_place(working)
            self._after = working

        if self._after is None:
            raise RuntimeError("MoveKeyframeCommand state is invalid")
        self._apply_snapshot(self._after)

    def undo(self) -> None:
        if self._before is None:
            raise RuntimeError("Cannot undo before command execution")
        self._apply_snapshot(self._before)

    def _apply_snapshot(self, snapshot: list[Keyframe]) -> None:
        target = keyframe_list(self._clip, self._attr_name)
        target[:] = clone_keyframes(snapshot)
