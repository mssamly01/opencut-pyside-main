from __future__ import annotations

import math

from app.controllers.timeline_controller import TimelineController
from app.ui.shared.icons import build_icon, icon_size
from app.ui.timeline.timeline_view import TimelineView
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QMenu, QSlider, QToolButton, QWidget


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
        self.setObjectName("timeline_toolbar")
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        # Left cluster: editing actions.
        self._undo_button = self._create_icon_button("undo", self.tr("Hoàn tác (Ctrl+Z)"))
        self._undo_button.clicked.connect(self._timeline_controller.undo)
        layout.addWidget(self._undo_button)

        self._redo_button = self._create_icon_button("redo", self.tr("Làm lại (Ctrl+Y)"))
        self._redo_button.clicked.connect(self._timeline_controller.redo)
        layout.addWidget(self._redo_button)
        layout.addWidget(self._create_separator())

        self._add_track_button = QToolButton(self)
        self._add_track_button.setText(self.tr("+ Track"))
        self._add_track_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        add_track_menu = QMenu(self._add_track_button)
        add_track_menu.addAction(self.tr("Track Video"), lambda: self._add_track("video"))
        add_track_menu.addAction(self.tr("Track Âm thanh"), lambda: self._add_track("audio"))
        add_track_menu.addAction(self.tr("Track Văn bản"), lambda: self._add_track("text"))
        self._add_track_button.setMenu(add_track_menu)
        layout.addWidget(self._add_track_button)
        layout.addWidget(self._create_separator())

        self._split_button = self._create_icon_button("split", self.tr("Tách (S)"))
        self._split_button.clicked.connect(self._on_split)
        layout.addWidget(self._split_button)

        self._duplicate_button = self._create_icon_button("duplicate", self.tr("Nhân bản (Ctrl+D)"))
        self._duplicate_button.clicked.connect(self._on_duplicate)
        layout.addWidget(self._duplicate_button)

        self._delete_button = self._create_icon_button("delete", self.tr("Xóa (Delete)"))
        self._delete_button.clicked.connect(self._on_delete)
        layout.addWidget(self._delete_button)

        layout.addStretch(1)

        # Right cluster: timeline behavior + zoom controls.
        self._snap_checkbox = QCheckBox(self.tr("Hút"), self)
        self._snap_checkbox.toggled.connect(self._on_snap_toggled)
        layout.addWidget(self._snap_checkbox)

        self._ripple_checkbox = QCheckBox(self.tr("Ripple"), self)
        self._ripple_checkbox.toggled.connect(self._on_ripple_toggled)
        layout.addWidget(self._ripple_checkbox)

        self._playhead_sticky_checkbox = QCheckBox(self.tr("Dính đầu phát"), self)
        self._playhead_sticky_checkbox.toggled.connect(self._on_playhead_sticky_toggled)
        layout.addWidget(self._playhead_sticky_checkbox)

        self._hover_scrub_checkbox = QCheckBox(self.tr("Theo dõi chuột"), self)
        self._hover_scrub_checkbox.setToolTip(
            self.tr(
                "Khi bật: rê chuột trên timeline sẽ tự seek preview tới vị trí đó (không cần click)."
            )
        )
        self._hover_scrub_checkbox.toggled.connect(self._on_hover_scrub_toggled)
        layout.addWidget(self._hover_scrub_checkbox)
        layout.addWidget(self._create_separator())

        self._zoom_label = QLabel(self.tr("Thu phóng"), self)
        layout.addWidget(self._zoom_label)

        self._zoom_slider = QSlider(Qt.Orientation.Horizontal, self)
        self._zoom_slider.setRange(0, 1000)
        self._zoom_slider.setFixedWidth(140)
        self._zoom_slider.valueChanged.connect(self._on_zoom_slider_changed)
        layout.addWidget(self._zoom_slider)

        self._fit_button = QToolButton(self)
        self._fit_button.setText(self.tr("Vừa khít"))
        self._fit_button.clicked.connect(self._timeline_view.fit_timeline)
        layout.addWidget(self._fit_button)

        self._timeline_controller.timeline_changed.connect(self._sync_from_controller)
        self._sync_from_controller()

    def _create_icon_button(self, icon_name: str, tooltip: str) -> QToolButton:
        button = QToolButton(self)
        button.setIcon(build_icon(icon_name))
        button.setIconSize(icon_size(16))
        button.setToolTip(tooltip)
        button.setAutoRaise(True)
        return button

    def _create_separator(self) -> QFrame:
        separator = QFrame(self)
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Plain)
        separator.setObjectName("timeline_toolbar_sep")
        return separator

    def _add_track(self, track_type: str) -> None:
        self._timeline_controller.add_track(track_type)

    def _on_split(self) -> None:
        split_position = round(self._timeline_controller.playhead_seconds(), 3)
        self._timeline_controller.split_selected_clip(split_position)

    def _on_duplicate(self) -> None:
        self._timeline_controller.duplicate_clip()

    def _on_delete(self) -> None:
        self._timeline_controller.delete_selected_clip()

    def _on_snap_toggled(self, checked: bool) -> None:
        self._timeline_controller.set_snapping_enabled(checked)

    def _on_ripple_toggled(self, checked: bool) -> None:
        self._timeline_controller.set_ripple_edit_enabled(checked)

    def _on_playhead_sticky_toggled(self, checked: bool) -> None:
        self._timeline_view.set_playhead_sticky_to_mouse_enabled(checked)

    def _on_hover_scrub_toggled(self, checked: bool) -> None:
        self._timeline_view.set_hover_scrub_enabled(checked)

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
            self._hover_scrub_checkbox.setChecked(self._timeline_view.hover_scrub_enabled())
            pps = self._timeline_controller.pixels_per_second
            self._zoom_slider.setValue(self._pixels_per_second_to_slider(pps))
            self._zoom_label.setText(self.tr("Thu phóng: {pps:.0f} px/s").format(pps=pps))
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
