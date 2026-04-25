from __future__ import annotations

from app.domain.clips.image_clip import ImageClip
from app.domain.clips.sticker_clip import StickerClip
from app.ui.inspector._clip_inspector_base import ClipInspectorBase, block_signals
from PySide6.QtWidgets import QDoubleSpinBox


class ImageInspector(ClipInspectorBase):
    def __init__(self, timeline_controller: object, clip: ImageClip | StickerClip, parent=None) -> None:
        super().__init__(timeline_controller, clip, parent)

    def _build_specific_fields(self) -> None:
        self._scale_spin = QDoubleSpinBox(self)
        self._scale_spin.setRange(0.1, 10.0)
        self._scale_spin.setDecimals(2)
        self._scale_spin.setSingleStep(0.1)
        self._scale_spin.setKeyboardTracking(False)
        self._scale_spin.editingFinished.connect(self._commit_specific_fields)
        self._form.addRow("Scale", self._scale_spin)

    def _refresh_specific_fields(self) -> None:
        clip = self._clip
        if not isinstance(clip, (ImageClip, StickerClip)):
            return

        with block_signals(self._scale_spin):
            self._scale_spin.setValue(clip.scale)

    def _commit_specific_fields(self) -> None:
        clip = self._clip
        if not isinstance(clip, (ImageClip, StickerClip)):
            return

        self._apply_property_update(clip, "scale", float(self._scale_spin.value()))
