from __future__ import annotations

import math

from app.controllers.timeline_controller import TimelineController
from app.ui.shared.icons import build_icon
from app.ui.timeline.timeline_view import TimelineView
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
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
        layout.setSpacing(8)

        self._undo_button = self._create_icon_button("undo", "Undo (Ctrl+Z)")
        self._undo_button.clicked.connect(self._timeline_controller.undo)
        layout.addWidget(self._undo_button)

        self._redo_button = self._create_icon_button("redo", "Redo (Ctrl+Y)")
        self._redo_button.clicked.connect(self._timeline_controller.redo)
        layout.addWidget(self._redo_button)
        layout.addWidget(self._create_separator())

        self._zoom_out_button = self._create_icon_button("zoom-out", "Zoom Out (Ctrl+-)")
        self._zoom_out_button.clicked.connect(self._timeline_view.zoom_out)
        layout.addWidget(self._zoom_out_button)

        self._zoom_in_button = self._create_icon_button("zoom-in", "Zoom In (Ctrl+=)")
        self._zoom_in_button.clicked.connect(self._timeline_view.zoom_in)
        layout.addWidget(self._zoom_in_button)

        self._fit_icon_button = self._create_icon_button("fit", "Fit Timeline (Ctrl+0)")
        self._fit_icon_button.clicked.connect(self._timeline_view.fit_timeline)
        layout.addWidget(self._fit_icon_button)
        layout.addWidget(self._create_separator())

        self._add_track_button = QToolButton(self)
        self._add_track_button.setText("Add Track")
        self._add_track_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        add_track_menu = QMenu(self._add_track_button)
        add_track_menu.addAction("Video Track", lambda: self._add_track("video"))
        add_track_menu.addAction("Audio Track", lambda: self._add_track("audio"))
        add_track_menu.addAction("Text Track", lambda: self._add_track("text"))
        self._add_track_button.setMenu(add_track_menu)
        layout.addWidget(self._add_track_button)

        self._snap_button = self._create_icon_button("magnet", "Toggle Snap")
        self._snap_button.setCheckable(True)
        self._snap_button.setChecked(self._timeline_controller.snapping_enabled())
        self._snap_button.toggled.connect(self._timeline_controller.set_snapping_enabled)
        layout.addWidget(self._snap_button)

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

        layout.addStretch(1)
        self._timeline_controller.timeline_changed.connect(self._sync_from_controller)
        self._sync_from_controller()

    def _create_icon_button(self, icon_name: str, tooltip: str) -> QToolButton:
        button = QToolButton(self)
        button.setIcon(build_icon(icon_name))
        button.setIconSize(QSize(18, 18))
        button.setToolTip(tooltip)
        button.setAutoRaise(True)
        return button

    def _create_separator(self) -> QFrame:
        separator = QFrame(self)
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Plain)
        separator.setLineWidth(0)
        separator.setMidLineWidth(0)
        separator.setFixedWidth(1)
        separator.setStyleSheet("QFrame { background-color: #3a4452; }")
        return separator

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
            self._snap_button.setChecked(self._timeline_controller.snapping_enabled())
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
