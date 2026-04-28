from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

_NAV_COLUMN_WIDTH = 112


class RailLibraryPanel(QWidget):
    """Sidebar wrapper that mirrors the captions import-only layout."""

    def __init__(
        self,
        content_widget: QWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._content_widget = content_widget

        self.setObjectName("captionsPanel")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        left_column = QWidget(self)
        left_column.setObjectName("captions_left_column")
        left_column.setFixedWidth(_NAV_COLUMN_WIDTH)
        left_layout = QVBoxLayout(left_column)
        left_layout.setContentsMargins(8, 10, 8, 10)
        left_layout.setSpacing(8)

        self._import_nav_label = QLabel(self.tr("Nhập"), left_column)
        self._import_nav_label.setObjectName("captions_nav_label")
        self._import_nav_label.setProperty("active", True)
        self._import_nav_label.setCursor(Qt.CursorShape.ArrowCursor)
        left_layout.addWidget(self._import_nav_label)
        left_layout.addStretch(1)

        separator = QFrame(self)
        separator.setObjectName("captions_column_separator")
        separator.setFrameShape(QFrame.Shape.VLine)

        right_column = QWidget(self)
        right_column.setObjectName("captions_right_column")
        right_layout = QVBoxLayout(right_column)
        right_layout.setContentsMargins(10, 10, 8, 8)
        right_layout.setSpacing(0)

        import_page = QWidget(right_column)
        import_page.setObjectName("captions_import_page")
        import_layout = QVBoxLayout(import_page)
        import_layout.setContentsMargins(0, 0, 0, 0)
        import_layout.setSpacing(0)
        import_layout.addWidget(self._content_widget, 1)
        right_layout.addWidget(import_page, 1)

        layout.addWidget(left_column)
        layout.addWidget(separator)
        layout.addWidget(right_column, 1)

    def open_import_dialog(self) -> None:
        callback = getattr(self._content_widget, "open_import_dialog", None)
        if callable(callback):
            callback()

    def __getattr__(self, name: str):
        # Preserve compatibility for callers that accessed attributes on the
        # old concrete panel objects (for example media_list/import_button).
        return getattr(self._content_widget, name)
