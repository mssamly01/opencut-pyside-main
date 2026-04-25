from __future__ import annotations

from app.ui.sidebar.left_rail import RAIL_CATEGORIES
from app.ui.sidebar.placeholder_panel import PlaceholderPanel
from PySide6.QtWidgets import QStackedWidget, QWidget


class LeftSidebarStack(QStackedWidget):
    """Stack of sidebar panels, keyed by LeftRail category."""

    def __init__(self, media_panel: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("leftSidebarStack")
        self._key_to_index: dict[str, int] = {}

        for key, label, _icon_name in RAIL_CATEGORIES:
            panel = media_panel if key == "media" else PlaceholderPanel(label, self)
            index = self.addWidget(panel)
            self._key_to_index[key] = index

    def show_category(self, key: str) -> None:
        index = self._key_to_index.get(key)
        if index is None:
            return
        self.setCurrentIndex(index)

