from __future__ import annotations

from app.controllers.app_controller import AppController
from app.ui.inspector.details_inspector import DetailsInspector
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QScrollArea, QVBoxLayout, QWidget


class InspectorPanel(QWidget):
    """Inspector panel with a single 'Chi tiết' mode."""

    def __init__(self, app_controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        toggle_row = QWidget(self)
        toggle_row.setObjectName("inspector_toggle_row")
        toggle_layout = QHBoxLayout(toggle_row)
        toggle_layout.setContentsMargins(8, 6, 8, 4)
        toggle_layout.setSpacing(4)

        details_button = QPushButton(self.tr("Chi tiết"), toggle_row)
        details_button.setObjectName("inspector_toggle_button")
        details_button.setCheckable(True)
        details_button.setChecked(True)
        details_button.setEnabled(False)
        toggle_layout.addWidget(details_button)
        toggle_layout.addStretch(1)
        outer_layout.addWidget(toggle_row)

        details_scroll = QScrollArea(self)
        details_scroll.setWidgetResizable(True)
        details_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        details_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        details_scroll.setWidget(DetailsInspector(app_controller, details_scroll))
        outer_layout.addWidget(details_scroll, 1)
