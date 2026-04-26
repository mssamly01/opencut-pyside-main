"""Sprint 1 chrome tests: icons, window shell, sticky header, media grid thumbnails."""

from __future__ import annotations

from app.bootstrap import build_main_window, create_application
from app.domain.project import build_demo_project
from app.services.thumbnail_service import ThumbnailService
from app.ui.shared.icons import build_icon, build_pixmap
from app.ui.timeline.timeline_scene import TimelineScene
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter


def test_build_icon_renders_non_empty_pixmap() -> None:
    create_application(["pytest"])
    icon = build_icon("save", color="#ffffff")
    pixmap = icon.pixmap(24, 24)
    assert not pixmap.isNull()
    assert pixmap.width() == 24


def test_build_pixmap_unknown_glyph_returns_transparent() -> None:
    create_application(["pytest"])
    pixmap = build_pixmap("does-not-exist", 16)
    assert pixmap.width() == 16
    image = pixmap.toImage()
    assert image.pixelColor(0, 0).alpha() == 0


def test_main_window_has_topbar_statusbar_and_timecode() -> None:
    application = create_application(["pytest"])
    main_window = build_main_window()

    # Sprint 11+: menubar is hidden and actions are moved to TopBar popup.
    menu_bar = main_window.menuBar()
    assert menu_bar is not None
    assert not menu_bar.isVisible()
    assert main_window._top_bar is not None
    top_menu = main_window._top_bar._menu_button.menu()
    assert top_menu is not None
    action_texts = [action.text() for action in top_menu.actions() if not action.isSeparator()]
    # Sprint 16-D: Vietnamese is the source language; UI labels default to VI.
    assert "Lưu" in action_texts
    assert "Hoàn tác" in action_texts
    assert "Thoát" in action_texts

    assert main_window.statusBar() is not None
    main_window._refresh_timecode(3723.456)
    assert main_window._timecode_label is not None
    assert main_window._timecode_label.text() == "01:02:03.456"

    main_window._refresh_timecode(0.0)
    assert main_window._timecode_label.text() == "00:00:00.000"
    application.quit()


def test_sticky_header_renders_at_visible_rect_left() -> None:
    create_application(["pytest"])
    scene = TimelineScene(
        project=build_demo_project(),
        project_path=None,
        thumbnail_service=ThumbnailService(),
        waveform_service=None,
    )
    image = QImage(800, 400, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    visible_rect = QRectF(400.0, 0.0, 800.0, 400.0)
    painter.translate(-visible_rect.left(), 0.0)
    scene.drawForeground(painter, visible_rect)
    painter.end()

    sample = image.pixelColor(10, 60)
    assert sample.red() < 70 and sample.green() < 80 and sample.blue() < 95


def test_media_panel_builds_with_demo_project_and_icons() -> None:
    from app.controllers.app_controller import AppController
    from app.ui.media_panel.media_panel import MediaPanel

    application = create_application(["pytest"])
    app_controller = AppController()
    app_controller.project_controller.set_active_project(build_demo_project())

    panel = MediaPanel(
        app_controller.project_controller,
        parent=None,
        thumbnail_service=app_controller.thumbnail_service,
    )
    assert panel.media_list.count() > 0
    for index in range(panel.media_list.count()):
        item = panel.media_list.item(index)
        assert not item.icon().isNull()
    application.quit()
