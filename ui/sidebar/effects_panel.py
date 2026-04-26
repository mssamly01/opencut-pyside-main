from __future__ import annotations

from app.controllers.app_controller import AppController
from app.domain.clips.base_clip import BaseClip
from app.domain.clips.image_clip import ImageClip
from app.domain.clips.video_clip import VideoClip
from app.domain.commands import CompositeCommand, UpdatePropertyCommand
from app.domain.project import Project
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

# Slider scaling: integer slider position -> float clip attribute.
# brightness: -100..+100 -> -1.0..+1.0
# contrast:      0..200 ->  0.0..2.0  (default 100 = 1.0)
# saturation:    0..300 ->  0.0..3.0  (default 100 = 1.0)
# hue:        -180..180 -> -180..180 (degrees)
_SLIDER_RANGES: dict[str, tuple[int, int, float, float]] = {
    "brightness": (-100, 100, 100.0, 0.0),
    "contrast": (0, 200, 100.0, 1.0),
    "saturation": (0, 300, 100.0, 1.0),
    "hue": (-180, 180, 1.0, 0.0),
}


def _slider_to_attr(name: str, slider_value: int) -> float:
    _lo, _hi, divisor, _default = _SLIDER_RANGES[name]
    return slider_value / divisor


def _attr_to_slider(name: str, attr_value: float) -> int:
    _lo, _hi, divisor, _default = _SLIDER_RANGES[name]
    return int(round(attr_value * divisor))


def _default_attr(name: str) -> float:
    return _SLIDER_RANGES[name][3]


class EffectsPanel(QWidget):
    """Sidebar color-grading panel with brightness/contrast/saturation/hue sliders."""

    def __init__(self, app_controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app_controller = app_controller
        self._current_clip: VideoClip | ImageClip | None = None
        self._press_value: float | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self._title = QLabel(self.tr("Hiệu ứng màu"), self)
        self._title.setStyleSheet("font-weight: 600;")
        layout.addWidget(self._title)

        self._hint = QLabel(
            self.tr("Chọn một clip video hoặc ảnh trên dòng thời gian để chỉnh màu."),
            self,
        )
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("color: #7a8794;")
        layout.addWidget(self._hint)

        form = QFormLayout()
        form.setSpacing(6)

        self._sliders: dict[str, QSlider] = {}
        self._value_labels: dict[str, QLabel] = {}
        for name, label_text in (
            ("brightness", self.tr("Độ sáng")),
            ("contrast", self.tr("Tương phản")),
            ("saturation", self.tr("Bão hoà")),
            ("hue", self.tr("Sắc độ")),
        ):
            slider, value_label = self._build_slider_row(name)
            row_widget = QWidget(self)
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            row_layout.addWidget(slider, 1)
            row_layout.addWidget(value_label)
            form.addRow(label_text, row_widget)
            self._sliders[name] = slider
            self._value_labels[name] = value_label

        layout.addLayout(form)

        self._reset_button = QPushButton(self.tr("Đặt lại màu"), self)
        self._reset_button.clicked.connect(self._on_reset_clicked)
        layout.addWidget(self._reset_button)

        layout.addStretch(1)

        app_controller.selection_controller.selection_changed.connect(self._refresh_from_selection)
        app_controller.project_controller.project_changed.connect(self._refresh_from_selection)
        self._refresh_from_selection()

    # --- slider plumbing ---------------------------------------------------

    def _build_slider_row(self, name: str) -> tuple[QSlider, QLabel]:
        lo, hi, _divisor, _default = _SLIDER_RANGES[name]
        slider = QSlider(Qt.Orientation.Horizontal, self)
        slider.setRange(lo, hi)
        slider.setSingleStep(1)
        slider.setPageStep(10)
        slider.sliderPressed.connect(lambda n=name: self._on_slider_pressed(n))
        slider.valueChanged.connect(lambda v, n=name: self._on_slider_value_changed(n, v))
        slider.sliderReleased.connect(lambda n=name: self._on_slider_released(n))
        value_label = QLabel("", self)
        value_label.setMinimumWidth(48)
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return slider, value_label

    # --- selection / refresh ----------------------------------------------

    def _refresh_from_selection(self) -> None:
        clip = self._resolve_selected_clip()
        self._current_clip = clip
        enabled = clip is not None
        for slider in self._sliders.values():
            slider.setEnabled(enabled)
        self._reset_button.setEnabled(enabled)
        if clip is None:
            for name, slider in self._sliders.items():
                slider.blockSignals(True)
                slider.setValue(_attr_to_slider(name, _default_attr(name)))
                slider.blockSignals(False)
                self._value_labels[name].setText("")
            return
        for name, slider in self._sliders.items():
            attr_value = float(getattr(clip, name))
            slider.blockSignals(True)
            slider.setValue(_attr_to_slider(name, attr_value))
            slider.blockSignals(False)
            self._update_value_label(name, attr_value)

    def _resolve_selected_clip(self) -> VideoClip | ImageClip | None:
        project: Project | None = self._app_controller.project_controller.active_project()
        if project is None:
            return None
        clip_id = self._app_controller.selection_controller.selected_clip_id()
        if clip_id is None:
            return None
        for track in project.timeline.tracks:
            for candidate in track.clips:
                if candidate.clip_id == clip_id and isinstance(candidate, (VideoClip, ImageClip)):
                    return candidate
        return None

    # --- slider event handlers -------------------------------------------

    def _on_slider_pressed(self, name: str) -> None:
        clip = self._current_clip
        if clip is None:
            return
        self._press_value = float(getattr(clip, name))

    def _on_slider_value_changed(self, name: str, slider_value: int) -> None:
        clip = self._current_clip
        if clip is None:
            return
        new_attr = _slider_to_attr(name, slider_value)
        if self._press_value is not None:
            # Mouse drag in progress: live preview only; the undoable command
            # is committed once on sliderReleased so the whole drag becomes a
            # single undo step.
            setattr(clip, name, new_attr)
            self._update_value_label(name, new_attr)
            self._app_controller.timeline_controller.timeline_changed.emit()
            return
        # No active drag (keyboard arrow / Page Up-Down / programmatic):
        # commit each step as its own undoable command so Ctrl+Z works.
        old_attr = float(getattr(clip, name))
        if abs(new_attr - old_attr) <= 1e-9:
            return
        self._app_controller.timeline_controller.execute_command(
            UpdatePropertyCommand(target=clip, attribute_name=name, new_value=new_attr)
        )
        self._update_value_label(name, new_attr)

    def _on_slider_released(self, name: str) -> None:
        clip = self._current_clip
        press_value = self._press_value
        self._press_value = None
        if clip is None or press_value is None:
            return
        new_value = float(getattr(clip, name))
        if abs(new_value - press_value) <= 1e-9:
            return
        # Revert transient drag value so the command captures (press_value -> new_value)
        # as a single undoable step.
        setattr(clip, name, press_value)
        self._app_controller.timeline_controller.execute_command(
            UpdatePropertyCommand(target=clip, attribute_name=name, new_value=new_value)
        )

    def _on_reset_clicked(self) -> None:
        clip = self._current_clip
        if clip is None:
            return
        sub_commands: list[UpdatePropertyCommand] = []
        for name in self._sliders:
            current = float(getattr(clip, name))
            default = _default_attr(name)
            if abs(current - default) > 1e-9:
                sub_commands.append(
                    UpdatePropertyCommand(target=clip, attribute_name=name, new_value=default)
                )
        if sub_commands:
            self._app_controller.timeline_controller.execute_command(
                CompositeCommand(sub_commands)
            )
        self._refresh_from_selection()

    # --- formatting -------------------------------------------------------

    def _update_value_label(self, name: str, attr_value: float) -> None:
        label = self._value_labels[name]
        if name == "hue":
            label.setText(f"{attr_value:+.0f}°")
        elif name == "brightness":
            label.setText(f"{attr_value:+.2f}")
        else:
            label.setText(f"{attr_value:.2f}")

    # --- accessors for tests ----------------------------------------------

    def slider_for(self, name: str) -> QSlider:
        return self._sliders[name]

    @staticmethod
    def supported_clip(clip: BaseClip) -> bool:
        return isinstance(clip, (VideoClip, ImageClip))
