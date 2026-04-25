from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class InspectorController(QObject):
    inspector_changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
