from __future__ import annotations

from app.domain.clips.base_clip import BaseClip
from app.domain.clips.image_clip import ImageClip
from app.domain.clips.video_clip import VideoClip
from app.ui.inspector._inspector_base import block_signals
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

_COLOR_PRESETS: list[tuple[str, str]] = [
    ("none", "None"),
    ("warm", "Warm"),
    ("cool", "Cool"),
    ("sepia", "Sepia"),
    ("bw", "Black & White"),
    ("vivid", "Vivid"),
]


class _AdjustSlider(QSlider):
    def __init__(self, value_range: tuple[float, float], parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._value_min, self._value_max = value_range
        self.setRange(0, int(round((self._value_max - self._value_min) * 100)))
        self.setSingleStep(1)
        self.setPageStep(5)

    def set_normalized(self, value: float) -> None:
        clamped = max(self._value_min, min(self._value_max, float(value)))
        self.setValue(int(round((clamped - self._value_min) * 100)))

    def normalized_value(self) -> float:
        return self._value_min + self.value() / 100.0


class AdjustInspector(QWidget):
    def __init__(self, timeline_controller: object, clip: BaseClip, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._timeline_controller = timeline_controller
        self._clip = clip

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self._unsupported_label = QLabel("Adjust is available for video/image clips.", self)
        self._unsupported_label.setStyleSheet("color: #7a8794;")
        self._unsupported_label.setWordWrap(True)

        self._panel = QWidget(self)
        form = QFormLayout(self._panel)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(6)

        self._brightness = _AdjustSlider((-1.0, 1.0), self._panel)
        self._contrast = _AdjustSlider((-1.0, 1.0), self._panel)
        self._saturation = _AdjustSlider((-1.0, 1.0), self._panel)
        self._blur = _AdjustSlider((0.0, 1.0), self._panel)
        self._vignette = _AdjustSlider((0.0, 1.0), self._panel)
        self._preset = QComboBox(self._panel)
        for value, label in _COLOR_PRESETS:
            self._preset.addItem(label, value)

        for slider in (self._brightness, self._contrast, self._saturation, self._blur, self._vignette):
            slider.valueChanged.connect(self._commit_adjustments)

        self._preset.currentIndexChanged.connect(self._commit_preset)

        form.addRow("Brightness", self._row_with_value(self._brightness, "brightness"))
        form.addRow("Contrast", self._row_with_value(self._contrast, "contrast"))
        form.addRow("Saturation", self._row_with_value(self._saturation, "saturation"))
        form.addRow("Blur", self._row_with_value(self._blur, "blur"))
        form.addRow("Vignette", self._row_with_value(self._vignette, "vignette"))
        form.addRow("Preset", self._preset)

        root.addWidget(self._unsupported_label)
        root.addWidget(self._panel)
        root.addStretch(1)
        self.refresh_from_clip()

    def set_clip(self, clip: BaseClip) -> None:
        self._clip = clip
        self.refresh_from_clip()

    def refresh_from_clip(self) -> None:
        clip = self._clip
        supports_adjust = isinstance(clip, (VideoClip, ImageClip))
        self._panel.setVisible(supports_adjust)
        self._unsupported_label.setVisible(not supports_adjust)
        if not supports_adjust:
            return

        with block_signals(
            self._brightness,
            self._contrast,
            self._saturation,
            self._blur,
            self._vignette,
            self._preset,
        ):
            self._brightness.set_normalized(float(getattr(clip, "brightness", 0.0)))
            self._contrast.set_normalized(float(getattr(clip, "contrast", 0.0)))
            self._saturation.set_normalized(float(getattr(clip, "saturation", 0.0)))
            self._blur.set_normalized(float(getattr(clip, "blur", 0.0)))
            self._vignette.set_normalized(float(getattr(clip, "vignette", 0.0)))
            preset = str(getattr(clip, "color_preset", "none"))
            index = self._preset.findData(preset)
            self._preset.setCurrentIndex(index if index >= 0 else 0)
        self._refresh_value_labels()

    def _commit_adjustments(self) -> None:
        clip = self._clip
        if not isinstance(clip, (VideoClip, ImageClip)):
            return
        self._refresh_value_labels()
        if not hasattr(self._timeline_controller, "set_clip_adjustments"):
            return
        self._timeline_controller.set_clip_adjustments(
            clip.clip_id,
            brightness=self._brightness.normalized_value(),
            contrast=self._contrast.normalized_value(),
            saturation=self._saturation.normalized_value(),
            blur=self._blur.normalized_value(),
            vignette=self._vignette.normalized_value(),
        )

    def _commit_preset(self) -> None:
        clip = self._clip
        if not isinstance(clip, (VideoClip, ImageClip)):
            return
        if not hasattr(self._timeline_controller, "apply_clip_color_preset"):
            return
        preset = str(self._preset.currentData() or "none")
        if self._timeline_controller.apply_clip_color_preset(clip.clip_id, preset):
            clip_after = self._clip
            self._brightness.set_normalized(float(getattr(clip_after, "brightness", 0.0)))
            self._contrast.set_normalized(float(getattr(clip_after, "contrast", 0.0)))
            self._saturation.set_normalized(float(getattr(clip_after, "saturation", 0.0)))
            self._blur.set_normalized(float(getattr(clip_after, "blur", 0.0)))
            self._vignette.set_normalized(float(getattr(clip_after, "vignette", 0.0)))
            self._refresh_value_labels()

    def _row_with_value(self, slider: _AdjustSlider, name: str) -> QWidget:
        row = QWidget(self._panel)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        label = QLabel("0.00", row)
        label.setObjectName(f"{name}_value")
        label.setMinimumWidth(42)
        layout.addWidget(slider, 1)
        layout.addWidget(label)
        return row

    def _refresh_value_labels(self) -> None:
        for slider, object_name in (
            (self._brightness, "brightness_value"),
            (self._contrast, "contrast_value"),
            (self._saturation, "saturation_value"),
            (self._blur, "blur_value"),
            (self._vignette, "vignette_value"),
        ):
            label = self.findChild(QLabel, object_name)
            if label is None:
                continue
            if object_name in {"brightness_value", "contrast_value", "saturation_value"}:
                label.setText(f"{slider.normalized_value():+.2f}")
            else:
                label.setText(f"{slider.normalized_value():.2f}")
