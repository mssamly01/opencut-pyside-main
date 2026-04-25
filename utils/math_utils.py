"""Pure-Python numeric helpers used across the editor.

These live in ``app.utils`` so they must not import PySide6 or any other
non-stdlib dependency — they need to be trivially testable and usable from
headless tooling (CI builders, exporters, pre-commit hooks, etc.).
"""

from __future__ import annotations

__all__ = [
    "clamp",
    "inverse_lerp",
    "lerp",
    "map_range",
    "snap",
]


def clamp(value: float, low: float, high: float) -> float:
    """Constrain ``value`` to the closed interval ``[low, high]``.

    If ``low > high`` the bounds are swapped so the function never crashes
    on a badly-ordered range — useful when the bounds themselves come from
    user input (trim handles, inspector spin boxes, keyframe editor).
    """
    if low > high:
        low, high = high, low
    if value < low:
        return low
    if value > high:
        return high
    return value


def lerp(a: float, b: float, t: float) -> float:
    """Linearly interpolate between ``a`` and ``b`` by parameter ``t``.

    ``t`` is not clamped — callers that need a clamped version should wrap
    the result with :func:`clamp`. This mirrors the behaviour most shader
    languages and animation systems expect.
    """
    return a + (b - a) * t


def inverse_lerp(a: float, b: float, value: float) -> float:
    """Return the ``t`` such that ``lerp(a, b, t) == value``.

    Returns ``0.0`` when ``a == b`` rather than raising — this matches the
    common "progress bar" use case where a zero-length range should simply
    report "done".
    """
    if a == b:
        return 0.0
    return (value - a) / (b - a)


def map_range(
    value: float,
    from_low: float,
    from_high: float,
    to_low: float,
    to_high: float,
) -> float:
    """Re-map ``value`` from ``[from_low, from_high]`` to ``[to_low, to_high]``."""
    return lerp(to_low, to_high, inverse_lerp(from_low, from_high, value))


def snap(value: float, step: float, offset: float = 0.0) -> float:
    """Snap ``value`` to the nearest multiple of ``step`` (plus ``offset``).

    Used by the timeline snap engine and by inspector controls that quantise
    keyframes / trims to the project's frame grid. A non-positive ``step``
    disables snapping and returns ``value`` unchanged.
    """
    if step <= 0:
        return value
    return offset + round((value - offset) / step) * step
