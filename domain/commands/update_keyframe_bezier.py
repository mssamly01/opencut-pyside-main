from __future__ import annotations

from app.domain.commands.base_command import BaseCommand
from app.domain.keyframe import Keyframe


class UpdateKeyframeBezierCommand(BaseCommand):
    _TIME_TOLERANCE = 1e-4

    def __init__(
        self,
        clip: object,
        property_name: str,
        time_seconds: float,
        cp1_dx: float,
        cp1_dy: float,
        cp2_dx: float,
        cp2_dy: float,
    ) -> None:
        self._clip = clip
        self._property_name = property_name
        self._time_seconds = float(time_seconds)
        self._new = (
            max(0.0, min(1.0, float(cp1_dx))),
            float(cp1_dy),
            max(0.0, min(1.0, float(cp2_dx))),
            float(cp2_dy),
        )
        self._old: tuple[float, float, float, float] | None = None

    def _find_keyframe(self) -> Keyframe | None:
        keyframes = getattr(self._clip, self._property_name, None)
        if not isinstance(keyframes, list):
            return None
        for keyframe in keyframes:
            if abs(float(keyframe.time_seconds) - self._time_seconds) <= self._TIME_TOLERANCE:
                return keyframe
        return None

    def execute(self) -> None:
        keyframe = self._find_keyframe()
        if keyframe is None:
            return
        if self._old is None:
            self._old = (
                float(keyframe.bezier_cp1_dx),
                float(keyframe.bezier_cp1_dy),
                float(keyframe.bezier_cp2_dx),
                float(keyframe.bezier_cp2_dy),
            )
        (
            keyframe.bezier_cp1_dx,
            keyframe.bezier_cp1_dy,
            keyframe.bezier_cp2_dx,
            keyframe.bezier_cp2_dy,
        ) = self._new

    def undo(self) -> None:
        if self._old is None:
            return
        keyframe = self._find_keyframe()
        if keyframe is None:
            return
        (
            keyframe.bezier_cp1_dx,
            keyframe.bezier_cp1_dy,
            keyframe.bezier_cp2_dx,
            keyframe.bezier_cp2_dy,
        ) = self._old
