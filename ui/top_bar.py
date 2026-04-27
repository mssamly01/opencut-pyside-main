from __future__ import annotations

from app.ui.shared.icons import build_icon
from PySide6.QtCore import QEvent, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QAction, QMouseEvent
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLineEdit, QMenu, QPushButton, QToolButton, QWidget


class TopBar(QWidget):
    """Custom top bar with menu button, project name, and export button."""

    export_requested = Signal()
    project_name_commit_requested = Signal(str)
    minimize_requested = Signal()
    maximize_toggle_requested = Signal()
    close_requested = Signal()
    drag_started = Signal()
    maximize_toggle_via_doubleclick_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("top_bar")
        self.setFixedHeight(32)

        self._project_name_base = self.tr("Không có tiêu đề")
        self._project_name_committing = False

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

        self._project_name = QLineEdit(self._project_name_base, self)
        self._project_name.setObjectName("top_project_name")
        self._project_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._project_name.setFrame(False)
        self._project_name.setMaxLength(180)
        self._project_name.setFixedHeight(24)
        self._project_name.setMinimumWidth(180)
        self._project_name.setReadOnly(True)
        self._project_name.installEventFilter(self)
        self._project_name.returnPressed.connect(self._commit_project_name_change)
        self._project_name.editingFinished.connect(self._on_project_name_edit_finished)
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

        # Sprint 16-B: drag-to-move tracks press position so we can defer the
        # actual startSystemMove() until the user crosses the drag threshold.
        self._drag_press_global: QPoint | None = None
        self._drag_active = False

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
        self._project_name_base = (name or "").strip() or self.tr("Không có tiêu đề")
        _ = dirty
        if self._project_name.isReadOnly():
            self._refresh_project_name_display()

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
        return child is self._project_name and self._project_name.isReadOnly()

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched is self._project_name and event.type() == QEvent.Type.MouseButtonPress:
            if self._project_name.isReadOnly():
                self._begin_project_name_edit()
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def _begin_project_name_edit(self) -> None:
        self._project_name.setReadOnly(False)
        self._project_name.setText(self._project_name_base)
        self._project_name.setFocus(Qt.FocusReason.MouseFocusReason)
        self._project_name.selectAll()

    def _refresh_project_name_display(self) -> None:
        self._project_name.setText(self._project_name_base)
        self._project_name.setCursorPosition(0)

    def _on_project_name_edit_finished(self) -> None:
        self._commit_project_name_change()

    def _commit_project_name_change(self) -> None:
        if self._project_name.isReadOnly() or self._project_name_committing:
            return
        self._project_name_committing = True
        value = self._project_name.text().strip() or self._project_name_base
        previous = self._project_name_base
        self._project_name.setReadOnly(True)
        self._project_name.clearFocus()
        if value != previous:
            self._project_name_base = value
            self.project_name_commit_requested.emit(value)
        self._refresh_project_name_display()
        self._project_name_committing = False

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._is_drag_region(event):
            self._drag_press_global = event.globalPosition().toPoint()
            self._drag_active = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._drag_press_global is not None
            and not self._drag_active
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            current = event.globalPosition().toPoint()
            delta = current - self._drag_press_global
            if max(abs(delta.x()), abs(delta.y())) >= QApplication.startDragDistance():
                self._drag_active = True
                self.drag_started.emit()
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_press_global = None
            self._drag_active = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._is_drag_region(event):
            self._drag_press_global = None
            self._drag_active = False
            self.maximize_toggle_via_doubleclick_requested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
