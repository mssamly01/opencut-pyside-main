from __future__ import annotations

from app.ui.shared.icons import build_icon
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QPushButton, QToolButton, QWidget


class TopBar(QWidget):
    """Custom top bar with menu button, project name, and export button."""

    export_requested = Signal()
    minimize_requested = Signal()
    maximize_toggle_requested = Signal()
    close_requested = Signal()
    drag_started = Signal()
    maximize_toggle_via_doubleclick_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("top_bar")
        self.setFixedHeight(32)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(8)

        self._menu_button = QToolButton(self)
        self._menu_button.setObjectName("top_menu_button")
        self._menu_button.setText("☰")
        self._menu_button.setToolTip(self.tr("Menu"))
        self._menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._menu_button.setFixedSize(28, 24)
        self._menu = QMenu(self._menu_button)
        self._menu_button.setMenu(self._menu)
        layout.addWidget(self._menu_button)

        layout.addStretch(1)

        self._project_name = QLabel(self.tr("Không có tiêu đề"), self)
        self._project_name.setObjectName("top_project_name")
        self._project_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._project_name)

        layout.addStretch(1)

        self._export_button = QPushButton(self.tr("Xuất"), self)
        self._export_button.setObjectName("top_export_button")
        self._export_button.clicked.connect(self.export_requested.emit)
        layout.addWidget(self._export_button)

        # Sprint 16-B: window chrome controls (min / max-restore / close).
        self._minimize_button = self._build_chrome_button(
            "window-min",
            self.tr("Thu nhỏ"),
            self.minimize_requested,
            object_name="top_minimize_button",
        )
        layout.addWidget(self._minimize_button)

        self._maximize_button = self._build_chrome_button(
            "window-max",
            self.tr("Phóng to"),
            self.maximize_toggle_requested,
            object_name="top_maximize_button",
        )
        layout.addWidget(self._maximize_button)

        self._close_button = self._build_chrome_button(
            "window-close",
            self.tr("Đóng"),
            self.close_requested,
            object_name="top_close_button",
        )
        self._close_button.setProperty("chromeRole", "close")
        layout.addWidget(self._close_button)

    def _build_chrome_button(
        self,
        icon_name: str,
        tooltip: str,
        signal: Signal,
        *,
        object_name: str,
    ) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName(object_name)
        button.setIcon(build_icon(icon_name))
        button.setIconSize(QSize(14, 14))
        button.setFixedSize(28, 24)
        button.setToolTip(tooltip)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(signal.emit)
        return button

    def set_maximized_state(self, maximized: bool) -> None:
        """Swap the max/restore icon to mirror the window state."""
        if maximized:
            self._maximize_button.setIcon(build_icon("window-restore"))
            self._maximize_button.setToolTip(self.tr("Khôi phục"))
        else:
            self._maximize_button.setIcon(build_icon("window-max"))
            self._maximize_button.setToolTip(self.tr("Phóng to"))

    def clear_menu(self) -> None:
        self._menu.clear()

    def set_project_name(self, name: str, dirty: bool = False) -> None:
        suffix = " *" if dirty else ""
        self._project_name.setText((name or self.tr("Không có tiêu đề")) + suffix)

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

    # Sprint 16-B: drag-to-move on empty regions of the title bar.
    def _is_drag_region(self, event: QMouseEvent) -> bool:
        child = self.childAt(event.position().toPoint())
        if child is None:
            return True
        # Allow drag when the press lands on the project-name label or the
        # bar background; buttons (menu, export, chrome) keep their own clicks.
        return child is self._project_name

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._is_drag_region(event):
            self.drag_started.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._is_drag_region(event):
            self.maximize_toggle_via_doubleclick_requested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
