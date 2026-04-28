"""Hover-scrub behaviour on the timeline view.

When enabled (off by default), moving the mouse over the ruler / clip area
should seek the preview to that time without requiring a click. Throttled
so a fast cursor sweep doesn't decode every intermediate frame.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.bootstrap import create_application
from app.controllers.app_controller import AppController
from app.ui.timeline.timeline_view import TimelineView
from PySide6.QtCore import Qt


def _build_view() -> tuple[TimelineView, AppController]:
    create_application(["pytest"])
    app_controller = AppController()
    view = TimelineView(
        app_controller.timeline_controller,
        app_controller.playback_controller,
        app_controller.selection_controller,
        app_controller.thumbnail_service,
        app_controller.waveform_service,
    )
    return view, app_controller


def _event(*, x: float, buttons=Qt.MouseButton.NoButton, timestamp_ms: int):
    return SimpleNamespace(
        position=lambda: SimpleNamespace(x=lambda: x),
        buttons=lambda: buttons,
        timestamp=lambda: timestamp_ms,
    )


def test_set_hover_scrub_enabled_round_trips() -> None:
    view, _app = _build_view()
    assert view.hover_scrub_enabled() is False
    view.set_hover_scrub_enabled(True)
    assert view.hover_scrub_enabled() is True
    view.set_hover_scrub_enabled(False)
    assert view.hover_scrub_enabled() is False


def test_hover_scrub_no_op_when_disabled() -> None:
    view, _app = _build_view()
    with patch.object(view, "_seek_to_scene_x") as seek:
        view._maybe_hover_scrub(  # noqa: SLF001
            _event(x=200.0, timestamp_ms=1000),
            scene_pos=SimpleNamespace(x=lambda: 200.0),
        )
    seek.assert_not_called()


def test_hover_scrub_seeks_when_enabled_over_content() -> None:
    view, _app = _build_view()
    view.set_hover_scrub_enabled(True)
    with patch.object(view, "_seek_to_scene_x") as seek:
        view._maybe_hover_scrub(  # noqa: SLF001
            _event(x=200.0, timestamp_ms=1000),
            scene_pos=SimpleNamespace(x=lambda: 200.0),
        )
    seek.assert_called_once_with(200.0)


def test_hover_scrub_skipped_when_button_held() -> None:
    """A button down means the user is dragging/scrubbing already."""

    view, _app = _build_view()
    view.set_hover_scrub_enabled(True)
    with patch.object(view, "_seek_to_scene_x") as seek:
        view._maybe_hover_scrub(  # noqa: SLF001
            _event(x=200.0, buttons=Qt.MouseButton.LeftButton, timestamp_ms=1000),
            scene_pos=SimpleNamespace(x=lambda: 200.0),
        )
    seek.assert_not_called()


def test_hover_scrub_skipped_over_track_header_gutter() -> None:
    view, _app = _build_view()
    view.set_hover_scrub_enabled(True)
    # Move into the header gutter (viewport_x <= scene.left_gutter).
    gutter_x = view._timeline_scene.left_gutter - 5  # noqa: SLF001
    with patch.object(view, "_seek_to_scene_x") as seek:
        view._maybe_hover_scrub(  # noqa: SLF001
            _event(x=gutter_x, timestamp_ms=1000),
            scene_pos=SimpleNamespace(x=lambda: gutter_x),
        )
    seek.assert_not_called()


def test_hover_scrub_throttled_within_window() -> None:
    view, _app = _build_view()
    view.set_hover_scrub_enabled(True)
    with patch.object(view, "_seek_to_scene_x") as seek:
        view._maybe_hover_scrub(  # noqa: SLF001
            _event(x=200.0, timestamp_ms=1000),
            scene_pos=SimpleNamespace(x=lambda: 200.0),
        )
        # 10ms later — well below the 40ms throttle.
        view._maybe_hover_scrub(  # noqa: SLF001
            _event(x=210.0, timestamp_ms=1010),
            scene_pos=SimpleNamespace(x=lambda: 210.0),
        )
    assert seek.call_count == 1


def test_hover_scrub_fires_again_after_throttle_window() -> None:
    view, _app = _build_view()
    view.set_hover_scrub_enabled(True)
    with patch.object(view, "_seek_to_scene_x") as seek:
        view._maybe_hover_scrub(  # noqa: SLF001
            _event(x=200.0, timestamp_ms=1000),
            scene_pos=SimpleNamespace(x=lambda: 200.0),
        )
        # 50ms later — past the 40ms throttle.
        view._maybe_hover_scrub(  # noqa: SLF001
            _event(x=300.0, timestamp_ms=1050),
            scene_pos=SimpleNamespace(x=lambda: 300.0),
        )
    assert seek.call_count == 2


def test_set_hover_scrub_enabled_resets_throttle_clock() -> None:
    """Toggling off then on must let the next hover seek immediately even
    if a stale ``_hover_scrub_last_seek_ms`` is lingering."""

    view, _app = _build_view()
    view.set_hover_scrub_enabled(True)
    view._hover_scrub_last_seek_ms = 9_999_999  # noqa: SLF001

    view.set_hover_scrub_enabled(False)
    view.set_hover_scrub_enabled(True)

    with patch.object(view, "_seek_to_scene_x") as seek:
        view._maybe_hover_scrub(  # noqa: SLF001
            _event(x=200.0, timestamp_ms=1000),
            scene_pos=SimpleNamespace(x=lambda: 200.0),
        )
    seek.assert_called_once()
