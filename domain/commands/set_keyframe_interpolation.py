from __future__ import annotations

from app.domain.commands._keyframe_utils import (
    clone_keyframes,
    find_keyframe_index,
    keyframe_list,
    resolve_keyframe_attr,
)
from app.domain.commands.base_command import BaseCommand
from app.domain.keyframe import Keyframe


class SetKeyframeInterpolationCommand(BaseCommand):
    def __init__(
        self,
        clip: object,
        property_name: str,
        time_seconds: float,
        interpolation: str,
    ) -> None:
        # Validate mode early.
        Keyframe(time_seconds=0.0, value=0.0, interpolation=interpolation)

        self._clip = clip
        self._attr_name = resolve_keyframe_attr(clip, property_name)
        self._time_seconds = float(time_seconds)
        self._interpolation = interpolation
        self._before: list[Keyframe] | None = None
        self._after: list[Keyframe] | None = None

    def execute(self) -> None:
        if self._before is None:
            current = keyframe_list(self._clip, self._attr_name)
            self._before = clone_keyframes(current)
            working = clone_keyframes(current)
            index = find_keyframe_index(working, self._time_seconds)
            if index is None:
                raise ValueError(
                    f"No keyframe found near {self._time_seconds:.6f}s "
                    f"for property '{self._attr_name}'"
                )
            working[index].interpolation = self._interpolation
            self._after = working

        if self._after is None:
            raise RuntimeError("SetKeyframeInterpolationCommand state is invalid")
        self._apply_snapshot(self._after)

    def undo(self) -> None:
        if self._before is None:
            raise RuntimeError("Cannot undo before command execution")
        self._apply_snapshot(self._before)

    def _apply_snapshot(self, snapshot: list[Keyframe]) -> None:
        target = keyframe_list(self._clip, self._attr_name)
        target[:] = clone_keyframes(snapshot)
