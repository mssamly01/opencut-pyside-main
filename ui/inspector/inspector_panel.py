from __future__ import annotations

from app.controllers.app_controller import AppController
from app.ui.inspector.details_inspector import DetailsInspector
from app.ui.inspector.editor_inspector_page import EditorInspectorPage
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget


class InspectorPanel(QWidget):
    """Inspector with Details/Edit toggle."""

    _MODE_DETAILS = 0
    _MODE_EDIT = 1

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

        self._details_button = QPushButton(self.tr("Chi tiết"), toggle_row)
        self._details_button.setObjectName("inspector_toggle_button")
        self._details_button.setCheckable(True)
        self._details_button.setChecked(True)

        self._edit_button = QPushButton(self.tr("Chỉnh sửa"), toggle_row)
        self._edit_button.setObjectName("inspector_toggle_button")
        self._edit_button.setCheckable(True)

        self._toggle_group = QButtonGroup(self)
        self._toggle_group.setExclusive(True)
        self._toggle_group.addButton(self._details_button, self._MODE_DETAILS)
        self._toggle_group.addButton(self._edit_button, self._MODE_EDIT)
        self._toggle_group.buttonClicked.connect(self._on_toggle_clicked)

        toggle_layout.addWidget(self._details_button)
        toggle_layout.addWidget(self._edit_button)
        toggle_layout.addStretch(1)
        outer_layout.addWidget(toggle_row)

        self._stack = QStackedWidget(self)
        outer_layout.addWidget(self._stack, 1)

        details_scroll = QScrollArea(self._stack)
        details_scroll.setWidgetResizable(True)
        details_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        details_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        details_scroll.setWidget(DetailsInspector(app_controller, details_scroll))
        self._stack.insertWidget(self._MODE_DETAILS, details_scroll)

        edit_scroll = QScrollArea(self._stack)
        edit_scroll.setWidgetResizable(True)
        edit_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        edit_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        edit_scroll.setWidget(EditorInspectorPage(app_controller, edit_scroll))
        self._stack.insertWidget(self._MODE_EDIT, edit_scroll)

        self._stack.setCurrentIndex(self._MODE_DETAILS)

    def _on_toggle_clicked(self, button) -> None:
        mode_id = self._toggle_group.id(button)
        self._stack.setCurrentIndex(mode_id)
