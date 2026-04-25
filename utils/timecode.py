"""SMPTE-style non-drop-frame timecode value object.

Prosumer editors expose timecode everywhere (ruler, playback toolbar,
inspector, export dialog) and expect frame-accurate round-trips between
seconds, frame indices and ``HH:MM:SS:FF`` strings. This module centralises
that conversion so the UI layer stays dumb.

Scope for v1.0:

* Non-drop-frame (NDF) timecode with integer and fractional frame rates
  (23.976, 24, 25, 29.97, 30, 50, 59.94, 60). Fractional rates use the
  nominal integer FPS for the structural ``HH:MM:SS:FF`` split and the exact
  FPS only for the ``seconds <-> frames`` conversion.
* Drop-frame (DF) timecode (shown with a ``;`` separator for 29.97 / 59.94)
  is parsed leniently — the semicolon is accepted but treated as NDF. A
  dedicated DF implementation is planned for Sprint 6 (ROADMAP M3).

The class is immutable (``frozen=True``) so it can be used freely as a
dict key or passed between threads without synchronisation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["Timecode"]

_TIMECODE_RE = re.compile(r"^(\d{1,2}):(\d{2}):(\d{2})[:;](\d{1,3})$")


@dataclass(frozen=True, slots=True)
class Timecode:
    """An immutable ``(total_frames, fps)`` pair with SMPTE formatting."""

    total_frames: int
    fps: float

    def __post_init__(self) -> None:
        if self.fps <= 0:
            raise ValueError(f"fps must be positive, got {self.fps}")
        if self.total_frames < 0:
            raise ValueError(
                f"total_frames must be non-negative, got {self.total_frames}"
            )

    # --- Construction ---------------------------------------------------

    @classmethod
    def from_seconds(cls, seconds: float, fps: float) -> Timecode:
        """Build a timecode from a time-in-seconds (rounded to nearest frame)."""
        if seconds < 0:
            raise ValueError(f"seconds must be non-negative, got {seconds}")
        if fps <= 0:
            raise ValueError(f"fps must be positive, got {fps}")
        frames = int(round(seconds * fps))
        return cls(total_frames=frames, fps=fps)

    @classmethod
    def from_frames(cls, frames: int, fps: float) -> Timecode:
        return cls(total_frames=frames, fps=fps)

    @classmethod
    def from_smpte(cls, text: str, fps: float) -> Timecode:
        """Parse an ``HH:MM:SS:FF`` (or ``HH:MM:SS;FF``) string."""
        if fps <= 0:
            raise ValueError(f"fps must be positive, got {fps}")
        match = _TIMECODE_RE.match(text.strip())
        if match is None:
            raise ValueError(f"invalid SMPTE timecode: {text!r}")
        hours, minutes, seconds, frames = (int(part) for part in match.groups())
        nominal_fps = _nominal_fps(fps)
        if minutes >= 60 or seconds >= 60:
            raise ValueError(f"out-of-range minute/second in timecode: {text!r}")
        if frames >= nominal_fps:
            raise ValueError(
                f"frame part {frames} exceeds nominal fps {nominal_fps} in {text!r}"
            )
        total = (
            hours * nominal_fps * 3600
            + minutes * nominal_fps * 60
            + seconds * nominal_fps
            + frames
        )
        return cls(total_frames=total, fps=fps)

    # --- Conversion -----------------------------------------------------

    def to_seconds(self) -> float:
        return self.total_frames / self.fps

    def to_smpte(self) -> str:
        """Return an ``HH:MM:SS:FF`` representation (always NDF for now)."""
        nominal_fps = _nominal_fps(self.fps)
        frames = self.total_frames
        hours, frames = divmod(frames, nominal_fps * 3600)
        minutes, frames = divmod(frames, nominal_fps * 60)
        seconds, frame_part = divmod(frames, nominal_fps)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frame_part:02d}"

    # --- Python protocol ------------------------------------------------

    def __str__(self) -> str:
        return self.to_smpte()


def _nominal_fps(fps: float) -> int:
    """Return the integer "nominal" frame rate used for timecode structure.

    29.97 -> 30, 23.976 -> 24, 59.94 -> 60, 25 -> 25, etc. This is how SMPTE
    12M splits a wall-clock fractional rate into whole-frame HH:MM:SS:FF
    buckets; the fractional rate is preserved separately for seconds
    conversion so ``from_seconds`` / ``to_seconds`` stay exact.
    """
    nominal = int(round(fps))
    if nominal <= 0:
        raise ValueError(f"nominal fps must be positive, got {nominal} (fps={fps})")
    return nominal
