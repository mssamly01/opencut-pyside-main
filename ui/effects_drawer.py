from __future__ import annotations

from app.controllers.app_controller import AppController
from PySide6.QtCore import QMimeData, QPoint, Qt
from PySide6.QtGui import QDrag, QMouseEvent, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

_PRESET_BUTTONS: list[tuple[str, str]] = [
    ("none", "Reset"),
    ("warm", "Warm"),
    ("cool", "Cool"),
    ("sepia", "Sepia"),
    ("bw", "B&W"),
    ("vivid", "Vivid"),
]

_TRANSITION_BUTTONS: list[tuple[str, str]] = [
    ("cross_dissolve", "Dissolve"),
    ("fade_to_black", "Fade to Black"),
    ("slide_left", "Slide <-"),
    ("slide_right", "Slide ->"),
    ("wipe_left", "Wipe <-"),
    ("wipe_right", "Wipe ->"),
]

TRANSITION_MIME_TYPE = "application/x-opencut-transition"


class _TransitionDragButton(QPushButton):
    def __init__(self, transition_type: str, label: str, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self._transition_type = transition_type
        self._press_pos: QPoint | None = None
        self.setToolTip("Drag onto a clip boundary on the timeline")

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._press_pos is None:
            return
        if (event.pos() - self._press_pos).manhattanLength() < 8:
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(TRANSITION_MIME_TYPE, self._transition_type.encode("utf-8"))
        drag.setMimeData(mime)
        preview = QPixmap(120, 32)
        preview.fill(Qt.GlobalColor.transparent)
        drag.setPixmap(preview)
        drag.exec(Qt.DropAction.CopyAction)
        self._press_pos = None

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._press_pos = None
        super().mouseReleaseEvent(event)


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

        separator = QFrame(self)
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        transitions_title = QLabel("Transitions", self)
        transitions_title.setStyleSheet("font-weight: 600;")
        layout.addWidget(transitions_title)

        transitions_hint = QLabel("Drag onto the boundary between two clips.", self)
        transitions_hint.setWordWrap(True)
        transitions_hint.setStyleSheet("color: #7a8794;")
        layout.addWidget(transitions_hint)

        for transition_type, label in _TRANSITION_BUTTONS:
            layout.addWidget(_TransitionDragButton(transition_type, label, self))

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
