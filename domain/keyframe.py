from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

_VALID_INTERPOLATIONS = frozenset(
    {"linear", "hold", "ease_in", "ease_out", "ease_in_out", "bezier"}
)


@dataclass(slots=True)
class Keyframe:
    time_seconds: float
    value: float
    interpolation: str = "linear"
    bezier_cp1_dx: float = 0.42
    bezier_cp1_dy: float = 0.0
    bezier_cp2_dx: float = 0.58
    bezier_cp2_dy: float = 1.0

    def __post_init__(self) -> None:
        if self.interpolation not in _VALID_INTERPOLATIONS:
            raise ValueError(
                f"Unsupported interpolation '{self.interpolation}'. "
                f"Allowed: {sorted(_VALID_INTERPOLATIONS)}"
            )
        self.time_seconds = float(self.time_seconds)
        self.value = float(self.value)
        self.bezier_cp1_dx = max(0.0, min(1.0, float(self.bezier_cp1_dx)))
        self.bezier_cp2_dx = max(0.0, min(1.0, float(self.bezier_cp2_dx)))
        self.bezier_cp1_dy = float(self.bezier_cp1_dy)
        self.bezier_cp2_dy = float(self.bezier_cp2_dy)


def _ease_in(t: float) -> float:
    return t * t


def _ease_out(t: float) -> float:
    return 1.0 - (1.0 - t) ** 2


def _ease_in_out(t: float) -> float:
    return 0.5 * (1.0 - math.cos(math.pi * t))


def _cubic_bezier(
    t: float,
    p1x: float,
    p1y: float,
    p2x: float,
    p2y: float,
) -> float:
    """Solve cubic-bezier(P0=(0,0), P1=(p1x,p1y), P2=(p2x,p2y), P3=(1,1))."""

    def x_of(s: float) -> float:
        return 3 * (1 - s) ** 2 * s * p1x + 3 * (1 - s) * s * s * p2x + s * s * s

    def dx_of(s: float) -> float:
        return (
            3 * (1 - s) ** 2 * p1x
            - 6 * (1 - s) * s * p1x
            + 6 * (1 - s) * s * p2x
            - 3 * s * s * p2x
            + 3 * s * s
        )

    s = t
    for _ in range(8):
        fx = x_of(s) - t
        if abs(fx) < 1e-5:
            break
        derivative = dx_of(s)
        if abs(derivative) < 1e-9:
            break
        s = max(0.0, min(1.0, s - fx / derivative))

    return 3 * (1 - s) ** 2 * s * p1y + 3 * (1 - s) * s * s * p2y + s * s * s


def _apply_curve(t: float, keyframe: Keyframe) -> float:
    mode = keyframe.interpolation
    if mode == "ease_in":
        return _ease_in(t)
    if mode == "ease_out":
        return _ease_out(t)
    if mode == "ease_in_out":
        return _ease_in_out(t)
    if mode == "bezier":
        return _cubic_bezier(
            t,
            keyframe.bezier_cp1_dx,
            keyframe.bezier_cp1_dy,
            keyframe.bezier_cp2_dx,
            keyframe.bezier_cp2_dy,
        )
    return t


class AnimatedProperty:
    """Read-only evaluator over sorted keyframes."""

    __slots__ = ("_keyframes",)

    def __init__(self, keyframes: Iterable[Keyframe]) -> None:
        self._keyframes: list[Keyframe] = sorted(
            keyframes,
            key=lambda item: item.time_seconds,
        )

    @property
    def keyframes(self) -> list[Keyframe]:
        return list(self._keyframes)

    def is_empty(self) -> bool:
        return not self._keyframes

    def value_at(self, time_seconds: float, default: float) -> float:
        if not self._keyframes:
            return float(default)
        if len(self._keyframes) == 1:
            return float(self._keyframes[0].value)

        first = self._keyframes[0]
        last = self._keyframes[-1]
        if time_seconds <= first.time_seconds:
            return first.value
        if time_seconds >= last.time_seconds:
            return last.value

        for index in range(len(self._keyframes) - 1):
            left = self._keyframes[index]
            right = self._keyframes[index + 1]
            if not (left.time_seconds <= time_seconds <= right.time_seconds):
                continue

            if left.interpolation == "hold":
                return left.value

            span = right.time_seconds - left.time_seconds
            if span <= 1e-9:
                return right.value

            t = (time_seconds - left.time_seconds) / span
            eased = _apply_curve(t, left)
            return left.value + (right.value - left.value) * eased

        return last.value

    def time_segments(self) -> list[tuple[Keyframe, Keyframe]]:
        return [
            (self._keyframes[index], self._keyframes[index + 1])
            for index in range(len(self._keyframes) - 1)
        ]
