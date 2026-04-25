"""Unit tests for ``app.utils`` helpers.

These exercise pure-Python code paths so we can run them without Qt.
"""

from __future__ import annotations

import pytest
from app.utils.id_generator import generate_id, generate_raw_id
from app.utils.math_utils import clamp, inverse_lerp, lerp, map_range, snap
from app.utils.timecode import Timecode

# ---- math_utils -------------------------------------------------------


def test_clamp_within_bounds_returns_value():
    assert clamp(5, 0, 10) == 5


def test_clamp_below_bounds_clips_to_low():
    assert clamp(-3, 0, 10) == 0


def test_clamp_above_bounds_clips_to_high():
    assert clamp(42, 0, 10) == 10


def test_clamp_swaps_inverted_bounds():
    assert clamp(5, 10, 0) == 5
    assert clamp(-3, 10, 0) == 0


def test_lerp_endpoints():
    assert lerp(0.0, 10.0, 0.0) == 0.0
    assert lerp(0.0, 10.0, 1.0) == 10.0


def test_lerp_midpoint():
    assert lerp(0.0, 10.0, 0.5) == 5.0


def test_lerp_extrapolates_beyond_unit_t():
    assert lerp(0.0, 10.0, 2.0) == 20.0


def test_inverse_lerp_basic():
    assert inverse_lerp(0.0, 10.0, 2.5) == 0.25


def test_inverse_lerp_zero_range_returns_zero():
    assert inverse_lerp(5.0, 5.0, 5.0) == 0.0


def test_map_range():
    assert map_range(5, 0, 10, 100, 200) == 150


def test_snap_rounds_to_nearest_step():
    assert snap(1.23, 0.5) == 1.0
    assert snap(1.26, 0.5) == 1.5


def test_snap_with_zero_step_is_identity():
    assert snap(1.23, 0.0) == 1.23
    assert snap(1.23, -1.0) == 1.23


def test_snap_with_offset():
    assert snap(1.3, 0.5, offset=0.1) == 1.1
    assert snap(1.4, 0.5, offset=0.1) == 1.6


# ---- id_generator ----------------------------------------------------


def test_generate_raw_id_is_hex_and_correct_length():
    raw = generate_raw_id()
    assert len(raw) == 12
    assert all(c in "0123456789abcdef" for c in raw)


def test_generate_raw_id_is_collision_resistant():
    ids = {generate_raw_id() for _ in range(2000)}
    assert len(ids) == 2000


def test_generate_id_with_prefix():
    uid = generate_id("clip")
    assert uid.startswith("clip_")
    assert len(uid) == len("clip_") + 12


def test_generate_id_empty_prefix_returns_raw():
    uid = generate_id("")
    assert "_" not in uid
    assert len(uid) == 12


def test_generate_raw_id_rejects_out_of_range_entropy():
    with pytest.raises(ValueError):
        generate_raw_id(entropy_chars=2)
    with pytest.raises(ValueError):
        generate_raw_id(entropy_chars=64)


def test_generate_id_rejects_non_ascii_prefix():
    with pytest.raises(ValueError):
        generate_id("clip với dấu")


def test_generate_id_rejects_whitespace_prefix():
    with pytest.raises(ValueError):
        generate_id("my clip")


# ---- timecode --------------------------------------------------------


def test_timecode_from_seconds_rounds_to_nearest_frame():
    tc = Timecode.from_seconds(1.0, fps=30)
    assert tc.total_frames == 30
    assert tc.to_smpte() == "00:00:01:00"


def test_timecode_to_seconds_round_trip():
    tc = Timecode.from_seconds(2.5, fps=24)
    assert tc.to_seconds() == pytest.approx(2.5)


def test_timecode_formats_hours_minutes_seconds_frames():
    tc = Timecode.from_frames(3 * 3600 * 25 + 12 * 60 * 25 + 7 * 25 + 4, fps=25)
    assert tc.to_smpte() == "03:12:07:04"


def test_timecode_parses_smpte_string_with_colon():
    tc = Timecode.from_smpte("00:01:30:15", fps=30)
    assert tc.total_frames == (60 + 30) * 30 + 15
    assert str(tc) == "00:01:30:15"


def test_timecode_parses_drop_frame_separator_as_ndf():
    # Semicolon separator is accepted but currently treated as NDF.
    tc = Timecode.from_smpte("00:01:00;00", fps=29.97)
    assert tc.total_frames == 60 * 30


def test_timecode_rejects_invalid_format():
    with pytest.raises(ValueError):
        Timecode.from_smpte("garbage", fps=30)


def test_timecode_rejects_frame_part_at_or_above_fps():
    with pytest.raises(ValueError):
        Timecode.from_smpte("00:00:00:30", fps=30)


def test_timecode_rejects_negative_frames():
    with pytest.raises(ValueError):
        Timecode(total_frames=-1, fps=30)


def test_timecode_rejects_non_positive_fps():
    with pytest.raises(ValueError):
        Timecode.from_seconds(1.0, fps=0)
    with pytest.raises(ValueError):
        Timecode.from_seconds(1.0, fps=-1)


def test_timecode_fractional_fps_seconds_are_exact():
    # 30000 / 1001 = 29.97002997... so 1 real second ≈ 30 frames.
    fps = 30000 / 1001
    tc = Timecode.from_seconds(1.0, fps=fps)
    assert tc.total_frames == 30
    # Round-trip retains fractional precision up to rounding.
    assert tc.to_seconds() == pytest.approx(30 / fps)


def test_timecode_is_immutable():
    tc = Timecode(total_frames=10, fps=30)
    with pytest.raises(AttributeError):
        tc.total_frames = 20  # type: ignore[misc]
