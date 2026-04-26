from __future__ import annotations

from dataclasses import dataclass

from app.domain.clips.text_clip import TextClip
from app.ui.inspector._clip_inspector_base import ClipInspectorBase, block_signals
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)


@dataclass(frozen=True)
class _CaptionPreset:
    label: str
    font_family: str = "Arial"
    font_size: int = 48
    bold: bool = False
    italic: bool = False
    alignment: str = "center"
    color: str = "#ffffff"
    outline_color: str = "#000000"
    outline_width: float = 0.0
    background_color: str = "#000000"
    background_opacity: float = 0.0
    shadow_color: str = "#000000"
    shadow_offset_x: float = 0.0
    shadow_offset_y: float = 0.0


CAPTION_PRESETS: dict[str, _CaptionPreset] = {
    "default": _CaptionPreset(label="Default"),
    "outline_white": _CaptionPreset(
        label="Outline White",
        font_size=46,
        bold=True,
        outline_color="#000000",
        outline_width=3.0,
    ),
    "yellow_box": _CaptionPreset(
        label="Yellow Box",
        font_size=44,
        bold=True,
        color="#111111",
        background_color="#ffe34d",
        background_opacity=0.95,
    ),
    "soft_shadow": _CaptionPreset(
        label="Soft Shadow",
        font_size=46,
        shadow_color="#000000",
        shadow_offset_x=3.0,
        shadow_offset_y=3.0,
    ),
    "capcut_pop": _CaptionPreset(
        label="CapCut Pop",
        font_size=54,
        bold=True,
        color="#ffffff",
        outline_color="#000000",
        outline_width=4.0,
        shadow_color="#000000",
        shadow_offset_x=2.0,
        shadow_offset_y=3.0,
    ),
}


class TextInspector(ClipInspectorBase):
    def __init__(self, timeline_controller: object, clip: TextClip, parent=None) -> None:
        super().__init__(timeline_controller, clip, parent)

    def _build_specific_fields(self) -> None:
        self._preset_combo = QComboBox(self)
        self._preset_combo.addItem("-", userData="")
        for key, preset in CAPTION_PRESETS.items():
            self._preset_combo.addItem(self.tr(preset.label), userData=key)
        self._preset_combo.activated.connect(self._apply_selected_preset)
        self._form.addRow(self.tr("Preset"), self._preset_combo)

        self._content_edit = QLineEdit(self)
        self._content_edit.editingFinished.connect(self._commit_specific_fields)
        self._form.addRow(self.tr("Nội dung"), self._content_edit)

        self._font_family_edit = QLineEdit(self)
        self._font_family_edit.editingFinished.connect(self._commit_specific_fields)
        self._form.addRow(self.tr("Phông chữ"), self._font_family_edit)

        self._font_size_spin = QDoubleSpinBox(self)
        self._font_size_spin.setRange(8, 512)
        self._font_size_spin.setDecimals(0)
        self._font_size_spin.setSingleStep(4)
        self._font_size_spin.setKeyboardTracking(False)
        self._font_size_spin.editingFinished.connect(self._commit_specific_fields)
        self._form.addRow(self.tr("Cỡ chữ"), self._font_size_spin)

        self._bold_check = QCheckBox(self.tr("In đậm"), self)
        self._bold_check.toggled.connect(self._commit_specific_fields)
        self._form.addRow("", self._bold_check)

        self._italic_check = QCheckBox(self.tr("In nghiêng"), self)
        self._italic_check.toggled.connect(self._commit_specific_fields)
        self._form.addRow("", self._italic_check)

        self._alignment_combo = QComboBox(self)
        self._alignment_combo.addItem(self.tr("Trái"), userData="left")
        self._alignment_combo.addItem(self.tr("Giữa"), userData="center")
        self._alignment_combo.addItem(self.tr("Phải"), userData="right")
        self._alignment_combo.currentIndexChanged.connect(self._commit_specific_fields)
        self._form.addRow(self.tr("Căn lề"), self._alignment_combo)

        self._color_edit = QLineEdit(self)
        self._color_edit.editingFinished.connect(self._commit_specific_fields)
        self._form.addRow(self.tr("Màu sắc"), self._color_edit)

        self._highlight_color_edit = QLineEdit(self)
        self._highlight_color_edit.editingFinished.connect(self._commit_specific_fields)
        self._highlight_color_pick_button = QPushButton("...", self)
        self._highlight_color_pick_button.setMaximumWidth(36)
        self._highlight_color_pick_button.clicked.connect(self._on_pick_highlight_color)
        highlight_row = QWidget(self)
        highlight_layout = QHBoxLayout(highlight_row)
        highlight_layout.setContentsMargins(0, 0, 0, 0)
        highlight_layout.setSpacing(6)
        highlight_layout.addWidget(self._highlight_color_edit, 1)
        highlight_layout.addWidget(self._highlight_color_pick_button)
        self._form.addRow(self.tr("Đánh dấu"), highlight_row)

        self._pos_x_spin = QDoubleSpinBox(self)
        self._pos_x_spin.setRange(0.0, 1.0)
        self._pos_x_spin.setDecimals(2)
        self._pos_x_spin.setSingleStep(0.05)
        self._pos_x_spin.setKeyboardTracking(False)
        self._pos_x_spin.editingFinished.connect(self._commit_specific_fields)
        self._form.addRow(self.tr("Vị trí X"), self._pos_x_spin)

        self._pos_y_spin = QDoubleSpinBox(self)
        self._pos_y_spin.setRange(0.0, 1.0)
        self._pos_y_spin.setDecimals(2)
        self._pos_y_spin.setSingleStep(0.05)
        self._pos_y_spin.setKeyboardTracking(False)
        self._pos_y_spin.editingFinished.connect(self._commit_specific_fields)
        self._form.addRow(self.tr("Vị trí Y"), self._pos_y_spin)

        self._outline_color_edit = QLineEdit(self)
        self._outline_color_edit.editingFinished.connect(self._commit_specific_fields)
        self._form.addRow(self.tr("Màu viền"), self._outline_color_edit)

        self._outline_width_spin = QDoubleSpinBox(self)
        self._outline_width_spin.setRange(0.0, 32.0)
        self._outline_width_spin.setDecimals(1)
        self._outline_width_spin.setSingleStep(0.5)
        self._outline_width_spin.setKeyboardTracking(False)
        self._outline_width_spin.editingFinished.connect(self._commit_specific_fields)
        self._form.addRow(self.tr("Độ dày viền"), self._outline_width_spin)

        self._bg_color_edit = QLineEdit(self)
        self._bg_color_edit.editingFinished.connect(self._commit_specific_fields)
        self._form.addRow(self.tr("Màu nền"), self._bg_color_edit)

        self._bg_opacity_spin = QDoubleSpinBox(self)
        self._bg_opacity_spin.setRange(0.0, 1.0)
        self._bg_opacity_spin.setDecimals(2)
        self._bg_opacity_spin.setSingleStep(0.05)
        self._bg_opacity_spin.setKeyboardTracking(False)
        self._bg_opacity_spin.editingFinished.connect(self._commit_specific_fields)
        self._form.addRow(self.tr("Độ đục nền"), self._bg_opacity_spin)

        self._shadow_color_edit = QLineEdit(self)
        self._shadow_color_edit.editingFinished.connect(self._commit_specific_fields)
        self._form.addRow(self.tr("Màu bóng"), self._shadow_color_edit)

        self._shadow_offset_x_spin = QDoubleSpinBox(self)
        self._shadow_offset_x_spin.setRange(-64.0, 64.0)
        self._shadow_offset_x_spin.setDecimals(1)
        self._shadow_offset_x_spin.setSingleStep(0.5)
        self._shadow_offset_x_spin.setKeyboardTracking(False)
        self._shadow_offset_x_spin.editingFinished.connect(self._commit_specific_fields)
        self._form.addRow(self.tr("Lệch bóng X"), self._shadow_offset_x_spin)

        self._shadow_offset_y_spin = QDoubleSpinBox(self)
        self._shadow_offset_y_spin.setRange(-64.0, 64.0)
        self._shadow_offset_y_spin.setDecimals(1)
        self._shadow_offset_y_spin.setSingleStep(0.5)
        self._shadow_offset_y_spin.setKeyboardTracking(False)
        self._shadow_offset_y_spin.editingFinished.connect(self._commit_specific_fields)
        self._form.addRow(self.tr("Lệch bóng Y"), self._shadow_offset_y_spin)

        self._auto_split_words_button = QPushButton(self.tr("Tự tách từng từ"), self)
        self._auto_split_words_button.clicked.connect(self._on_auto_split_words)
        self._form.addRow("", self._auto_split_words_button)

    def _refresh_specific_fields(self) -> None:
        clip = self._clip
        if not isinstance(clip, TextClip):
            return

        alignment_index = max(0, self._alignment_combo.findData(clip.alignment or "center"))

        with block_signals(
            self._preset_combo,
            self._content_edit,
            self._font_family_edit,
            self._font_size_spin,
            self._bold_check,
            self._italic_check,
            self._alignment_combo,
            self._color_edit,
            self._highlight_color_edit,
            self._pos_x_spin,
            self._pos_y_spin,
            self._outline_color_edit,
            self._outline_width_spin,
            self._bg_color_edit,
            self._bg_opacity_spin,
            self._shadow_color_edit,
            self._shadow_offset_x_spin,
            self._shadow_offset_y_spin,
        ):
            self._preset_combo.setCurrentIndex(0)
            self._content_edit.setText(clip.content)
            self._font_family_edit.setText(clip.font_family)
            self._font_size_spin.setValue(clip.font_size)
            self._bold_check.setChecked(clip.bold)
            self._italic_check.setChecked(clip.italic)
            self._alignment_combo.setCurrentIndex(alignment_index)
            self._color_edit.setText(clip.color)
            self._highlight_color_edit.setText(clip.highlight_color)
            self._pos_x_spin.setValue(clip.position_x)
            self._pos_y_spin.setValue(clip.position_y)
            self._outline_color_edit.setText(clip.outline_color)
            self._outline_width_spin.setValue(clip.outline_width)
            self._bg_color_edit.setText(clip.background_color)
            self._bg_opacity_spin.setValue(clip.background_opacity)
            self._shadow_color_edit.setText(clip.shadow_color)
            self._shadow_offset_x_spin.setValue(clip.shadow_offset_x)
            self._shadow_offset_y_spin.setValue(clip.shadow_offset_y)

    def _commit_specific_fields(self) -> None:
        clip = self._clip
        if not isinstance(clip, TextClip):
            return

        alignment_value = self._alignment_combo.currentData()
        if not isinstance(alignment_value, str) or not alignment_value:
            alignment_value = "center"

        self._apply_property_update(clip, "content", self._content_edit.text())
        self._apply_property_update(clip, "font_family", self._font_family_edit.text() or "Arial")
        self._apply_property_update(clip, "font_size", int(self._font_size_spin.value()))
        self._apply_property_update(clip, "bold", bool(self._bold_check.isChecked()))
        self._apply_property_update(clip, "italic", bool(self._italic_check.isChecked()))
        self._apply_property_update(clip, "alignment", alignment_value)
        self._apply_property_update(clip, "color", self._color_edit.text())
        self._apply_property_update(clip, "highlight_color", self._highlight_color_edit.text() or "#ffd166")
        self._apply_property_update(clip, "position_x", float(self._pos_x_spin.value()))
        self._apply_property_update(clip, "position_y", float(self._pos_y_spin.value()))
        self._apply_property_update(clip, "outline_color", self._outline_color_edit.text())
        self._apply_property_update(clip, "outline_width", float(self._outline_width_spin.value()))
        self._apply_property_update(clip, "background_color", self._bg_color_edit.text())
        self._apply_property_update(clip, "background_opacity", float(self._bg_opacity_spin.value()))
        self._apply_property_update(clip, "shadow_color", self._shadow_color_edit.text())
        self._apply_property_update(clip, "shadow_offset_x", float(self._shadow_offset_x_spin.value()))
        self._apply_property_update(clip, "shadow_offset_y", float(self._shadow_offset_y_spin.value()))

    def _apply_selected_preset(self, index: int) -> None:
        clip = self._clip
        if not isinstance(clip, TextClip):
            return

        preset_key = self._preset_combo.itemData(index)
        if not isinstance(preset_key, str) or not preset_key:
            return

        preset = CAPTION_PRESETS.get(preset_key)
        if preset is None:
            return

        self._apply_property_update(clip, "font_family", preset.font_family)
        self._apply_property_update(clip, "font_size", preset.font_size)
        self._apply_property_update(clip, "bold", preset.bold)
        self._apply_property_update(clip, "italic", preset.italic)
        self._apply_property_update(clip, "alignment", preset.alignment)
        self._apply_property_update(clip, "color", preset.color)
        self._apply_property_update(clip, "outline_color", preset.outline_color)
        self._apply_property_update(clip, "outline_width", preset.outline_width)
        self._apply_property_update(clip, "background_color", preset.background_color)
        self._apply_property_update(clip, "background_opacity", preset.background_opacity)
        self._apply_property_update(clip, "shadow_color", preset.shadow_color)
        self._apply_property_update(clip, "shadow_offset_x", preset.shadow_offset_x)
        self._apply_property_update(clip, "shadow_offset_y", preset.shadow_offset_y)

    def _on_pick_highlight_color(self) -> None:
        clip = self._clip
        if not isinstance(clip, TextClip):
            return

        initial = QColor(self._highlight_color_edit.text() or clip.highlight_color or "#ffd166")
        color = QColorDialog.getColor(initial, self, self.tr("Chọn màu đánh dấu"))
        if not color.isValid():
            return

        selected = color.name()
        self._highlight_color_edit.setText(selected)
        self._apply_property_update(clip, "highlight_color", selected)

    def _on_auto_split_words(self) -> None:
        clip = self._clip
        if not isinstance(clip, TextClip):
            return

        word_timings = clip.split_words_evenly()
        if not word_timings:
            return
        self._apply_property_update(clip, "word_timings", word_timings)
