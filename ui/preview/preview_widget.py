from __future__ import annotations

import math
from dataclasses import dataclass

from app.controllers.playback_controller import PlaybackController
from app.controllers.project_controller import ProjectController
from app.controllers.selection_controller import SelectionController
from app.controllers.timeline_controller import TimelineController
from app.domain.clips.base_clip import BaseClip
from app.domain.clips.image_clip import ImageClip
from app.domain.clips.text_clip import TextClip
from app.domain.clips.video_clip import VideoClip
from app.services.keyframe_evaluator import resolve_clip_value_at
from app.ui.preview.playback_toolbar import PlaybackPlayButton, PlaybackTimeLabel
from app.ui.shared.icons import build_icon
from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
    QTransform,
)
from PySide6.QtWidgets import QHBoxLayout, QMenu, QPushButton, QToolButton, QVBoxLayout, QWidget

_ASPECT_PRESETS: list[tuple[str, int, int]] = [
    ("16:9", 1920, 1080),
    ("9:16", 1080, 1920),
    ("1:1", 1080, 1080),
    ("4:3", 1440, 1080),
    ("21:9", 2560, 1080),
]

_HANDLE_RADIUS = 6.0
_ROTATION_HANDLE_OFFSET = 28.0


@dataclass(slots=True)
class _DragState:
    handle: str  # body | tl | tr | bl | br | rot
    clip_id: str
    start_widget_pos: QPointF
    start_position_x: float
    start_position_y: float
    start_scale: float
    start_rotation: float
    start_radius: float = 0.0
    start_angle: float = 0.0


class _PreviewCanvas(QWidget):
    def __init__(
        self,
        project_controller: ProjectController,
        timeline_controller: TimelineController,
        selection_controller: SelectionController,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._project_controller = project_controller
        self._timeline_controller = timeline_controller
        self._selection_controller = selection_controller
        self._preview_image: QImage | None = None
        self._preview_message = "No frame"
        self._current_time = 0.0
        self._is_playing = False
        self._safe_zone_enabled = False
        self._drag_state: _DragState | None = None

        self.setMouseTracking(True)
        self.setMinimumHeight(240)
        self.setObjectName("preview_canvas")

    def set_preview_state(
        self,
        image: QImage | None,
        message: str,
        current_time: float,
        is_playing: bool,
    ) -> None:
        self._preview_image = image
        self._preview_message = message
        self._current_time = current_time
        self._is_playing = is_playing
        self.update()

    def set_safe_zone_enabled(self, enabled: bool) -> None:
        self._safe_zone_enabled = bool(enabled)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#0c0e12"))

        project_rect = self._project_rect()
        if project_rect.width() <= 1.0 or project_rect.height() <= 1.0:
            return

        painter.fillRect(project_rect, QColor("#11161f"))
        if self._preview_image is None or self._preview_image.isNull():
            painter.setPen(QColor("#8c9bab"))
            painter.drawText(
                project_rect,
                Qt.AlignmentFlag.AlignCenter,
                f"{self._preview_message}\nTime: {self._current_time:0.2f}s",
            )
        else:
            pixmap = QPixmap.fromImage(self._preview_image)
            scaled = pixmap.scaled(
                project_rect.size().toSize(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation
                if self._is_playing
                else Qt.TransformationMode.SmoothTransformation,
            )
            draw_x = project_rect.x() + (project_rect.width() - scaled.width()) / 2.0
            draw_y = project_rect.y() + (project_rect.height() - scaled.height()) / 2.0
            active_clip = self._currently_rendered_clip()
            if active_clip is not None and isinstance(active_clip, (VideoClip, ImageClip)):
                time_in_clip = max(
                    0.0,
                    min(float(active_clip.duration), self._current_time - float(active_clip.timeline_start)),
                )
                scale = max(
                    0.05,
                    min(
                        8.0,
                        resolve_clip_value_at(
                            active_clip,
                            "scale",
                            time_in_clip,
                            default=1.0,
                        ),
                    ),
                )
                rotation = resolve_clip_value_at(
                    active_clip,
                    "rotation",
                    time_in_clip,
                    default=0.0,
                )
                position_x = resolve_clip_value_at(
                    active_clip,
                    "position_x",
                    time_in_clip,
                    default=0.5,
                )
                position_y = resolve_clip_value_at(
                    active_clip,
                    "position_y",
                    time_in_clip,
                    default=0.5,
                )
                opacity = max(
                    0.0,
                    min(
                        1.0,
                        resolve_clip_value_at(
                            active_clip,
                            "opacity",
                            time_in_clip,
                            default=1.0,
                        ),
                    ),
                )

                transform = QTransform()
                center_x = project_rect.center().x() + (position_x - 0.5) * project_rect.width()
                center_y = project_rect.center().y() + (position_y - 0.5) * project_rect.height()
                transform.translate(center_x, center_y)
                transform.rotate(rotation)
                transform.scale(scale, scale)
                transform.translate(-scaled.width() / 2.0, -scaled.height() / 2.0)

                painter.save()
                painter.setOpacity(opacity)
                painter.setTransform(transform, combine=False)
                painter.drawPixmap(0, 0, scaled)
                painter.restore()
            else:
                painter.drawPixmap(int(round(draw_x)), int(round(draw_y)), scaled)
            self._draw_active_text_overlays(painter, project_rect, skip_when_text_base=isinstance(active_clip, TextClip))

        if self._safe_zone_enabled:
            self._draw_safe_zone(painter, project_rect)
        self._draw_transform_overlay(painter, project_rect)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        clip = self._selected_transform_clip()
        if clip is None:
            super().mousePressEvent(event)
            return

        geometry = self._overlay_geometry(clip)
        if geometry is None:
            super().mousePressEvent(event)
            return
        center, corners, handles, _top_center = geometry
        pointer = event.position()

        hit_handle = self._hit_handle(handles, pointer)
        if hit_handle is None:
            polygon_path = self._overlay_path(corners)
            if not polygon_path.contains(pointer):
                super().mousePressEvent(event)
                return
            hit_handle = "body"

        start_radius = max(1.0, self._distance(center, pointer))
        start_angle = math.degrees(math.atan2(pointer.y() - center.y(), pointer.x() - center.x()))
        self._drag_state = _DragState(
            handle=hit_handle,
            clip_id=clip.clip_id,
            start_widget_pos=QPointF(pointer.x(), pointer.y()),
            start_position_x=float(getattr(clip, "position_x", 0.5)),
            start_position_y=float(getattr(clip, "position_y", 0.5)),
            start_scale=float(getattr(clip, "scale", 1.0)),
            start_rotation=float(getattr(clip, "rotation", 0.0)),
            start_radius=start_radius,
            start_angle=start_angle,
        )
        self.setCursor(Qt.CursorShape.ClosedHandCursor if hit_handle == "body" else Qt.CursorShape.SizeAllCursor)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        drag = self._drag_state
        if drag is None:
            super().mouseMoveEvent(event)
            return

        clip = self._clip_by_id(drag.clip_id)
        project_rect = self._project_rect()
        if clip is None or project_rect.width() <= 1.0 or project_rect.height() <= 1.0:
            self._drag_state = None
            self.unsetCursor()
            super().mouseMoveEvent(event)
            return

        pos = event.position()
        if drag.handle == "body":
            dx = pos.x() - drag.start_widget_pos.x()
            dy = pos.y() - drag.start_widget_pos.y()
            self._timeline_controller.set_clip_transform(
                drag.clip_id,
                position_x=drag.start_position_x + (dx / project_rect.width()),
                position_y=drag.start_position_y + (dy / project_rect.height()),
            )
            event.accept()
            return

        geometry = self._overlay_geometry(clip)
        if geometry is None:
            event.accept()
            return
        center, _corners, _handles, _top_center = geometry

        if drag.handle == "rot":
            angle_now = math.degrees(math.atan2(pos.y() - center.y(), pos.x() - center.x()))
            new_rotation = drag.start_rotation + (angle_now - drag.start_angle)
            self._timeline_controller.set_clip_transform(drag.clip_id, rotation=new_rotation)
            event.accept()
            return

        current_radius = max(1.0, self._distance(center, pos))
        ratio = current_radius / max(1.0, drag.start_radius)
        self._timeline_controller.set_clip_transform(drag.clip_id, scale=drag.start_scale * ratio)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_state is not None:
            self._drag_state = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _draw_safe_zone(self, painter: QPainter, project_rect: QRectF) -> None:
        margin_x = project_rect.width() * 0.1
        margin_y = project_rect.height() * 0.1
        safe = QRectF(
            project_rect.left() + margin_x,
            project_rect.top() + margin_y,
            project_rect.width() - margin_x * 2.0,
            project_rect.height() - margin_y * 2.0,
        )
        painter.save()
        painter.setPen(QPen(QColor("#5f7082"), 1, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(safe)
        painter.restore()

    def _draw_transform_overlay(self, painter: QPainter, project_rect: QRectF) -> None:
        clip = self._selected_transform_clip()
        if clip is None:
            return
        geometry = self._overlay_geometry(clip, project_rect)
        if geometry is None:
            return
        _center, corners, handles, top_center = geometry

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor("#00bcd4"), 1.6))
        painter.setBrush(QColor(0, 188, 212, 24))
        from PySide6.QtGui import QPolygonF

        painter.drawPolygon(QPolygonF([corners["tl"], corners["tr"], corners["br"], corners["bl"]]))
        painter.setBrush(QColor("#00bcd4"))
        for handle_name in ("tl", "tr", "bl", "br"):
            point = handles[handle_name]
            painter.drawEllipse(point, _HANDLE_RADIUS, _HANDLE_RADIUS)
        painter.setPen(QPen(QColor("#00bcd4"), 1.0))
        painter.drawLine(top_center, handles["rot"])
        painter.setBrush(QColor("#ff5a36"))
        painter.drawEllipse(handles["rot"], _HANDLE_RADIUS, _HANDLE_RADIUS)
        painter.restore()

    def _draw_active_text_overlays(
        self,
        painter: QPainter,
        project_rect: QRectF,
        *,
        skip_when_text_base: bool,
    ) -> None:
        if skip_when_text_base:
            return
        project = self._project_controller.active_project()
        if project is None or project.width <= 0 or project.height <= 0:
            return

        text_clips = self._active_text_clips()
        if not text_clips:
            return

        scale_factor = project_rect.width() / float(project.width)
        for clip in text_clips:
            self._draw_text_clip_overlay(
                painter=painter,
                clip=clip,
                project_rect=project_rect,
                scale_factor=scale_factor,
            )

    def _active_text_clips(self) -> list[TextClip]:
        project = self._project_controller.active_project()
        if project is None:
            return []
        epsilon = 1e-6
        clips: list[TextClip] = []
        for track in reversed(project.timeline.tracks):
            if track.is_hidden or track.is_muted:
                continue
            for clip in track.sorted_clips():
                if not isinstance(clip, TextClip):
                    continue
                if clip.is_muted:
                    continue
                if clip.timeline_start - epsilon <= self._current_time < clip.timeline_end + epsilon:
                    clips.append(clip)
        return clips

    def _draw_text_clip_overlay(
        self,
        painter: QPainter,
        clip: TextClip,
        project_rect: QRectF,
        scale_factor: float,
    ) -> None:
        project = self._project_controller.active_project()
        if project is None:
            return

        font_size = max(1, int(round(float(clip.font_size) * scale_factor)))
        font = QFont(clip.font_family or "Arial", font_size)
        font.setBold(bool(clip.bold))
        font.setItalic(bool(clip.italic))
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(font)
        painter.setOpacity(max(0.0, min(1.0, float(getattr(clip, "opacity", 1.0)))))

        metrics = QFontMetricsF(font)
        raw_text = clip.content or "Text"
        lines = raw_text.split("\n")
        line_height = metrics.height()
        total_height = max(line_height, line_height * len(lines))
        line_widths = [metrics.horizontalAdvance(line) for line in lines]
        block_width = max(line_widths) if line_widths else 0.0

        anchor_x = project_rect.left() + float(clip.position_x) * project_rect.width()
        anchor_y = project_rect.top() + float(clip.position_y) * project_rect.height()
        alignment = (clip.alignment or "center").lower()
        if alignment == "left":
            block_left = anchor_x
        elif alignment == "right":
            block_left = anchor_x - block_width
        else:
            block_left = anchor_x - block_width / 2.0
        block_top = anchor_y - total_height / 2.0

        if clip.background_opacity > 0.0 and clip.background_color:
            pad_x = max(4.0, line_height * 0.25)
            pad_y = max(4.0, line_height * 0.15)
            bg_color = QColor(clip.background_color or "#000000")
            bg_color.setAlphaF(max(0.0, min(1.0, float(clip.background_opacity))))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg_color)
            painter.drawRoundedRect(
                QRectF(
                    block_left - pad_x,
                    block_top - pad_y,
                    block_width + 2 * pad_x,
                    total_height + 2 * pad_y,
                ),
                pad_y,
                pad_y,
            )

        fill_color = QColor(clip.color or "#ffffff")
        outline_color = QColor(clip.outline_color or "#000000")
        shadow_color = QColor(clip.shadow_color or "#000000")
        outline_width = max(0.0, float(clip.outline_width) * scale_factor)
        shadow_offset_x = float(clip.shadow_offset_x) * scale_factor
        shadow_offset_y = float(clip.shadow_offset_y) * scale_factor
        has_shadow = abs(shadow_offset_x) > 0.0 or abs(shadow_offset_y) > 0.0
        ascent = metrics.ascent()

        for line_index, line in enumerate(lines):
            line_width = line_widths[line_index]
            if alignment == "left":
                line_x = block_left
            elif alignment == "right":
                line_x = block_left + (block_width - line_width)
            else:
                line_x = block_left + (block_width - line_width) / 2.0
            line_y = block_top + ascent + line_index * line_height

            path = QPainterPath()
            path.addText(QPointF(line_x, line_y), font, line)

            if has_shadow:
                shadow_path = QPainterPath(path)
                shadow_path.translate(shadow_offset_x, shadow_offset_y)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(shadow_color)
                painter.drawPath(shadow_path)

            if outline_width > 0.0:
                pen = QPen(outline_color, outline_width * 2.0)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(path)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill_color)
            painter.drawPath(path)

        painter.restore()

    def _project_rect(self) -> QRectF:
        project = self._project_controller.active_project()
        if project is None or project.width <= 0 or project.height <= 0:
            return QRectF()
        margin = 16.0
        available = QRectF(
            margin,
            margin,
            max(1.0, self.width() - margin * 2.0),
            max(1.0, self.height() - margin * 2.0),
        )
        aspect = float(project.width) / float(project.height)
        draw_width = available.width()
        draw_height = draw_width / aspect
        if draw_height > available.height():
            draw_height = available.height()
            draw_width = draw_height * aspect
        x = available.left() + (available.width() - draw_width) * 0.5
        y = available.top() + (available.height() - draw_height) * 0.5
        return QRectF(x, y, draw_width, draw_height)

    def _selected_transform_clip(self) -> BaseClip | None:
        clip_id = self._selection_controller.selected_clip_id()
        if not clip_id:
            return None
        clip = self._clip_by_id(clip_id)
        if clip is None:
            return None
        if not isinstance(clip, (VideoClip, ImageClip, TextClip)):
            return None
        if not hasattr(clip, "position_x") or not hasattr(clip, "position_y"):
            return None
        return clip

    def _currently_rendered_clip(self) -> BaseClip | None:
        project = self._project_controller.active_project()
        if project is None:
            return None
        current_time = float(self._current_time)
        for track in reversed(project.timeline.tracks):
            if track.is_hidden or track.is_muted:
                continue
            for clip in reversed(track.sorted_clips()):
                if clip.is_muted:
                    continue
                if not isinstance(clip, (VideoClip, ImageClip, TextClip)):
                    continue
                if clip.timeline_start <= current_time < (clip.timeline_start + clip.duration):
                    return clip
        return None

    def _clip_by_id(self, clip_id: str) -> BaseClip | None:
        project = self._project_controller.active_project()
        if project is None:
            return None
        for track in project.timeline.tracks:
            for clip in track.clips:
                if clip.clip_id == clip_id:
                    return clip
        return None

    def _overlay_geometry(
        self,
        clip: BaseClip,
        project_rect: QRectF | None = None,
    ) -> tuple[QPointF, dict[str, QPointF], dict[str, QPointF], QPointF] | None:
        target_rect = project_rect or self._project_rect()
        if target_rect.width() <= 1.0 or target_rect.height() <= 1.0:
            return None
        position_x = float(getattr(clip, "position_x", 0.5))
        position_y = float(getattr(clip, "position_y", 0.5))
        scale = max(0.05, min(8.0, float(getattr(clip, "scale", 1.0))))
        rotation = float(getattr(clip, "rotation", 0.0))

        center = QPointF(
            target_rect.left() + position_x * target_rect.width(),
            target_rect.top() + position_y * target_rect.height(),
        )
        base_factor = 0.38 if isinstance(clip, TextClip) else 0.52
        width = max(34.0, target_rect.width() * base_factor * scale)
        height = max(24.0, target_rect.height() * base_factor * scale)
        raw = QRectF(center.x() - width / 2.0, center.y() - height / 2.0, width, height)

        transform = QTransform()
        transform.translate(center.x(), center.y())
        transform.rotate(rotation)
        transform.translate(-center.x(), -center.y())

        corners = {
            "tl": transform.map(QPointF(raw.left(), raw.top())),
            "tr": transform.map(QPointF(raw.right(), raw.top())),
            "br": transform.map(QPointF(raw.right(), raw.bottom())),
            "bl": transform.map(QPointF(raw.left(), raw.bottom())),
        }
        top_center = transform.map(QPointF(raw.center().x(), raw.top()))
        vec_x = top_center.x() - center.x()
        vec_y = top_center.y() - center.y()
        length = math.hypot(vec_x, vec_y) or 1.0
        rot = QPointF(
            top_center.x() + (vec_x / length) * _ROTATION_HANDLE_OFFSET,
            top_center.y() + (vec_y / length) * _ROTATION_HANDLE_OFFSET,
        )
        handles = {
            "tl": corners["tl"],
            "tr": corners["tr"],
            "bl": corners["bl"],
            "br": corners["br"],
            "rot": rot,
        }
        return center, corners, handles, top_center

    @staticmethod
    def _overlay_path(corners: dict[str, QPointF]):
        from PySide6.QtGui import QPainterPath

        path = QPainterPath()
        path.moveTo(corners["tl"])
        path.lineTo(corners["tr"])
        path.lineTo(corners["br"])
        path.lineTo(corners["bl"])
        path.closeSubpath()
        return path

    @staticmethod
    def _distance(a: QPointF, b: QPointF) -> float:
        return math.hypot(a.x() - b.x(), a.y() - b.y())

    @staticmethod
    def _hit_handle(handles: dict[str, QPointF], pointer: QPointF) -> str | None:
        for name, pos in handles.items():
            if math.hypot(pointer.x() - pos.x(), pointer.y() - pos.y()) <= (_HANDLE_RADIUS + 3.0):
                return name
        return None


class PreviewWidget(QWidget):
    def __init__(
        self,
        playback_controller: PlaybackController,
        project_controller: ProjectController,
        timeline_controller: TimelineController,
        selection_controller: SelectionController,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._playback_controller = playback_controller
        self._project_controller = project_controller
        self._timeline_controller = timeline_controller
        self._selection_controller = selection_controller

        self._current_time = self._playback_controller.current_time()
        self._current_preview_image: QImage | None = self._playback_controller.latest_preview_image()
        self._preview_message = self._playback_controller.latest_preview_message()
        self._is_playing = self._playback_controller.is_playing()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Canvas
        self.preview_canvas = _PreviewCanvas(
            project_controller=self._project_controller,
            timeline_controller=self._timeline_controller,
            selection_controller=self._selection_controller,
            parent=self,
        )
        layout.addWidget(self.preview_canvas, 1)

        # Bottom toolbar (3 columns)
        bottom_bar = QWidget(self)
        bottom_bar.setObjectName("previewBottomBar")
        bottom_bar.setFixedHeight(44)
        bottom_bar.setStyleSheet("#previewBottomBar { background: #1a1d23; border-top: 1px solid #2a2f37; }")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(8, 4, 8, 4)
        bottom_layout.setSpacing(8)

        self._time_label = PlaybackTimeLabel(self._playback_controller, bottom_bar)
        bottom_layout.addWidget(self._time_label, alignment=Qt.AlignmentFlag.AlignLeft)

        bottom_layout.addStretch(1)
        bottom_layout.addWidget(
            PlaybackPlayButton(self._playback_controller, bottom_bar),
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        bottom_layout.addStretch(1)

        right_group = QWidget(bottom_bar)
        right_group_layout = QHBoxLayout(right_group)
        right_group_layout.setContentsMargins(0, 0, 0, 0)
        right_group_layout.setSpacing(6)
        control_height = 30

        icon_tool_style = (
            "QToolButton { border: none; background: transparent; border-radius: 4px; padding: 0px; }"
            "QToolButton:hover { border: none; background: rgba(255,255,255,0.14); }"
            "QToolButton:pressed { border: none; background: rgba(255,255,255,0.20); }"
        )

        zoom_button = QToolButton(right_group)
        zoom_button.setIcon(build_icon("zoom-in"))
        zoom_button.setIconSize(QSize(20, 20))
        zoom_button.setToolTip(self.tr("Thu phóng"))
        zoom_button.setAutoRaise(True)
        zoom_button.setFixedSize(control_height, control_height)
        zoom_button.setStyleSheet(icon_tool_style)
        right_group_layout.addWidget(zoom_button)

        self._aspect_menu_button = QPushButton(self.tr("Tỉ lệ khung hình"), right_group)
        self._aspect_menu_button.setFlat(False)
        self._aspect_menu_button.setFixedHeight(control_height)
        self._aspect_menu_button.setStyleSheet(
            "QPushButton { border: 1px solid #384256; border-radius: 4px; padding: 0 10px; background: #222a36; color: #d6deea; }"
            "QPushButton:hover { background: #2a3443; border-color: #445069; }"
            "QPushButton::menu-indicator { image: none; width: 0px; }"
        )
        self._aspect_menu_button.setToolTip(self.tr("Đổi tỉ lệ khung hình dự án"))
        aspect_menu = QMenu(self._aspect_menu_button)
        for label, width, height in _ASPECT_PRESETS:
            action = aspect_menu.addAction(label)
            action.setData((width, height))
            action.triggered.connect(self._on_aspect_action_triggered)
        self._aspect_menu_button.setMenu(aspect_menu)
        right_group_layout.addWidget(self._aspect_menu_button)

        fullscreen_button = QToolButton(right_group)
        fullscreen_button.setIcon(build_icon("fit"))
        fullscreen_button.setIconSize(QSize(20, 20))
        fullscreen_button.setToolTip(self.tr("Toàn màn hình"))
        fullscreen_button.setAutoRaise(True)
        fullscreen_button.setFixedSize(control_height, control_height)
        fullscreen_button.setStyleSheet(icon_tool_style)
        right_group_layout.addWidget(fullscreen_button)

        bottom_layout.addWidget(right_group, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(bottom_bar)

        self._project_controller.project_changed.connect(self._refresh_total_duration)
        self._timeline_controller.timeline_changed.connect(self._refresh_total_duration)
        self._refresh_total_duration()

        self._playback_controller.current_time_changed.connect(self._on_current_time_changed)
        self._playback_controller.preview_frame_changed.connect(self._on_preview_frame_changed)
        self._playback_controller.preview_message_changed.connect(self._on_preview_message_changed)
        self._playback_controller.playback_state_changed.connect(self._on_playback_state_changed)
        self._selection_controller.selection_changed.connect(self.preview_canvas.update)
        self._project_controller.project_changed.connect(self.preview_canvas.update)
        self._timeline_controller.timeline_changed.connect(self.preview_canvas.update)

        self._render_preview()

    def _on_aspect_action_triggered(self) -> None:
        action = self.sender()
        if not isinstance(action, QAction):
            return
        data = action.data()
        if not isinstance(data, tuple) or len(data) != 2:
            return
        width, height = data
        if not isinstance(width, int) or not isinstance(height, int):
            return
        if width <= 0 or height <= 0:
            return
        if self._project_controller.set_project_resolution(width, height):
            self._playback_controller.refresh_preview_frame()
            self._aspect_menu_button.setText(self.tr("Tỉ lệ {ratio}").format(ratio=action.text()))

    def _refresh_total_duration(self) -> None:
        project = self._project_controller.active_project()
        total_seconds = project.timeline.total_duration() if project is not None else 0.0
        self._time_label.set_total_seconds(total_seconds)

    def _on_current_time_changed(self, current_time: float) -> None:
        self._current_time = current_time
        if self._current_preview_image is None:
            self._render_preview()

    def _on_preview_frame_changed(self, frame_image: object) -> None:
        if isinstance(frame_image, QImage) and not frame_image.isNull():
            self._current_preview_image = frame_image
        else:
            self._current_preview_image = None
        self._render_preview()

    def _on_preview_message_changed(self, message: str) -> None:
        self._preview_message = message
        if self._current_preview_image is None:
            self._render_preview()

    def _on_playback_state_changed(self, state: str) -> None:
        self._is_playing = state == "playing"
        self._render_preview()

    def _render_preview(self) -> None:
        self.preview_canvas.set_preview_state(
            self._current_preview_image,
            self._preview_message,
            self._current_time,
            self._is_playing,
        )
