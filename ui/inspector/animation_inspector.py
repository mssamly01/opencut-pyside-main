from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.controllers.playback_controller import PlaybackController
from app.controllers.timeline_controller import TimelineController
from app.domain.clips.audio_clip import AudioClip
from app.domain.clips.base_clip import BaseClip
from app.domain.clips.image_clip import ImageClip
from app.domain.clips.sticker_clip import StickerClip
from app.domain.clips.text_clip import TextClip
from app.domain.clips.video_clip import VideoClip
from app.domain.keyframe import Keyframe
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class _PropertyRowSpec:
    label: str
    property_name: str
    value_min: float
    value_max: float
    static_default: float


_VISUAL_ROWS: tuple[_PropertyRowSpec, ...] = (
    _PropertyRowSpec("Position X", "position_x", -2.0, 3.0, 0.5),
    _PropertyRowSpec("Position Y", "position_y", -2.0, 3.0, 0.5),
    _PropertyRowSpec("Scale", "scale", 0.05, 8.0, 1.0),
    _PropertyRowSpec("Rotation", "rotation", -180.0, 180.0, 0.0),
    _PropertyRowSpec("Opacity", "opacity", 0.0, 1.0, 1.0),
)

_AUDIO_ROWS: tuple[_PropertyRowSpec, ...] = (
    _PropertyRowSpec("Gain (dB)", "gain_db", -60.0, 12.0, 0.0),
)

_VIDEO_EXTRA_ROWS: tuple[_PropertyRowSpec, ...] = (
    _PropertyRowSpec("Speed", "playback_speed", 0.1, 8.0, 1.0),
)


def _keyframes_for_clip(clip: BaseClip, property_name: str) -> list[Keyframe]:
    attr_name = f"{property_name}_keyframes"
    keyframes = getattr(clip, attr_name, None)
    if not isinstance(keyframes, list):
        return []
    return keyframes


class _BezierCurvePreview(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(80, 80)
        self._cp1 = QPointF(0.42, 0.0)
        self._cp2 = QPointF(0.58, 1.0)
        self._dragging_index: int | None = None
        self._on_changed: Callable[[QPointF, QPointF], None] = lambda _cp1, _cp2: None
        self._on_release: Callable[[QPointF, QPointF], None] = lambda _cp1, _cp2: None

    def set_control_points(
        self,
        cp1_dx: float,
        cp1_dy: float,
        cp2_dx: float,
        cp2_dy: float,
    ) -> None:
        self._cp1 = QPointF(max(0.0, min(1.0, cp1_dx)), cp1_dy)
        self._cp2 = QPointF(max(0.0, min(1.0, cp2_dx)), cp2_dy)
        self.update()

    def set_on_changed(self, callback: Callable[[QPointF, QPointF], None]) -> None:
        self._on_changed = callback

    def set_on_release(self, callback: Callable[[QPointF, QPointF], None]) -> None:
        self._on_release = callback

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(4, 4, -4, -4)
        painter.fillRect(self.rect(), QColor("#1a1d23"))
        painter.setPen(QPen(QColor("#3a4452"), 1))
        painter.drawRect(rect)

        path = QPainterPath()
        path.moveTo(self._to_widget(rect, QPointF(0.0, 0.0)))
        path.cubicTo(
            self._to_widget(rect, self._cp1),
            self._to_widget(rect, self._cp2),
            self._to_widget(rect, QPointF(1.0, 1.0)),
        )
        painter.setPen(QPen(QColor("#f6c453"), 2))
        painter.drawPath(path)

        painter.setBrush(QBrush(QColor("#ff5a36")))
        painter.setPen(QPen(QColor("#101418"), 1))
        painter.drawEllipse(self._to_widget(rect, self._cp1), 4.0, 4.0)
        painter.drawEllipse(self._to_widget(rect, self._cp2), 4.0, 4.0)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        rect = self.rect().adjusted(4, 4, -4, -4)
        pointer = event.position()
        for index, cp in enumerate((self._cp1, self._cp2)):
            point = self._to_widget(rect, cp)
            if (point - pointer).manhattanLength() < 12:
                self._dragging_index = index
                return
        self._dragging_index = None

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._dragging_index is None:
            return
        rect = self.rect().adjusted(4, 4, -4, -4)
        logical = self._from_widget(rect, event.position())
        if self._dragging_index == 0:
            self._cp1 = logical
        else:
            self._cp2 = logical
        self.update()
        self._on_changed(self._cp1, self._cp2)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._dragging_index is not None:
            self._on_release(self._cp1, self._cp2)
        self._dragging_index = None
        super().mouseReleaseEvent(event)

    @staticmethod
    def _to_widget(rect, point: QPointF) -> QPointF:
        return QPointF(
            rect.left() + point.x() * rect.width(),
            rect.bottom() - point.y() * rect.height(),
        )

    @staticmethod
    def _from_widget(rect, point: QPointF) -> QPointF:
        dx = max(0.0, min(1.0, (point.x() - rect.left()) / max(1.0, rect.width())))
        dy = (rect.bottom() - point.y()) / max(1.0, rect.height())
        dy = max(-1.5, min(2.5, dy))
        return QPointF(dx, dy)


class _KeyframeRow(QWidget):
    def __init__(
        self,
        timeline_controller: TimelineController,
        playback_controller: PlaybackController,
        clip: BaseClip,
        spec: _PropertyRowSpec,
        selection_changed: Callable[[_KeyframeRow], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._timeline_controller = timeline_controller
        self._playback_controller = playback_controller
        self._clip = clip
        self._spec = spec
        self._selection_changed = selection_changed

        self._selected_time: float | None = None
        self._dragging = False
        self._drag_original_time: float | None = None
        self._drag_preview_time: float | None = None
        self.setMinimumHeight(22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_clip(self, clip: BaseClip) -> None:
        self._clip = clip
        self._selected_time = None
        self._dragging = False
        self._drag_original_time = None
        self._drag_preview_time = None
        self.update()

    def spec(self) -> _PropertyRowSpec:
        return self._spec

    def selected_keyframe(self) -> Keyframe | None:
        if self._selected_time is None:
            return None
        keyframes = _keyframes_for_clip(self._clip, self._spec.property_name)
        if not keyframes:
            return None
        closest = min(
            keyframes,
            key=lambda item: abs(float(item.time_seconds) - float(self._selected_time)),
        )
        if abs(float(closest.time_seconds) - float(self._selected_time)) > 1e-3:
            return None
        return closest

    def clear_selected(self) -> None:
        self._selected_time = None
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self.rect().adjusted(2, 2, -2, -2)
        painter.fillRect(rect, QColor("#202733"))
        painter.setPen(QPen(QColor("#304052"), 1))
        painter.drawRect(rect)

        center_y = rect.center().y()
        painter.setPen(QPen(QColor("#47617a"), 1))
        painter.drawLine(rect.left() + 4, center_y, rect.right() - 4, center_y)

        keyframes = _keyframes_for_clip(self._clip, self._spec.property_name)
        if not keyframes:
            return

        selected = self.selected_keyframe()
        selected_time = float(selected.time_seconds) if selected is not None else None
        for keyframe in keyframes:
            time_seconds = float(keyframe.time_seconds)
            if (
                self._dragging
                and self._drag_original_time is not None
                and abs(time_seconds - self._drag_original_time) <= 1e-3
            ):
                if self._drag_preview_time is not None:
                    time_seconds = self._drag_preview_time
            x = self._time_to_x(time_seconds)
            is_selected = selected_time is not None and abs(time_seconds - selected_time) <= 1e-3

            color = QColor("#ff7a45") if is_selected else QColor("#f6c453")
            painter.setBrush(color)
            painter.setPen(QPen(QColor("#101418"), 1))
            half = 4.0
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(x, center_y - half),
                        QPointF(x + half, center_y),
                        QPointF(x, center_y + half),
                        QPointF(x - half, center_y),
                    ]
                )
            )

        playhead_time = self._time_in_clip(self._playback_controller.current_time())
        playhead_x = self._time_to_x(playhead_time)
        painter.setPen(QPen(QColor("#ff5a36"), 1))
        painter.drawLine(playhead_x, rect.top(), playhead_x, rect.bottom())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        keyframes = _keyframes_for_clip(self._clip, self._spec.property_name)
        hit_index = self._hit_keyframe_index(event.position().x(), keyframes)
        if hit_index is None:
            self._selected_time = None
            self._selection_changed(self)
            self.update()
            event.accept()
            return

        selected = keyframes[hit_index]
        self._selected_time = float(selected.time_seconds)
        self._dragging = True
        self._drag_original_time = float(selected.time_seconds)
        self._drag_preview_time = float(selected.time_seconds)
        self._selection_changed(self)
        self.update()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._dragging or self._drag_original_time is None:
            super().mouseMoveEvent(event)
            return
        self._drag_preview_time = self._x_to_time(event.position().x())
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self._dragging:
            super().mouseReleaseEvent(event)
            return

        old_time = self._drag_original_time
        new_time = self._drag_preview_time
        self._dragging = False
        self._drag_original_time = None
        self._drag_preview_time = None
        if old_time is None or new_time is None:
            self.update()
            event.accept()
            return

        if abs(new_time - old_time) > 1e-3:
            moved = self._timeline_controller.move_keyframe(
                self._clip.clip_id,
                self._spec.property_name,
                old_time,
                new_time,
            )
            if moved:
                self._selected_time = new_time

        self.update()
        event.accept()

    def _time_in_clip(self, absolute_time: float) -> float:
        return max(0.0, min(float(self._clip.duration), absolute_time - float(self._clip.timeline_start)))

    def _timeline_bounds(self) -> tuple[float, float]:
        left = 8.0
        right = max(left + 1.0, float(self.width()) - 8.0)
        return left, right

    def _time_to_x(self, time_seconds: float) -> float:
        left, right = self._timeline_bounds()
        duration = max(1e-6, float(self._clip.duration))
        ratio = max(0.0, min(1.0, float(time_seconds) / duration))
        return left + ratio * (right - left)

    def _x_to_time(self, x: float) -> float:
        left, right = self._timeline_bounds()
        if right <= left:
            return 0.0
        ratio = (float(x) - left) / (right - left)
        ratio = max(0.0, min(1.0, ratio))
        return ratio * max(0.0, float(self._clip.duration))

    def _hit_keyframe_index(self, x: float, keyframes: list[Keyframe]) -> int | None:
        if not keyframes:
            return None
        for index, keyframe in enumerate(keyframes):
            if abs(self._time_to_x(float(keyframe.time_seconds)) - float(x)) <= 7.0:
                return index
        return None


class AnimationInspector(QWidget):
    def __init__(
        self,
        timeline_controller: TimelineController,
        playback_controller: PlaybackController,
        clip: BaseClip,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._timeline_controller = timeline_controller
        self._playback_controller = playback_controller
        self._clip = clip
        self._rows: list[_KeyframeRow] = []
        self._active_row: _KeyframeRow | None = None
        self._syncing_bezier_ui = False

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        self._unsupported_label = QLabel("Keyframes are not available for this clip type.", self)
        self._unsupported_label.setStyleSheet("color: #6f7d8d;")
        self._unsupported_label.setWordWrap(True)
        root.addWidget(self._unsupported_label)

        self._rows_panel = QWidget(self)
        self._rows_layout = QVBoxLayout(self._rows_panel)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(4)
        root.addWidget(self._rows_panel)

        self._edit_panel = QWidget(self)
        edit_form = QFormLayout(self._edit_panel)
        edit_form.setContentsMargins(0, 6, 0, 0)
        edit_form.setSpacing(6)

        self._value_spin = QDoubleSpinBox(self._edit_panel)
        self._value_spin.setDecimals(3)
        self._value_spin.setSingleStep(0.05)
        self._value_spin.valueChanged.connect(self._on_value_changed)

        self._interp_combo = QComboBox(self._edit_panel)
        for label, value in (
            ("Linear", "linear"),
            ("Hold", "hold"),
            ("Ease In", "ease_in"),
            ("Ease Out", "ease_out"),
            ("Ease In/Out", "ease_in_out"),
            ("Bezier", "bezier"),
        ):
            self._interp_combo.addItem(label, value)
        self._interp_combo.currentIndexChanged.connect(self._on_interp_changed)

        self._bezier_controls = QWidget(self._edit_panel)
        bezier_controls_layout = QHBoxLayout(self._bezier_controls)
        bezier_controls_layout.setContentsMargins(0, 0, 0, 0)
        bezier_controls_layout.setSpacing(4)

        self._cp1_dx_spin = self._make_bezier_spinbox(0.0, 1.0)
        self._cp1_dy_spin = self._make_bezier_spinbox(-1.5, 2.5)
        self._cp2_dx_spin = self._make_bezier_spinbox(0.0, 1.0)
        self._cp2_dy_spin = self._make_bezier_spinbox(-1.5, 2.5)

        bezier_controls_layout.addWidget(QLabel("CP1 x", self._bezier_controls))
        bezier_controls_layout.addWidget(self._cp1_dx_spin)
        bezier_controls_layout.addWidget(QLabel("y", self._bezier_controls))
        bezier_controls_layout.addWidget(self._cp1_dy_spin)
        bezier_controls_layout.addSpacing(6)
        bezier_controls_layout.addWidget(QLabel("CP2 x", self._bezier_controls))
        bezier_controls_layout.addWidget(self._cp2_dx_spin)
        bezier_controls_layout.addWidget(QLabel("y", self._bezier_controls))
        bezier_controls_layout.addWidget(self._cp2_dy_spin)

        self._bezier_preview = _BezierCurvePreview(self._edit_panel)
        self._bezier_preview.set_on_changed(self._on_bezier_preview_changed)
        self._bezier_preview.set_on_release(self._on_bezier_preview_released)

        self._delete_button = QPushButton("Delete keyframe", self._edit_panel)
        self._delete_button.clicked.connect(self._on_delete_clicked)

        edit_form.addRow("Value", self._value_spin)
        edit_form.addRow("Interpolation", self._interp_combo)
        edit_form.addRow("Bezier CP", self._bezier_controls)
        edit_form.addRow("Bezier curve", self._bezier_preview)
        edit_form.addRow(self._delete_button)
        root.addWidget(self._edit_panel)
        root.addStretch(1)

        self._timeline_controller.timeline_changed.connect(self._on_timeline_changed)
        self.set_clip(clip)

    def set_clip(self, clip: BaseClip) -> None:
        self._clip = clip
        self._active_row = None
        self._rebuild_rows()
        self._sync_edit_panel()

    def _rebuild_rows(self) -> None:
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._rows.clear()

        if isinstance(self._clip, VideoClip):
            specs = (*_VISUAL_ROWS, *_VIDEO_EXTRA_ROWS)
        elif isinstance(self._clip, (ImageClip, TextClip, StickerClip)):
            specs = _VISUAL_ROWS
        elif isinstance(self._clip, AudioClip):
            specs = _AUDIO_ROWS
        else:
            specs = ()

        supports_keyframes = len(specs) > 0
        self._unsupported_label.setVisible(not supports_keyframes)
        self._rows_panel.setVisible(supports_keyframes)
        self._edit_panel.setVisible(supports_keyframes)
        if not supports_keyframes:
            return

        for spec in specs:
            row_container = QWidget(self._rows_panel)
            row_layout = QHBoxLayout(row_container)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            name_label = QLabel(spec.label, row_container)
            name_label.setMinimumWidth(86)

            add_button = QPushButton("+", row_container)
            add_button.setFixedWidth(24)
            add_button.setToolTip("Add keyframe at playhead")
            add_button.clicked.connect(
                lambda _checked=False, row_spec=spec: self._on_add_keyframe(row_spec)
            )

            row = _KeyframeRow(
                timeline_controller=self._timeline_controller,
                playback_controller=self._playback_controller,
                clip=self._clip,
                spec=spec,
                selection_changed=self._on_row_selection_changed,
                parent=row_container,
            )

            row_layout.addWidget(name_label)
            row_layout.addWidget(add_button)
            row_layout.addWidget(row, 1)
            self._rows_layout.addWidget(row_container)
            self._rows.append(row)

    def _on_add_keyframe(self, spec: _PropertyRowSpec) -> None:
        playhead_abs = float(self._playback_controller.current_time())
        time_in_clip = max(
            0.0,
            min(float(self._clip.duration), playhead_abs - float(self._clip.timeline_start)),
        )
        current_value = float(getattr(self._clip, spec.property_name, spec.static_default))
        self._timeline_controller.add_keyframe(
            self._clip.clip_id,
            spec.property_name,
            time_in_clip,
            current_value,
        )

    def _on_row_selection_changed(self, row: _KeyframeRow) -> None:
        for other in self._rows:
            if other is not row:
                other.clear_selected()
        self._active_row = row if row.selected_keyframe() is not None else None
        self._sync_edit_panel()

    def _sync_edit_panel(self) -> None:
        keyframe = self._active_row.selected_keyframe() if self._active_row is not None else None
        enabled = keyframe is not None
        self._value_spin.setEnabled(enabled)
        self._interp_combo.setEnabled(enabled)
        self._delete_button.setEnabled(enabled)
        self._bezier_controls.setEnabled(enabled)
        self._bezier_preview.setEnabled(enabled)
        if not enabled:
            self._bezier_controls.setVisible(False)
            self._bezier_preview.setVisible(False)
            return

        spec = self._active_row.spec()
        self._value_spin.blockSignals(True)
        self._value_spin.setRange(spec.value_min, spec.value_max)
        self._value_spin.setValue(float(keyframe.value))
        self._value_spin.blockSignals(False)

        combo_index = self._interp_combo.findData(keyframe.interpolation)
        self._interp_combo.blockSignals(True)
        self._interp_combo.setCurrentIndex(combo_index if combo_index >= 0 else 0)
        self._interp_combo.blockSignals(False)

        is_bezier = keyframe.interpolation == "bezier"
        self._bezier_controls.setVisible(is_bezier)
        self._bezier_preview.setVisible(is_bezier)
        if is_bezier:
            self._syncing_bezier_ui = True
            try:
                self._cp1_dx_spin.setValue(float(keyframe.bezier_cp1_dx))
                self._cp1_dy_spin.setValue(float(keyframe.bezier_cp1_dy))
                self._cp2_dx_spin.setValue(float(keyframe.bezier_cp2_dx))
                self._cp2_dy_spin.setValue(float(keyframe.bezier_cp2_dy))
                self._bezier_preview.set_control_points(
                    float(keyframe.bezier_cp1_dx),
                    float(keyframe.bezier_cp1_dy),
                    float(keyframe.bezier_cp2_dx),
                    float(keyframe.bezier_cp2_dy),
                )
            finally:
                self._syncing_bezier_ui = False

    def _on_value_changed(self, value: float) -> None:
        if self._active_row is None:
            return
        keyframe = self._active_row.selected_keyframe()
        if keyframe is None:
            return
        self._timeline_controller.update_keyframe_value(
            self._clip.clip_id,
            self._active_row.spec().property_name,
            float(keyframe.time_seconds),
            float(value),
        )

    def _on_interp_changed(self, _index: int) -> None:
        if self._active_row is None:
            return
        keyframe = self._active_row.selected_keyframe()
        if keyframe is None:
            return
        mode = str(self._interp_combo.currentData() or "linear")
        self._timeline_controller.set_keyframe_interpolation(
            self._clip.clip_id,
            self._active_row.spec().property_name,
            float(keyframe.time_seconds),
            mode,
        )
        self._sync_edit_panel()

    def _on_delete_clicked(self) -> None:
        if self._active_row is None:
            return
        keyframe = self._active_row.selected_keyframe()
        if keyframe is None:
            return
        self._timeline_controller.remove_keyframe(
            self._clip.clip_id,
            self._active_row.spec().property_name,
            float(keyframe.time_seconds),
        )
        self._active_row.clear_selected()
        self._active_row = None
        self._sync_edit_panel()

    def _on_bezier_spin_changed(self, _value: float) -> None:
        if self._syncing_bezier_ui:
            return
        self._update_active_bezier(
            cp1_dx=self._cp1_dx_spin.value(),
            cp1_dy=self._cp1_dy_spin.value(),
            cp2_dx=self._cp2_dx_spin.value(),
            cp2_dy=self._cp2_dy_spin.value(),
        )

    def _on_bezier_preview_changed(self, cp1: QPointF, cp2: QPointF) -> None:
        if self._syncing_bezier_ui:
            return
        self._syncing_bezier_ui = True
        try:
            self._cp1_dx_spin.setValue(float(cp1.x()))
            self._cp1_dy_spin.setValue(float(cp1.y()))
            self._cp2_dx_spin.setValue(float(cp2.x()))
            self._cp2_dy_spin.setValue(float(cp2.y()))
        finally:
            self._syncing_bezier_ui = False

    def _on_bezier_preview_released(self, cp1: QPointF, cp2: QPointF) -> None:
        self._update_active_bezier(
            cp1_dx=float(cp1.x()),
            cp1_dy=float(cp1.y()),
            cp2_dx=float(cp2.x()),
            cp2_dy=float(cp2.y()),
        )

    def _update_active_bezier(
        self,
        cp1_dx: float,
        cp1_dy: float,
        cp2_dx: float,
        cp2_dy: float,
    ) -> None:
        if self._active_row is None:
            return
        keyframe = self._active_row.selected_keyframe()
        if keyframe is None or keyframe.interpolation != "bezier":
            return
        self._timeline_controller.update_keyframe_bezier(
            clip_id=self._clip.clip_id,
            property_name=self._active_row.spec().property_name,
            time_seconds=float(keyframe.time_seconds),
            cp1_dx=cp1_dx,
            cp1_dy=cp1_dy,
            cp2_dx=cp2_dx,
            cp2_dy=cp2_dy,
        )

    def _on_timeline_changed(self) -> None:
        for row in self._rows:
            row.update()
        self._sync_edit_panel()

    def _make_bezier_spinbox(self, minimum: float, maximum: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(self._edit_panel)
        spin.setRange(minimum, maximum)
        spin.setDecimals(3)
        spin.setSingleStep(0.01)
        spin.valueChanged.connect(self._on_bezier_spin_changed)
        return spin
