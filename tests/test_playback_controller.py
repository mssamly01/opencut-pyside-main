from __future__ import annotations

from app.controllers.playback_controller import PlaybackController


def test_preview_refresh_interval_matches_project_fps() -> None:
    assert PlaybackController._preview_refresh_interval_ms_for_fps(30.0) == 33
    assert PlaybackController._preview_refresh_interval_ms_for_fps(60.0) == 17


def test_preview_refresh_interval_is_clamped() -> None:
    assert PlaybackController._preview_refresh_interval_ms_for_fps(0.0) == 33
    assert PlaybackController._preview_refresh_interval_ms_for_fps(5.0) == 120
    assert PlaybackController._preview_refresh_interval_ms_for_fps(240.0) == 16
