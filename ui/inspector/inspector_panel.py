from __future__ import annotations

from app.controllers.app_controller import AppController
from app.ui.inspector.details_inspector import DetailsInspector
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QScrollArea, QVBoxLayout, QWidget


class InspectorPanel(QWidget):
    """Inspector panel with contextual subtitle tab."""

    def __init__(self, app_controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app_controller = app_controller

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self._toggle_row = QWidget(self)
        self._toggle_row.setObjectName("inspector_toggle_row")
        toggle_layout = QHBoxLayout(self._toggle_row)
        toggle_layout.setContentsMargins(8, 6, 8, 4)
        toggle_layout.setSpacing(4)

        self._subtitle_button = QPushButton(self.tr("Phụ đề"), self._toggle_row)
        self._subtitle_button.setObjectName("inspector_toggle_button")
        self._subtitle_button.setCheckable(True)
        self._subtitle_button.setChecked(False)
        self._subtitle_button.setEnabled(False)
        self._subtitle_button.setVisible(False)
        toggle_layout.addWidget(self._subtitle_button)
        toggle_layout.addStretch(1)
        outer_layout.addWidget(self._toggle_row)
        self._toggle_row.setVisible(False)

        details_scroll = QScrollArea(self)
        details_scroll.setWidgetResizable(True)
        details_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        details_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._details_inspector = DetailsInspector(app_controller, details_scroll)
        details_scroll.setWidget(self._details_inspector)
        outer_layout.addWidget(details_scroll, 1)

        self._app_controller.subtitle_selection_changed.connect(self._sync_mode)
        self._app_controller.selection_controller.selection_changed.connect(self._sync_mode)
        self._sync_mode()

    def _sync_mode(self) -> None:
        has_subtitle_selection = self._app_controller.selected_subtitle_segment() is not None
        self._toggle_row.setVisible(has_subtitle_selection)
        self._subtitle_button.setVisible(has_subtitle_selection)
        self._subtitle_button.setChecked(has_subtitle_selection)
        if has_subtitle_selection:
            self._details_inspector.set_mode(DetailsInspector.MODE_SUBTITLES)
            return
        self._details_inspector.set_mode(DetailsInspector.MODE_DETAILS)
