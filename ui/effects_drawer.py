from __future__ import annotations

from app.controllers.app_controller import AppController
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

_PRESET_BUTTONS: list[tuple[str, str]] = [
    ("none", "Reset"),
    ("warm", "Warm"),
    ("cool", "Cool"),
    ("sepia", "Sepia"),
    ("bw", "B&W"),
    ("vivid", "Vivid"),
]


class EffectsDrawer(QWidget):
    def __init__(self, app_controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app_controller = app_controller

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("Quick Effects", self)
        title.setStyleSheet("font-weight: 600;")
        layout.addWidget(title)

        self._hint = QLabel("Select a clip, then apply a preset.", self)
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("color: #7a8794;")
        layout.addWidget(self._hint)

        for preset, label in _PRESET_BUTTONS:
            button = QPushButton(label, self)
            button.setProperty("preset_name", preset)
            button.clicked.connect(self._on_preset_clicked)
            layout.addWidget(button)
        layout.addStretch(1)

        self._app_controller.selection_controller.selection_changed.connect(self._refresh_hint)
        self._refresh_hint()

    def _refresh_hint(self) -> None:
        selected = self._app_controller.selection_controller.selected_clip_ids()
        if not selected:
            self._hint.setText("Select a clip, then apply a preset.")
            return
        if len(selected) == 1:
            self._hint.setText("Preset will apply to selected clip.")
            return
        self._hint.setText(f"Preset will apply to {len(selected)} selected clips.")

    def _on_preset_clicked(self) -> None:
        sender = self.sender()
        if not isinstance(sender, QPushButton):
            return
        preset = str(sender.property("preset_name") or "none")
        selected_ids = self._app_controller.selection_controller.selected_clip_ids()
        if not selected_ids:
            return
        for clip_id in selected_ids:
            self._app_controller.timeline_controller.apply_clip_color_preset(clip_id, preset)
