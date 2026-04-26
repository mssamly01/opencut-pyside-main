"""Sprint 16-B: frameless window chrome (custom title bar + drag/resize)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.bootstrap import build_main_window, create_application
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent


def test_main_window_has_frameless_flag() -> None:
    create_application(["pytest"])
    window = build_main_window()
    try:
        assert bool(window.windowFlags() & Qt.WindowType.FramelessWindowHint)
    finally:
        window.close()


def test_top_bar_exposes_chrome_buttons() -> None:
    create_application(["pytest"])
    window = build_main_window()
    try:
        top_bar = window._top_bar
        assert top_bar is not None
        assert top_bar._minimize_button.objectName() == "top_minimize_button"
        assert top_bar._maximize_button.objectName() == "top_maximize_button"
        assert top_bar._close_button.objectName() == "top_close_button"
        assert top_bar._minimize_button.isEnabled()
        assert top_bar._maximize_button.isEnabled()
        assert top_bar._close_button.isEnabled()
    finally:
        window.close()


def test_max_button_icon_swaps_with_window_state() -> None:
    create_application(["pytest"])
    window = build_main_window()
    try:
        top_bar = window._top_bar
        assert top_bar is not None
        # Default state -> "Phóng to" tooltip (Maximize).
        assert top_bar._maximize_button.toolTip() == top_bar.tr("Phóng to")
        top_bar.set_maximized_state(True)
        assert top_bar._maximize_button.toolTip() == top_bar.tr("Khôi phục")
        top_bar.set_maximized_state(False)
        assert top_bar._maximize_button.toolTip() == top_bar.tr("Phóng to")
    finally:
        window.close()


def test_resize_edges_hit_corners_and_center() -> None:
    create_application(["pytest"])
    window = build_main_window()
    try:
        window.resize(800, 600)
        # Top-left corner is inside the 4 px border: should report Top|Left.
        edges = window._resize_edges_at(QPoint(2, 2))
        assert edges is not None
        assert bool(edges & Qt.Edge.TopEdge)
        assert bool(edges & Qt.Edge.LeftEdge)
        # Centre of the window: no resize edges.
        assert window._resize_edges_at(QPoint(400, 300)) is None
    finally:
        window.close()


def test_event_filter_press_at_edge_triggers_system_resize() -> None:
    create_application(["pytest"])
    window = build_main_window()
    try:
        window.resize(800, 600)
        window.show()
        window.activateWindow()
        window.isActiveWindow = MagicMock(return_value=True)  # type: ignore[method-assign]
        # The eventFilter relies on the live window handle to delegate the
        # resize to the compositor; we stub it out and verify it gets called
        # with the correct edges when the press lands inside the 4 px border.
        fake_handle = MagicMock()
        window.windowHandle = MagicMock(return_value=fake_handle)  # type: ignore[method-assign]
        global_pt = window.mapToGlobal(QPoint(2, 2))
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(2.0, 2.0),
            QPointF(global_pt),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        consumed = window.eventFilter(window, press)
        assert consumed is True
        fake_handle.startSystemResize.assert_called_once()
        edges_arg = fake_handle.startSystemResize.call_args.args[0]
        assert bool(edges_arg & Qt.Edge.TopEdge)
        assert bool(edges_arg & Qt.Edge.LeftEdge)
    finally:
        window.close()


def test_event_filter_press_at_center_is_ignored() -> None:
    create_application(["pytest"])
    window = build_main_window()
    try:
        window.resize(800, 600)
        window.show()
        window.activateWindow()
        window.isActiveWindow = MagicMock(return_value=True)  # type: ignore[method-assign]
        fake_handle = MagicMock()
        window.windowHandle = MagicMock(return_value=fake_handle)  # type: ignore[method-assign]
        centre_global = window.mapToGlobal(QPoint(400, 300))
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(400.0, 300.0),
            QPointF(centre_global),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        consumed = window.eventFilter(window, press)
        assert consumed is False
        fake_handle.startSystemResize.assert_not_called()
    finally:
        window.close()


def test_event_filter_does_not_steal_clicks_when_window_inactive() -> None:
    create_application(["pytest"])
    window = build_main_window()
    try:
        window.resize(800, 600)
        window.show()
        # Simulate a modal dialog being on top: MainWindow is no longer the
        # active window, so the resize-edge press should NOT be consumed.
        window.isActiveWindow = MagicMock(return_value=False)  # type: ignore[method-assign]
        fake_handle = MagicMock()
        window.windowHandle = MagicMock(return_value=fake_handle)  # type: ignore[method-assign]
        global_pt = window.mapToGlobal(QPoint(2, 2))
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(2.0, 2.0),
            QPointF(global_pt),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        consumed = window.eventFilter(window, press)
        assert consumed is False
        fake_handle.startSystemResize.assert_not_called()
    finally:
        window.close()


def test_toggle_maximized_alternates_state() -> None:
    create_application(["pytest"])
    window = build_main_window()
    try:
        # On the offscreen platform showMaximized may be a no-op for the
        # window manager, but `windowState` still reflects the request.
        window.showNormal()
        window._toggle_maximized()
        assert window.isMaximized()
        window._toggle_maximized()
        assert not window.isMaximized()
    finally:
        window.close()
