from __future__ import annotations

from collections.abc import Iterable

from app.domain.keyframe import AnimatedProperty, Keyframe, _cubic_bezier


def _keyframe_attr_name(property_name: str) -> str:
    return property_name if property_name.endswith("_keyframes") else f"{property_name}_keyframes"


def _static_attr_name(property_name: str) -> str:
    if property_name.endswith("_keyframes"):
        return property_name[: -len("_keyframes")]
    return property_name


def clip_has_keyframes(clip: object, property_name: str) -> bool:
    keyframes = getattr(clip, _keyframe_attr_name(property_name), None)
    return isinstance(keyframes, list) and len(keyframes) > 0


def resolve_clip_value_at(
    clip: object,
    property_name: str,
    time_in_clip: float,
    default: float,
) -> float:
    static_name = _static_attr_name(property_name)
    static_value = float(getattr(clip, static_name, default))
    keyframes = getattr(clip, _keyframe_attr_name(property_name), None)
    if not isinstance(keyframes, list) or not keyframes:
        return static_value
    return AnimatedProperty(keyframes).value_at(float(time_in_clip), static_value)


def evaluate_bezier_segment(t: float, left_keyframe: Keyframe, right_keyframe: Keyframe) -> float:
    """Evaluate one keyframe segment in value space for preview/runtime usage."""
    clamped_t = max(0.0, min(1.0, float(t)))
    if left_keyframe.interpolation != "bezier":
        return left_keyframe.value + (right_keyframe.value - left_keyframe.value) * clamped_t
    eased = _cubic_bezier(
        clamped_t,
        left_keyframe.bezier_cp1_dx,
        left_keyframe.bezier_cp1_dy,
        left_keyframe.bezier_cp2_dx,
        left_keyframe.bezier_cp2_dy,
    )
    return left_keyframe.value + (right_keyframe.value - left_keyframe.value) * eased


class _FakeKeyframe:
    """Surrogate for tessellated bezier sub-points used in FFmpeg expressions."""

    __slots__ = ("time_seconds", "value", "interpolation")

    def __init__(self, time_seconds: float, value: float) -> None:
        self.time_seconds = float(time_seconds)
        self.value = float(value)
        self.interpolation = "linear"


def ffmpeg_piecewise_expression(
    animated_property: AnimatedProperty | Iterable[Keyframe],
    default_value: float,
    clip_duration: float,
) -> str:
    _ = clip_duration

    if isinstance(animated_property, AnimatedProperty):
        sorted_kfs = animated_property.keyframes
    else:
        sorted_kfs = sorted(animated_property, key=lambda kf: kf.time_seconds)

    if not sorted_kfs:
        return f"{float(default_value):.6f}"
    if len(sorted_kfs) == 1:
        return f"{float(sorted_kfs[0].value):.6f}"

    expanded: list[Keyframe | _FakeKeyframe] = []
    for index in range(len(sorted_kfs) - 1):
        left = sorted_kfs[index]
        right = sorted_kfs[index + 1]
        expanded.append(left)
        if left.interpolation == "bezier":
            for step_index in range(1, 8):
                t = step_index / 8.0
                eased = _cubic_bezier(
                    t,
                    left.bezier_cp1_dx,
                    left.bezier_cp1_dy,
                    left.bezier_cp2_dx,
                    left.bezier_cp2_dy,
                )
                inner_time = left.time_seconds + (right.time_seconds - left.time_seconds) * t
                inner_value = left.value + (right.value - left.value) * eased
                expanded.append(_FakeKeyframe(inner_time, inner_value))
    expanded.append(sorted_kfs[-1])

    expression = f"{float(expanded[-1].value):.6f}"
    for index in range(len(expanded) - 1, 0, -1):
        left = expanded[index - 1]
        right = expanded[index]
        span = max(1e-6, float(right.time_seconds) - float(left.time_seconds))
        if getattr(left, "interpolation", "linear") == "hold":
            segment = f"{float(left.value):.6f}"
        else:
            slope = (float(right.value) - float(left.value)) / span
            segment = f"({float(left.value):.6f}+({slope:.6f})*(t-{float(left.time_seconds):.6f}))"
        expression = f"if(lt(t\\,{float(right.time_seconds):.6f})\\,{segment}\\,{expression})"

    first = expanded[0]
    return f"if(lt(t\\,{float(first.time_seconds):.6f})\\,{float(first.value):.6f}\\,{expression})"
