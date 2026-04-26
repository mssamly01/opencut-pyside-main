from __future__ import annotations

from app.ui.effects_drawer import EffectsDrawer
from PySide6.QtWidgets import QVBoxLayout, QWidget


class TransitionsPanel(QWidget):
    """Sidebar wrapper hosting the draggable transition buttons."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(EffectsDrawer(self))
