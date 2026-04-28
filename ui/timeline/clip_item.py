from __future__ import annotations

from app.domain.clips.audio_clip import AudioClip
from app.domain.clips.base_clip import BaseClip
from app.domain.clips.video_clip import VideoClip
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
    QStyleOptionGraphicsItem,
    QWidget,
)


class ClipItem(QGraphicsRectItem):
    def __init__(
        self,
        clip: BaseClip,
        rect: QRectF,
        color_hex: str,
        thumbnails: list[QPixmap] | None = None,
        waveform_peaks: list[float] | None = None,
        is_selected: bool = False,
    ) -> None:
        super().__init__(QRectF(0.0, 0.0, rect.width(), rect.height()))
        self.clip = clip
        self._base_color_hex = color_hex
        self._thumbnail_sources: list[QPixmap] = [
            pixmap for pixmap in (thumbnails or []) if pixmap is not None and not pixmap.isNull()
        ]
        self._thumbnail_items: list[QGraphicsPixmapItem] = []
        self._waveform_peaks = [max(0.0, min(float(value), 1.0)) for value in (waveform_peaks or [])]
        self.setPos(rect.x(), rect.y())
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, True)

        self._label = QGraphicsSimpleTextItem(self._build_clip_label(), self)
        self._label.setBrush(QBrush(QColor("#f7fbff")))
        self._label.setPos(8.0, 4.0)
        self._label.setZValue(3)
        self._label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._refresh_thumbnail_pixmaps()
        self.set_selected_state(is_selected)

    def hit_test_edge(self, scene_x: float, handle_width: float = 8.0) -> str | None:
        local_x = scene_x - self.scenePos().x()
        clip_width = self.rect().width()
        if clip_width <= 0:
            return None
        if 0.0 <= local_x <= handle_width:
            return "left"
        if clip_width - handle_width <= local_x <= clip_width:
            return "right"
        return None

    def hit_test_fade_handle(self, scene_x: float, scene_y: float, radius: float = 7.0) -> str | None:
        local_x = scene_x - self.scenePos().x()
        local_y = scene_y - self.scenePos().y()
        fade_in_center, fade_out_center = self._fade_handle_centers()

        if (local_x - fade_in_center.x()) ** 2 + (local_y - fade_in_center.y()) ** 2 <= radius**2:
            return "fade_in"
        if (local_x - fade_out_center.x()) ** 2 + (local_y - fade_out_center.y()) ** 2 <= radius**2:
            return "fade_out"
        return None

    def set_thumbnails(self, thumbnails: list[QPixmap]) -> None:
        """Replace the filmstrip pixmaps and re-tile (used by the async loader)."""

        self._thumbnail_sources = [
            pixmap for pixmap in thumbnails if pixmap is not None and not pixmap.isNull()
        ]
        self._refresh_thumbnail_pixmaps()
        self.update()

    def set_waveform_peaks(self, peaks: list[float]) -> None:
        """Replace the waveform peaks (used by the async waveform loader)."""

        self._waveform_peaks = [max(0.0, min(float(value), 1.0)) for value in (peaks or [])]
        self.update()

    def set_display_geometry(self, scene_x: float, width: float) -> None:
        clamped_width = max(1.0, width)
        self.setPos(scene_x, self.scenePos().y())
        self.setRect(QRectF(0.0, 0.0, clamped_width, self.rect().height()))
        self._refresh_thumbnail_pixmaps()
        self.update()

    def set_selected_state(self, is_selected: bool) -> None:
        if is_selected:
            self.setPen(QPen(QColor("#ff5a36"), 2))
            self.setBrush(QBrush(QColor(self._base_color_hex).lighter(108)))
            self.setZValue(12)
            return

        self.setPen(QPen(QColor("#1f2933"), 1))
        self.setBrush(QBrush(QColor(self._base_color_hex)))
        self.setZValue(10)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        super().paint(painter, option, widget)

        self._draw_waveform(painter)
        self._draw_fade_regions(painter)
        self._draw_badges(painter)
        self._draw_fade_handles(painter)
        self._draw_keyframe_markers(painter)

    def _refresh_thumbnail_pixmaps(self) -> None:
        for item in self._thumbnail_items:
            item.setParentItem(None)
        self._thumbnail_items.clear()

        if not self._thumbnail_sources:
            return

        total_width = max(1.0, self.rect().width())
        tile_height = max(1, int(self.rect().height()))
        x_cursor = 0.0
        source_index = 0
        max_tiles = 320

        while x_cursor < total_width and max_tiles > 0:
            source = self._thumbnail_sources[source_index % len(self._thumbnail_sources)]
            source_index += 1
            max_tiles -= 1
            scaled = source.scaledToHeight(tile_height, Qt.TransformationMode.SmoothTransformation)
            if scaled.isNull():
                continue

            thumbnail_item = QGraphicsPixmapItem(self)
            thumbnail_item.setOpacity(0.9)
            thumbnail_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            thumbnail_item.setZValue(1)
            y_offset = max(0, (tile_height - scaled.height()) // 2)
            thumbnail_item.setPixmap(scaled)
            thumbnail_item.setPos(x_cursor, float(y_offset))
            self._thumbnail_items.append(thumbnail_item)
            x_cursor += float(scaled.width())

    def _draw_waveform(self, painter: QPainter) -> None:
        if not self._waveform_peaks or not isinstance(self.clip, (AudioClip, VideoClip)):
            return

        rect = self.rect()
        width = rect.width()
        height = rect.height()
        if width < 8 or height < 12:
            return

        path = QPainterPath()
        baseline_y = height * 0.62
        amplitude = max(6.0, height * 0.22)
        count = len(self._waveform_peaks)
        if count <= 1:
            return

        for index, peak in enumerate(self._waveform_peaks):
            x = (index / (count - 1)) * width
            y = baseline_y - peak * amplitude
            if index == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor("#d8f4e8"), 1.1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.restore()

    def _draw_fade_regions(self, painter: QPainter) -> None:
        if self.clip.duration <= 1e-6:
            return

        width = self.rect().width()
        height = self.rect().height()
        fade_in_px = max(0.0, min(width, (self.clip.fade_in_seconds / self.clip.duration) * width))
        fade_out_px = max(0.0, min(width, (self.clip.fade_out_seconds / self.clip.duration) * width))
        if fade_in_px <= 0.5 and fade_out_px <= 0.5:
            return

        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 42))
        if fade_in_px > 0.5:
            fade_in_path = QPainterPath()
            fade_in_path.moveTo(0.0, 0.0)
            fade_in_path.lineTo(fade_in_px, 0.0)
            fade_in_path.lineTo(0.0, height)
            fade_in_path.closeSubpath()
            painter.drawPath(fade_in_path)

        if fade_out_px > 0.5:
            fade_out_path = QPainterPath()
            fade_out_path.moveTo(width - fade_out_px, 0.0)
            fade_out_path.lineTo(width, 0.0)
            fade_out_path.lineTo(width, height)
            fade_out_path.closeSubpath()
            painter.drawPath(fade_out_path)
        painter.restore()

    def _draw_fade_handles(self, painter: QPainter) -> None:
        fade_in_center, fade_out_center = self._fade_handle_centers()
        painter.save()
        painter.setPen(QPen(QColor("#101418"), 1))
        painter.setBrush(QBrush(QColor("#f4f7fb")))
        handle_radius = 4.5
        painter.drawEllipse(fade_in_center, handle_radius, handle_radius)
        painter.drawEllipse(fade_out_center, handle_radius, handle_radius)
        painter.restore()

    def _draw_badges(self, painter: QPainter) -> None:
        badges: list[str] = []
        if self.clip.is_muted:
            badges.append("MUTE")
        if isinstance(self.clip, VideoClip) and self.clip.is_reversed:
            badges.append("REV")
        if not badges:
            return

        painter.save()
        x = self.rect().width() - 8.0
        y = self.rect().height() - 6.0
        for badge in reversed(badges):
            width = 34.0 if len(badge) <= 4 else 42.0
            x -= width
            badge_rect = QRectF(x, y - 14.0, width - 4.0, 12.0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#ffb366" if badge == "MUTE" else "#c6d8ff"))
            painter.drawRoundedRect(badge_rect, 3.0, 3.0)
            painter.setPen(QColor("#162029"))
            painter.drawText(
                badge_rect,
                Qt.AlignmentFlag.AlignCenter,
                badge,
            )
            x -= 4.0
        painter.restore()

    def _draw_keyframe_markers(self, painter: QPainter) -> None:
        clip_duration = max(1e-9, float(self.clip.duration))
        width = self.rect().width()
        if width < 16.0:
            return

        keyframe_times: set[float] = set()
        for attr_name in (
            "opacity_keyframes",
            "position_x_keyframes",
            "position_y_keyframes",
            "scale_keyframes",
            "rotation_keyframes",
            "gain_db_keyframes",
        ):
            keyframes = getattr(self.clip, attr_name, None)
            if not isinstance(keyframes, list):
                continue
            for keyframe in keyframes:
                time_seconds = float(getattr(keyframe, "time_seconds", -1.0))
                if 0.0 <= time_seconds <= clip_duration:
                    keyframe_times.add(round(time_seconds, 4))

        if not keyframe_times:
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QBrush(QColor("#00bcd4")))
        painter.setPen(QPen(QColor("#101418"), 1))
        half = 4.0
        y = 4.0 + half
        for time_seconds in sorted(keyframe_times):
            x = (time_seconds / clip_duration) * width
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(x, y - half),
                        QPointF(x + half, y),
                        QPointF(x, y + half),
                        QPointF(x - half, y),
                    ]
                )
            )
        painter.restore()

    def _fade_handle_centers(self) -> tuple[QPointF, QPointF]:
        width = max(1.0, self.rect().width())
        if self.clip.duration <= 1e-9:
            return QPointF(6.0, 8.0), QPointF(max(6.0, width - 6.0), 8.0)

        fade_in_px = max(0.0, min(width, (self.clip.fade_in_seconds / self.clip.duration) * width))
        fade_out_px = max(0.0, min(width, (self.clip.fade_out_seconds / self.clip.duration) * width))
        left_x = min(max(6.0, fade_in_px), max(6.0, width - 6.0))
        right_x = max(6.0, min(width - 6.0, width - fade_out_px))
        return QPointF(left_x, 8.0), QPointF(right_x, 8.0)

    def _build_clip_label(self) -> str:
        prefix = "C"
        if isinstance(self.clip, VideoClip):
            prefix = "V"
        elif isinstance(self.clip, AudioClip):
            prefix = "A"
        duration_text = self._format_duration(self.clip.duration)
        return f"{prefix} - {self.clip.name}  {duration_text}"

    @staticmethod
    def _format_duration(duration_seconds: float) -> str:
        safe = max(0.0, float(duration_seconds))
        minutes = int(safe // 60)
        seconds = safe - minutes * 60
        return f"{minutes}:{seconds:05.2f}"

