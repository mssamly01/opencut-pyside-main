from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PlaceholderPanel(QWidget):
    """Sprint 9 placeholder for categories to be wired in Sprint 10."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 24, 16, 24)

        message = QLabel(f"{label}\n\nComing soon - Sprint 10", self)
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message.setWordWrap(True)
        layout.addWidget(message)
        layout.addStretch(1)

