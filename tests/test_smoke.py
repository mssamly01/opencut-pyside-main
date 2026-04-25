"""End-to-end smoke tests that exercise the full Qt startup path."""

from __future__ import annotations

from app.bootstrap import build_main_window, create_application
from app.domain.project import build_demo_project
from PySide6.QtCore import QTimer


def test_demo_project_builds() -> None:
    project = build_demo_project()
    assert project.name
    assert project.timeline.tracks
    total_duration = project.timeline.total_duration()
    assert total_duration > 0


def test_main_window_starts_and_exits() -> None:
    application = create_application([__name__])
    main_window = build_main_window()
    main_window.show()
    QTimer.singleShot(0, application.quit)
    exit_code = application.exec()
    assert exit_code == 0
