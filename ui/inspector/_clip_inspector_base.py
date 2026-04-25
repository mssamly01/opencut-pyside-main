from __future__ import annotations

from app.domain.clips.base_clip import BaseClip
from app.ui.inspector._inspector_base import CommandAwareInspector, block_signals
from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QFormLayout, QLineEdit


class ClipInspectorBase(CommandAwareInspector):
    def __init__(self, timeline_controller: object, clip: BaseClip, parent=None) -> None:
        super().__init__(timeline_controller, parent)
        self._clip: BaseClip | None = clip

        self._form = QFormLayout(self)

        self._name_edit = QLineEdit(self)
        self._name_edit.editingFinished.connect(self._commit_name)
        self._form.addRow("Clip Name", self._name_edit)

        self._start_spin = QDoubleSpinBox(self)
        self._start_spin.setRange(0.0, 100000.0)
        self._start_spin.setDecimals(3)
        self._start_spin.setSingleStep(0.1)
        self._start_spin.setKeyboardTracking(False)
        self._start_spin.editingFinished.connect(self._commit_timing)
        self._form.addRow("Timeline Start", self._start_spin)

        self._duration_spin = QDoubleSpinBox(self)
        self._duration_spin.setRange(0.001, 100000.0)
        self._duration_spin.setDecimals(3)
        self._duration_spin.setSingleStep(0.1)
        self._duration_spin.setKeyboardTracking(False)
        self._duration_spin.editingFinished.connect(self._commit_timing)
        self._form.addRow("Duration", self._duration_spin)

        self._opacity_spin = QDoubleSpinBox(self)
        self._opacity_spin.setRange(0.0, 1.0)
        self._opacity_spin.setDecimals(2)
        self._opacity_spin.setSingleStep(0.05)
        self._opacity_spin.setKeyboardTracking(False)
        self._opacity_spin.editingFinished.connect(self._commit_common_flags)
        self._form.addRow("Opacity", self._opacity_spin)

        self._fade_in_spin = QDoubleSpinBox(self)
        self._fade_in_spin.setRange(0.0, 100000.0)
        self._fade_in_spin.setDecimals(3)
        self._fade_in_spin.setSingleStep(0.05)
        self._fade_in_spin.setKeyboardTracking(False)
        self._fade_in_spin.editingFinished.connect(self._commit_common_flags)
        self._form.addRow("Fade In (s)", self._fade_in_spin)

        self._fade_out_spin = QDoubleSpinBox(self)
        self._fade_out_spin.setRange(0.0, 100000.0)
        self._fade_out_spin.setDecimals(3)
        self._fade_out_spin.setSingleStep(0.05)
        self._fade_out_spin.setKeyboardTracking(False)
        self._fade_out_spin.editingFinished.connect(self._commit_common_flags)
        self._form.addRow("Fade Out (s)", self._fade_out_spin)

        self._locked_check = QCheckBox("Locked", self)
        self._locked_check.toggled.connect(self._commit_common_flags)
        self._form.addRow("", self._locked_check)

        self._muted_check = QCheckBox("Muted", self)
        self._muted_check.toggled.connect(self._commit_common_flags)
        self._form.addRow("", self._muted_check)

        self._build_specific_fields()
        self.refresh_from_clip()

    def set_clip(self, clip: BaseClip) -> None:
        self._clip = clip
        self.refresh_from_clip()

    def refresh_from_clip(self) -> None:
        clip = self._clip
        if clip is None:
            self.setEnabled(False)
            return

        self.setEnabled(True)
        with block_signals(
            self._name_edit,
            self._start_spin,
            self._duration_spin,
            self._opacity_spin,
            self._fade_in_spin,
            self._fade_out_spin,
            self._locked_check,
            self._muted_check,
        ):
            self._name_edit.setText(clip.name)
            self._start_spin.setValue(clip.timeline_start)
            self._duration_spin.setValue(clip.duration)
            self._opacity_spin.setValue(clip.opacity)
            self._fade_in_spin.setValue(clip.fade_in_seconds)
            self._fade_out_spin.setValue(clip.fade_out_seconds)
            self._locked_check.setChecked(clip.is_locked)
            self._muted_check.setChecked(clip.is_muted)
        self._refresh_specific_fields()

    def _commit_name(self) -> None:
        clip = self._clip
        if clip is None:
            return

        new_name = self._name_edit.text().strip() or clip.name
        self._apply_property_update(clip, "name", new_name)

    def _commit_timing(self) -> None:
        clip = self._clip
        if clip is None:
            return

        self._apply_property_update(clip, "timeline_start", float(self._start_spin.value()))
        self._apply_property_update(clip, "duration", max(float(self._duration_spin.value()), 0.001))

    def _commit_common_flags(self) -> None:
        clip = self._clip
        if clip is None:
            return

        self._apply_property_update(clip, "opacity", float(self._opacity_spin.value()))
        if hasattr(self._timeline_controller, "set_clip_fade"):
            self._timeline_controller.set_clip_fade(
                clip.clip_id,
                fade_in_seconds=max(0.0, float(self._fade_in_spin.value())),
                fade_out_seconds=max(0.0, float(self._fade_out_spin.value())),
            )
        else:
            self._apply_property_update(clip, "fade_in_seconds", max(0.0, float(self._fade_in_spin.value())))
            self._apply_property_update(clip, "fade_out_seconds", max(0.0, float(self._fade_out_spin.value())))
        self._apply_property_update(clip, "is_locked", bool(self._locked_check.isChecked()))
        self._apply_property_update(clip, "is_muted", bool(self._muted_check.isChecked()))

    def _build_specific_fields(self) -> None:
        raise NotImplementedError

    def _refresh_specific_fields(self) -> None:
        raise NotImplementedError
