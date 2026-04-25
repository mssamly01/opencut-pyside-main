from __future__ import annotations

from app.controllers.app_controller import AppController
from app.ui.inspector.details_inspector import DetailsInspector
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget


class InspectorPanel(QWidget):
    """Sprint 11 readonly details inspector panel."""

    def __init__(self, app_controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        outer_layout.addWidget(scroll)

        details = DetailsInspector(app_controller, scroll)
        scroll.setWidget(details)
