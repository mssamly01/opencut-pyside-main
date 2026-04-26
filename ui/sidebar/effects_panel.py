from __future__ import annotations

from app.controllers.app_controller import AppController
from app.domain.clips.base_clip import BaseClip
from app.domain.clips.image_clip import ImageClip
from app.domain.clips.video_clip import VideoClip
from app.domain.commands import (
    AddKeyframeCommand,
    CompositeCommand,
    RemoveKeyframeCommand,
    UpdatePropertyCommand,
)
from app.domain.commands._keyframe_utils import find_keyframe_index
from app.domain.keyframe import Keyframe
from app.domain.project import Project
from app.services.keyframe_evaluator import clip_has_keyframes, resolve_clip_value_at
from app.services.lut_service import (
    PRESET_ID_PREFIX,
    PRESETS,
    display_label_for_path,
    is_valid_cube_file,
)
from PySide6.QtCore import QCoreApplication, QPoint, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QToolButton,
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
        # Track BOTH the original static attribute (used for revert/old-value
        # capture in undo commands) AND the resolved value displayed on press
        # (used for no-op detection).  When keyframes exist the two diverge.
        self._press_static: float | None = None
        self._press_resolved: float | None = None

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
        self._pin_buttons: dict[str, QToolButton] = {}
        for name, label_text in (
            ("brightness", self.tr("Độ sáng")),
            ("contrast", self.tr("Tương phản")),
            ("saturation", self.tr("Bão hoà")),
            ("hue", self.tr("Sắc độ")),
        ):
            slider, value_label, pin_button = self._build_slider_row(name)
            row_widget = QWidget(self)
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            row_layout.addWidget(slider, 1)
            row_layout.addWidget(value_label)
            row_layout.addWidget(pin_button)
            form.addRow(label_text, row_widget)
            self._sliders[name] = slider
            self._value_labels[name] = value_label
            self._pin_buttons[name] = pin_button

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
        # Update slider values + pin diamonds as the playhead moves.
        app_controller.playback_controller.current_time_changed.connect(
            lambda _seconds: self._refresh_from_selection()
        )
        self._refresh_from_selection()

    # --- slider plumbing ---------------------------------------------------

    def _build_slider_row(self, name: str) -> tuple[QSlider, QLabel, QToolButton]:
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
        pin_button = QToolButton(self)
        pin_button.setText("\u25C7")  # ◇ hollow diamond, replaced with ◆ when keyframed
        pin_button.setAutoRaise(True)
        pin_button.setCursor(Qt.CursorShape.PointingHandCursor)
        pin_button.setFixedWidth(24)
        pin_button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        pin_button.setToolTip(self.tr("Thêm/xoá keyframe tại đầu phát"))
        pin_button.clicked.connect(lambda _checked=False, n=name: self._on_pin_clicked(n))
        pin_button.customContextMenuRequested.connect(
            lambda pos, n=name: self._on_pin_context_menu(n, pos)
        )
        return slider, value_label, pin_button

    # --- selection / refresh ----------------------------------------------

    def _refresh_from_selection(self) -> None:
        clip = self._resolve_selected_clip()
        self._current_clip = clip
        enabled = clip is not None
        for slider in self._sliders.values():
            slider.setEnabled(enabled)
        for pin in self._pin_buttons.values():
            pin.setEnabled(enabled)
        self._reset_button.setEnabled(enabled)
        self._lut_combo.setEnabled(enabled)
        if clip is None:
            for name, slider in self._sliders.items():
                slider.blockSignals(True)
                slider.setValue(_attr_to_slider(name, _default_attr(name)))
                slider.blockSignals(False)
                self._value_labels[name].setText("")
                self._set_pin_state(name, "none")
            self._sync_lut_combo("")
            self._lut_status.setText("")
            return
        time_in_clip = self._clip_relative_playhead(clip)
        for name, slider in self._sliders.items():
            # When keyframes exist, the *displayed* value is the interpolated
            # value at the current playhead — otherwise the static attribute.
            if clip_has_keyframes(clip, name):
                attr_value = resolve_clip_value_at(
                    clip, name, time_in_clip, _default_attr(name)
                )
            else:
                attr_value = float(getattr(clip, name))
            slider.blockSignals(True)
            slider.setValue(_attr_to_slider(name, attr_value))
            slider.blockSignals(False)
            self._update_value_label(name, attr_value)
            self._set_pin_state(name, self._pin_state_for(clip, name, time_in_clip))
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
        self._press_static = float(getattr(clip, name))
        if clip_has_keyframes(clip, name):
            self._press_resolved = resolve_clip_value_at(
                clip,
                name,
                self._clip_relative_playhead(clip),
                _default_attr(name),
            )
        else:
            self._press_resolved = self._press_static

    def _on_slider_value_changed(self, name: str, slider_value: int) -> None:
        clip = self._current_clip
        if clip is None:
            return
        new_attr = _slider_to_attr(name, slider_value)
        if self._press_static is not None:
            # Mouse drag in progress.  For non-keyframed clips we mutate the
            # static attribute so the preview updates live.  For keyframed
            # clips the preview is bound to the interpolation curve, so a
            # drag-time mutation of the static fallback would be both
            # invisible and (worse) corrupt the value the user expects to see
            # after undo — we update the value label only and commit on
            # release.
            if not clip_has_keyframes(clip, name):
                setattr(clip, name, new_attr)
                self._app_controller.timeline_controller.timeline_changed.emit()
            self._update_value_label(name, new_attr)
            return
        # No active drag (keyboard arrow / Page Up-Down / programmatic):
        # commit each step as its own undoable command so Ctrl+Z works.
        old_attr = (
            resolve_clip_value_at(
                clip, name, self._clip_relative_playhead(clip), _default_attr(name)
            )
            if clip_has_keyframes(clip, name)
            else float(getattr(clip, name))
        )
        if abs(new_attr - old_attr) <= 1e-9:
            return
        self._commit_slider_change(clip, name, new_attr)
        self._update_value_label(name, new_attr)

    def _on_slider_released(self, name: str) -> None:
        clip = self._current_clip
        press_static = self._press_static
        press_resolved = self._press_resolved
        self._press_static = None
        self._press_resolved = None
        if clip is None or press_static is None or press_resolved is None:
            return
        new_value = _slider_to_attr(name, self._sliders[name].value())
        # Always revert any drag-time mutation back to the original static
        # attribute so the commit captures (press_static -> new_value) — never
        # (interpolated -> new_value), which would erase the original on undo.
        setattr(clip, name, press_static)
        if abs(new_value - press_resolved) <= 1e-9:
            self._refresh_from_selection()
            return
        self._commit_slider_change(clip, name, new_value)

    def _commit_slider_change(
        self,
        clip: VideoClip | ImageClip,
        name: str,
        new_value: float,
    ) -> None:
        """Commit a slider change as one undoable step.

        When keyframes already exist for ``name`` we *only* upsert a keyframe
        at the playhead — the static fallback stays untouched so undo cleanly
        rolls back to the prior animation state.  Without keyframes we just
        update the static attribute.
        """
        controller = self._app_controller.timeline_controller
        if clip_has_keyframes(clip, name):
            time_in_clip = self._clip_relative_playhead(clip)
            controller.execute_command(
                AddKeyframeCommand(
                    clip,
                    name,
                    Keyframe(time_seconds=time_in_clip, value=float(new_value)),
                )
            )
        else:
            controller.execute_command(
                UpdatePropertyCommand(target=clip, attribute_name=name, new_value=new_value)
            )

    def _on_reset_clicked(self) -> None:
        clip = self._current_clip
        if clip is None:
            return
        sub_commands: list[object] = []
        for name in self._sliders:
            current = float(getattr(clip, name))
            default = _default_attr(name)
            if abs(current - default) > 1e-9:
                sub_commands.append(
                    UpdatePropertyCommand(target=clip, attribute_name=name, new_value=default)
                )
            kf_attr = f"{name}_keyframes"
            if list(getattr(clip, kf_attr, [])):
                sub_commands.append(
                    UpdatePropertyCommand(target=clip, attribute_name=kf_attr, new_value=[])
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

    # --- keyframe pin handlers --------------------------------------------

    def _on_pin_clicked(self, name: str) -> None:
        clip = self._current_clip
        if clip is None:
            return
        time_in_clip = self._clip_relative_playhead(clip)
        kf_list = list(getattr(clip, f"{name}_keyframes", []))
        existing_index = find_keyframe_index(kf_list, time_in_clip)
        controller = self._app_controller.timeline_controller
        if existing_index is not None:
            try:
                controller.execute_command(
                    RemoveKeyframeCommand(clip, name, float(kf_list[existing_index].time_seconds))
                )
            except ValueError:
                pass
            return
        # Upsert at the current playhead with the slider's current value.
        new_value = _slider_to_attr(name, self._sliders[name].value())
        controller.execute_command(
            AddKeyframeCommand(
                clip,
                name,
                Keyframe(time_seconds=time_in_clip, value=float(new_value)),
            )
        )

    def _on_pin_context_menu(self, name: str, pos: QPoint) -> None:
        clip = self._current_clip
        if clip is None:
            return
        kf_list = list(getattr(clip, f"{name}_keyframes", []))
        if not kf_list:
            return
        menu = QMenu(self)
        time_in_clip = self._clip_relative_playhead(clip)
        existing_index = find_keyframe_index(kf_list, time_in_clip)
        if existing_index is not None:
            remove_one = menu.addAction(self.tr("Xoá keyframe tại đầu phát"))
            remove_one.triggered.connect(lambda: self._remove_keyframe_at(name, time_in_clip))
        clear_all = menu.addAction(self.tr("Xoá toàn bộ keyframe"))
        clear_all.triggered.connect(lambda: self._clear_all_keyframes(name))
        button = self._pin_buttons[name]
        menu.exec(button.mapToGlobal(pos))

    def _remove_keyframe_at(self, name: str, time_in_clip: float) -> None:
        clip = self._current_clip
        if clip is None:
            return
        try:
            self._app_controller.timeline_controller.execute_command(
                RemoveKeyframeCommand(clip, name, float(time_in_clip))
            )
        except ValueError:
            pass

    def _clear_all_keyframes(self, name: str) -> None:
        clip = self._current_clip
        if clip is None:
            return
        kf_attr = f"{name}_keyframes"
        if not list(getattr(clip, kf_attr, [])):
            return
        self._app_controller.timeline_controller.execute_command(
            UpdatePropertyCommand(target=clip, attribute_name=kf_attr, new_value=[])
        )

    # --- helpers ----------------------------------------------------------

    def _clip_relative_playhead(self, clip: VideoClip | ImageClip) -> float:
        absolute = float(self._app_controller.timeline_controller.playhead_seconds())
        local = absolute - float(clip.timeline_start)
        return max(0.0, min(float(clip.duration), local))

    def _pin_state_for(
        self,
        clip: VideoClip | ImageClip,
        name: str,
        time_in_clip: float,
    ) -> str:
        kf_list = list(getattr(clip, f"{name}_keyframes", []))
        if not kf_list:
            return "none"
        if find_keyframe_index(kf_list, time_in_clip) is not None:
            return "at"
        return "between"

    def _set_pin_state(self, name: str, state: str) -> None:
        button = self._pin_buttons[name]
        if state == "at":
            button.setText("\u25C6")  # ◆ filled diamond
            button.setStyleSheet("color: #ffd166;")
        elif state == "between":
            button.setText("\u25C7")  # ◇ hollow diamond, accented
            button.setStyleSheet("color: #ffd166;")
        else:
            button.setText("\u25C7")
            button.setStyleSheet("")

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
