from __future__ import annotations

import math

from app.controllers.timeline_controller import TimelineController
from app.ui.timeline.timeline_view import TimelineView
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSlider,
    QToolButton,
    QWidget,
)


class TimelineToolbar(QWidget):
    _MIN_PPS = 10.0
    _MAX_PPS = 2000.0

    def __init__(
        self,
        timeline_controller: TimelineController,
        timeline_view: TimelineView,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._timeline_controller = timeline_controller
        self._timeline_view = timeline_view
        self._is_syncing = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        self._add_track_button = QToolButton(self)
        self._add_track_button.setText("Add Track")
        self._add_track_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        add_track_menu = QMenu(self._add_track_button)
        add_track_menu.addAction("Video Track", lambda: self._add_track("video"))
        add_track_menu.addAction("Audio Track", lambda: self._add_track("audio"))
        add_track_menu.addAction("Text Track", lambda: self._add_track("text"))
        self._add_track_button.setMenu(add_track_menu)
        layout.addWidget(self._add_track_button)

        self._snap_checkbox = QCheckBox("Snap", self)
        self._snap_checkbox.setChecked(self._timeline_controller.snapping_enabled())
        self._snap_checkbox.toggled.connect(self._timeline_controller.set_snapping_enabled)
        layout.addWidget(self._snap_checkbox)

        self._ripple_checkbox = QCheckBox("Ripple", self)
        self._ripple_checkbox.setChecked(self._timeline_controller.ripple_edit_enabled())
        self._ripple_checkbox.toggled.connect(self._timeline_controller.set_ripple_edit_enabled)
        layout.addWidget(self._ripple_checkbox)

        self._playhead_sticky_checkbox = QCheckBox("Stick Playhead", self)
        self._playhead_sticky_checkbox.setChecked(self._timeline_view.playhead_sticky_to_mouse_enabled())
        self._playhead_sticky_checkbox.toggled.connect(self._timeline_view.set_playhead_sticky_to_mouse_enabled)
        layout.addWidget(self._playhead_sticky_checkbox)

        self._zoom_label = QLabel(self)
        layout.addWidget(self._zoom_label)

        self._zoom_slider = QSlider(Qt.Orientation.Horizontal, self)
        self._zoom_slider.setRange(0, 1000)
        self._zoom_slider.setFixedWidth(210)
        self._zoom_slider.valueChanged.connect(self._on_zoom_slider_changed)
        layout.addWidget(self._zoom_slider)

        self._fit_button = QPushButton("Fit", self)
        self._fit_button.clicked.connect(self._timeline_view.fit_timeline)
        layout.addWidget(self._fit_button)

        layout.addStretch(1)
        self._timeline_controller.timeline_changed.connect(self._sync_from_controller)
        self._sync_from_controller()

    def _add_track(self, track_type: str) -> None:
        self._timeline_controller.add_track(track_type)

    def _on_zoom_slider_changed(self, slider_value: int) -> None:
        if self._is_syncing:
            return
        pixels_per_second = self._slider_to_pixels_per_second(slider_value)
        self._timeline_controller.set_pixels_per_second(pixels_per_second)

    def _sync_from_controller(self) -> None:
        self._is_syncing = True
        try:
            self._snap_checkbox.setChecked(self._timeline_controller.snapping_enabled())
            self._ripple_checkbox.setChecked(self._timeline_controller.ripple_edit_enabled())
            self._playhead_sticky_checkbox.setChecked(self._timeline_view.playhead_sticky_to_mouse_enabled())
            pps = self._timeline_controller.pixels_per_second
            self._zoom_slider.setValue(self._pixels_per_second_to_slider(pps))
            self._zoom_label.setText(f"Zoom: {pps:.0f} px/s")
        finally:
            self._is_syncing = False

    @classmethod
    def _pixels_per_second_to_slider(cls, pixels_per_second: float) -> int:
        clamped = max(cls._MIN_PPS, min(float(pixels_per_second), cls._MAX_PPS))
        ratio = (math.log(clamped) - math.log(cls._MIN_PPS)) / (math.log(cls._MAX_PPS) - math.log(cls._MIN_PPS))
        return int(round(ratio * 1000))

    @classmethod
    def _slider_to_pixels_per_second(cls, slider_value: int) -> float:
        ratio = max(0.0, min(float(slider_value) / 1000.0, 1.0))
        exponent = math.log(cls._MIN_PPS) + ratio * (math.log(cls._MAX_PPS) - math.log(cls._MIN_PPS))
        return math.exp(exponent)
