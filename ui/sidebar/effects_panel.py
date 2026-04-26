from __future__ import annotations

from app.controllers.app_controller import AppController
from app.domain.clips.base_clip import BaseClip
from app.domain.clips.image_clip import ImageClip
from app.domain.clips.video_clip import VideoClip
from app.domain.commands import CompositeCommand, UpdatePropertyCommand
from app.domain.project import Project
from app.services.lut_service import (
    PRESET_ID_PREFIX,
    PRESETS,
    display_label_for_path,
    is_valid_cube_file,
)
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
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


def _translate_preset_name(preset_id: str) -> str:
    """Translate a preset display name. Source strings are literal so
    pyside6-lupdate can extract them; the runtime map dispatches by preset id."""
    if preset_id == "preset:cinematic":
        return QCoreApplication.translate("EffectsPanel", "Điện ảnh")
    if preset_id == "preset:vintage":
        return QCoreApplication.translate("EffectsPanel", "Hoài cổ")
    if preset_id == "preset:black_and_white":
        return QCoreApplication.translate("EffectsPanel", "Đen trắng")
    return preset_id


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

        # --- LUT section --------------------------------------------------
        separator = QFrame(self)
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        self._lut_title = QLabel(self.tr("LUT 3D"), self)
        self._lut_title.setStyleSheet("font-weight: 600;")
        layout.addWidget(self._lut_title)

        self._lut_combo = QComboBox(self)
        self._lut_combo.addItem(self.tr("Không dùng LUT"), userData="")
        for preset in PRESETS:
            self._lut_combo.addItem(_translate_preset_name(preset.preset_id), userData=preset.preset_id)
        self._lut_combo.addItem(self.tr("Tệp LUT tuỳ chỉnh…"), userData="__custom__")
        self._lut_combo.activated.connect(self._on_lut_combo_activated)
        layout.addWidget(self._lut_combo)

        self._lut_status = QLabel("", self)
        self._lut_status.setStyleSheet("color: #7a8794;")
        self._lut_status.setWordWrap(True)
        layout.addWidget(self._lut_status)

        layout.addStretch(1)

        app_controller.selection_controller.selection_changed.connect(self._refresh_from_selection)
        app_controller.project_controller.project_changed.connect(self._refresh_from_selection)
        # Re-sync sliders after undo/redo (or any other timeline edit) so the
        # widget never drifts out of step with the clip's actual color state.
        app_controller.timeline_controller.timeline_edited.connect(self._refresh_from_selection)
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
        self._lut_combo.setEnabled(enabled)
        if clip is None:
            for name, slider in self._sliders.items():
                slider.blockSignals(True)
                slider.setValue(_attr_to_slider(name, _default_attr(name)))
                slider.blockSignals(False)
                self._value_labels[name].setText("")
            self._sync_lut_combo("")
            self._lut_status.setText("")
            return
        for name, slider in self._sliders.items():
            attr_value = float(getattr(clip, name))
            slider.blockSignals(True)
            slider.setValue(_attr_to_slider(name, attr_value))
            slider.blockSignals(False)
            self._update_value_label(name, attr_value)
        self._sync_lut_combo(str(getattr(clip, "lut_path", "") or ""))

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
        current_lut = str(getattr(clip, "lut_path", "") or "")
        if current_lut:
            sub_commands.append(
                UpdatePropertyCommand(target=clip, attribute_name="lut_path", new_value="")
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

    # --- LUT handlers -----------------------------------------------------

    def _sync_lut_combo(self, lut_path: str) -> None:
        """Match combo selection + status label to the clip's stored lut_path."""
        self._lut_combo.blockSignals(True)
        try:
            target_index = 0  # "Không dùng LUT"
            if lut_path:
                if lut_path.startswith(PRESET_ID_PREFIX):
                    for i in range(self._lut_combo.count()):
                        if self._lut_combo.itemData(i) == lut_path:
                            target_index = i
                            break
                else:
                    # Custom file path: select the "custom" sentinel entry.
                    for i in range(self._lut_combo.count()):
                        if self._lut_combo.itemData(i) == "__custom__":
                            target_index = i
                            break
            self._lut_combo.setCurrentIndex(target_index)
        finally:
            self._lut_combo.blockSignals(False)
        if not lut_path:
            self._lut_status.setText("")
        else:
            self._lut_status.setText(self.tr("Đang dùng: {label}").format(label=display_label_for_path(lut_path)))

    def _on_lut_combo_activated(self, index: int) -> None:
        clip = self._current_clip
        if clip is None:
            return
        data = self._lut_combo.itemData(index)
        if data == "__custom__":
            self._prompt_for_custom_lut()
            return
        new_value = "" if data is None else str(data)
        self._apply_lut_path(new_value)

    def _prompt_for_custom_lut(self) -> None:
        clip = self._current_clip
        if clip is None:
            return
        path, _filter = QFileDialog.getOpenFileName(
            self,
            self.tr("Chọn tệp LUT (.cube)"),
            "",
            self.tr("Tệp LUT (*.cube)"),
        )
        if not path:
            # User cancelled: re-sync combo to the current clip state so the
            # transient "Tệp LUT tuỳ chỉnh…" selection does not stick.
            self._sync_lut_combo(str(getattr(clip, "lut_path", "") or ""))
            return
        if not is_valid_cube_file(path):
            QMessageBox.warning(
                self,
                self.tr("Tệp LUT không hợp lệ"),
                self.tr("Tệp được chọn không phải tệp .cube hợp lệ (thiếu LUT_3D_SIZE)."),
            )
            self._sync_lut_combo(str(getattr(clip, "lut_path", "") or ""))
            return
        self._apply_lut_path(path)

    def _apply_lut_path(self, new_value: str) -> None:
        clip = self._current_clip
        if clip is None:
            return
        old_value = str(getattr(clip, "lut_path", "") or "")
        if new_value == old_value:
            return
        self._app_controller.timeline_controller.execute_command(
            UpdatePropertyCommand(target=clip, attribute_name="lut_path", new_value=new_value)
        )

    # --- accessors for tests ----------------------------------------------

    def slider_for(self, name: str) -> QSlider:
        return self._sliders[name]

    def lut_combo(self) -> QComboBox:
        return self._lut_combo

    @staticmethod
    def supported_clip(clip: BaseClip) -> bool:
        return isinstance(clip, (VideoClip, ImageClip))
