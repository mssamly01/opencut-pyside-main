from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QPushButton, QToolButton, QWidget


class TopBar(QWidget):
    """Custom top bar with menu button, project name, and export button."""

    export_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("top_bar")
        self.setFixedHeight(32)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)

        self._menu_button = QToolButton(self)
        self._menu_button.setObjectName("top_menu_button")
        self._menu_button.setText("☰")
        self._menu_button.setToolTip("Menu")
        self._menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._menu_button.setFixedSize(28, 24)
        self._menu = QMenu(self._menu_button)
        self._menu_button.setMenu(self._menu)
        layout.addWidget(self._menu_button)

        layout.addStretch(1)

        self._project_name = QLabel("Untitled", self)
        self._project_name.setObjectName("top_project_name")
        self._project_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._project_name)

        layout.addStretch(1)

        self._export_button = QPushButton("Export", self)
        self._export_button.setObjectName("top_export_button")
        self._export_button.clicked.connect(self.export_requested.emit)
        layout.addWidget(self._export_button)

    def clear_menu(self) -> None:
        self._menu.clear()

    def set_project_name(self, name: str, dirty: bool = False) -> None:
        suffix = " *" if dirty else ""
        self._project_name.setText((name or "Untitled") + suffix)

    def set_export_enabled(self, enabled: bool) -> None:
        self._export_button.setEnabled(enabled)

    def add_menu_section(self, title: str, actions: list[QAction]) -> None:
        if not actions:
            return
        if not self._menu.isEmpty():
            self._menu.addSeparator()
        self._menu.addSection(title)
        for action in actions:
            self._menu.addAction(action)
