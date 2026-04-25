from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.controllers.app_controller import AppController
from app.infrastructure.translation_manager import install_translators
from app.ui.main_window import MainWindow
from app.ui.shared.theme import apply_basic_theme
from PySide6.QtCore import QTranslator
from PySide6.QtWidgets import QApplication


@dataclass(slots=True)
class AppContext:
    app_controller: AppController
    translators: list[QTranslator] = field(default_factory=list)


def build_app_context() -> AppContext:
    return AppContext(app_controller=AppController())


def create_application(
    argv: Sequence[str] | None = None,
    language: str | None = None,
) -> QApplication:
    existing_app = QApplication.instance()
    if existing_app is not None:
        return existing_app

    app = QApplication(list(argv) if argv is not None else [])
    app.setApplicationName("OpenCut PySide")
    app.setOrganizationName("OpenCut")
    # Install translators before building any widget so their tr()
    # lookups see the loaded QTranslator. We stash the list on the app
    # as a dynamic property so Qt keeps owning it for the app's lifetime.
    translators = install_translators(app, language=language)
    app.setProperty("opencut_translators", translators)
    apply_basic_theme(app)
    return app


def build_main_window(context: AppContext | None = None) -> MainWindow:
    resolved_context = context or build_app_context()
    return MainWindow(app_controller=resolved_context.app_controller)
