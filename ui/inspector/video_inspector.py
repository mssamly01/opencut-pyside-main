from __future__ import annotations

from app.domain.clips.video_clip import VideoClip
from app.ui.inspector._clip_inspector_base import ClipInspectorBase, block_signals
from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox


class VideoInspector(ClipInspectorBase):
    def __init__(self, timeline_controller: object, clip: VideoClip, parent=None) -> None:
        super().__init__(timeline_controller, clip, parent)

    def _build_specific_fields(self) -> None:
        self._playback_speed_spin = QDoubleSpinBox(self)
        self._playback_speed_spin.setRange(0.1, 8.0)
        self._playback_speed_spin.setDecimals(2)
        self._playback_speed_spin.setSingleStep(0.1)
        self._playback_speed_spin.setKeyboardTracking(False)
        self._playback_speed_spin.editingFinished.connect(self._commit_specific_fields)
        self._form.addRow(self.tr("Tốc độ phát"), self._playback_speed_spin)

        self._reversed_check = QCheckBox(self.tr("Đảo ngược"), self)
        self._reversed_check.toggled.connect(self._commit_specific_fields)
        self._form.addRow("", self._reversed_check)

    def _refresh_specific_fields(self) -> None:
        clip = self._clip
        if not isinstance(clip, VideoClip):
            return

        with block_signals(self._playback_speed_spin, self._reversed_check):
            self._playback_speed_spin.setValue(clip.playback_speed)
            self._reversed_check.setChecked(clip.is_reversed)

    def _commit_specific_fields(self) -> None:
        clip = self._clip
        if not isinstance(clip, VideoClip):
            return

        if hasattr(self._timeline_controller, "set_clip_playback_speed"):
            self._timeline_controller.set_clip_playback_speed(clip.clip_id, float(self._playback_speed_spin.value()))
        else:
            self._apply_property_update(clip, "playback_speed", float(self._playback_speed_spin.value()))

        if hasattr(self._timeline_controller, "set_clip_reversed"):
            self._timeline_controller.set_clip_reversed(clip.clip_id, bool(self._reversed_check.isChecked()))
        else:
            self._apply_property_update(clip, "is_reversed", bool(self._reversed_check.isChecked()))
