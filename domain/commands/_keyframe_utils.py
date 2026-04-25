from __future__ import annotations

from bisect import bisect_left
from collections.abc import Iterable

from app.domain.keyframe import Keyframe

TIME_EPSILON = 1e-4


def resolve_keyframe_attr(clip: object, property_name: str) -> str:
    attr_name = property_name
    if not attr_name.endswith("_keyframes"):
        attr_name = f"{attr_name}_keyframes"

    if not hasattr(clip, attr_name):
        raise ValueError(
            f"Clip '{getattr(clip, 'clip_id', '?')}' does not have keyframe property '{attr_name}'"
        )
    value = getattr(clip, attr_name)
    if not isinstance(value, list):
        raise ValueError(f"Property '{attr_name}' is not a keyframe list")
    return attr_name


def keyframe_list(clip: object, attr_name: str) -> list[Keyframe]:
    value = getattr(clip, attr_name)
    if not isinstance(value, list):
        raise ValueError(f"Property '{attr_name}' is not a keyframe list")
    return value


def clone_keyframe(keyframe: Keyframe) -> Keyframe:
    return Keyframe(
        time_seconds=keyframe.time_seconds,
        value=keyframe.value,
        interpolation=keyframe.interpolation,
        bezier_cp1_dx=keyframe.bezier_cp1_dx,
        bezier_cp1_dy=keyframe.bezier_cp1_dy,
        bezier_cp2_dx=keyframe.bezier_cp2_dx,
        bezier_cp2_dy=keyframe.bezier_cp2_dy,
    )


def clone_keyframes(keyframes: Iterable[Keyframe]) -> list[Keyframe]:
    return [clone_keyframe(item) for item in keyframes]


def find_keyframe_index(keyframes: list[Keyframe], time_seconds: float) -> int | None:
    for index, keyframe in enumerate(keyframes):
        if abs(float(keyframe.time_seconds) - float(time_seconds)) <= TIME_EPSILON:
            return index
    return None


def insertion_index(keyframes: list[Keyframe], time_seconds: float) -> int:
    sorted_times = [float(item.time_seconds) for item in keyframes]
    return bisect_left(sorted_times, float(time_seconds))


def sort_keyframes_in_place(keyframes: list[Keyframe]) -> None:
    keyframes.sort(key=lambda item: item.time_seconds)
