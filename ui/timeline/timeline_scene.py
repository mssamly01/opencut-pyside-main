from __future__ import annotations

import math
from dataclasses import dataclass

from app.domain.clips.audio_clip import AudioClip
from app.domain.clips.base_clip import BaseClip
from app.domain.clips.image_clip import ImageClip
from app.domain.clips.text_clip import TextClip
from app.domain.clips.video_clip import VideoClip
from app.domain.project import Project
from app.domain.track import Track
from app.services.thumbnail_service import ThumbnailService
from app.services.waveform_service import WaveformService
from app.ui.timeline.clip_item import ClipItem
from app.ui.timeline.playhead_item import PlayheadItem
from app.ui.timeline.ruler_widget import format_seconds_label
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsScene


@dataclass(slots=True, frozen=True)
class TrackLayout:
    track_id: str
    y: float
    height: float

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass(slots=True, frozen=True)
class _HeaderButtonSpec:
    track_id: str
    action: str
    label: str
    rect: QRectF
    active: bool


class TimelineScene(QGraphicsScene):
    def __init__(
        self,
        project: Project | None,
        project_path: str | None,
        thumbnail_service: ThumbnailService,
        waveform_service: WaveformService | None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.pixels_per_second = 90.0
        self.ruler_height = 24.0
        self.track_gap = 6.0
        self.left_gutter = 160.0
        self.right_padding = 80.0
        self.top_padding = 6.0
        self.bottom_padding = 12.0
        self._resize_handle_height = 4.0

        self._playhead_seconds = 0.0
        self._playhead_item: PlayheadItem | None = None
        self._snap_guide_item: QGraphicsLineItem | None = None
        self._project = project
        self._project_path = project_path
        self._thumbnail_service = thumbnail_service
        self._waveform_service = waveform_service
        self._selected_clip_id: str | None = None
        self._selected_clip_id_set: set[str] = set()
        self._last_min_width = 0.0
        self._last_min_height = 0.0
        self._ruler_label_specs: list[tuple[float, str]] = []
        self.track_layouts: list[TrackLayout] = []
        self._header_button_specs: list[_HeaderButtonSpec] = []
        self.setBackgroundBrush(QBrush(QColor("#1a1d23")))
        self.render_timeline()

    def set_project(
        self,
        project: Project | None,
        project_path: str | None,
        min_width: float | None = None,
        min_height: float | None = None,
    ) -> None:
        self._project = project
        self._project_path = project_path
        self.render_timeline(min_width=min_width, min_height=min_height)

    def set_selected_clip_id(self, clip_id: str | None) -> None:
        """Legacy single-select shim. Prefer set_selected_clip_ids()."""
        self.set_selected_clip_ids([clip_id] if clip_id else [])

    def set_selected_clip_ids(self, clip_ids: list[str]) -> None:
        new_primary = clip_ids[0] if clip_ids else None
        new_set = set(clip_ids)
        if new_primary == self._selected_clip_id and new_set == self._selected_clip_id_set:
            return
        self._selected_clip_id = new_primary
        self._selected_clip_id_set = new_set
        self._refresh_clip_selection_state()

    def set_playhead_seconds(self, seconds: float) -> None:
        clamped_seconds = max(0.0, seconds)
        if abs(clamped_seconds - self._playhead_seconds) < 1e-6:
            return

        self._playhead_seconds = clamped_seconds
        self._update_playhead(self.sceneRect().height())

    @property
    def playhead_seconds(self) -> float:
        return self._playhead_seconds

    def playhead_scene_x(self) -> float:
        if self._playhead_item is not None:
            return self._playhead_item.scene_x
        return self.left_gutter + self._playhead_seconds * self.pixels_per_second

    def hit_test_playhead(self, scene_x: float, scene_y: float) -> bool:
        if self._playhead_item is None:
            return False
        return self._playhead_item.hit_test(scene_x, scene_y)

    def render_timeline(
        self,
        min_width: float | None = None,
        min_height: float | None = None,
    ) -> None:
        if min_width is not None:
            self._last_min_width = min_width
        if min_height is not None:
            self._last_min_height = min_height

        self.clear()
        self._playhead_item = None
        self._snap_guide_item = None
        self._ruler_label_specs = []
        self.track_layouts = []
        self._header_button_specs = []

        tracks = self._project.timeline.tracks if self._project is not None else []
        total_duration = 12.0
        if self._project is not None:
            total_duration = max(total_duration, self._project.timeline.total_duration() + 2.0)

        current_y = self.ruler_height + self.top_padding
        for track in tracks:
            lane_height = max(28.0, min(float(track.height), 240.0))
            self.track_layouts.append(TrackLayout(track_id=track.track_id, y=current_y, height=lane_height))
            current_y += lane_height + self.track_gap

        calculated_width = self.left_gutter + (total_duration * self.pixels_per_second) + self.right_padding
        calculated_height = current_y - self.track_gap + self.bottom_padding
        scene_width = max(calculated_width, self._last_min_width)
        scene_height = max(calculated_height, self._last_min_height)
        self.setSceneRect(0, 0, scene_width, scene_height)

        ruler_duration = max(
            total_duration,
            max(0.0, (scene_width - self.left_gutter - self.right_padding) / self.pixels_per_second),
        )
        self._draw_ruler(ruler_duration)
        self._draw_tracks(tracks)
        self._update_playhead(scene_height)

    def track_layout_for_id(self, track_id: str) -> TrackLayout | None:
        for layout in self.track_layouts:
            if layout.track_id == track_id:
                return layout
        return None

    def header_hit_test(self, header_x: float, scene_y: float) -> tuple[str, str] | None:
        """Hit-test inside the sticky left header strip.

        `header_x` is viewport-relative: 0..left_gutter.
        """
        if header_x < 0.0 or header_x > self.left_gutter:
            return None

        for layout in self.track_layouts:
            if layout.y <= scene_y <= layout.bottom:
                if layout.bottom - self._resize_handle_height <= scene_y <= layout.bottom:
                    return layout.track_id, "resize"

                for button_spec in self._header_button_specs:
                    if button_spec.track_id != layout.track_id:
                        continue
                    if button_spec.rect.contains(header_x, scene_y):
                        return layout.track_id, button_spec.action
                return layout.track_id, "name"
        return None

    def track_id_at_scene_y(self, scene_y: float) -> str | None:
        for layout in self.track_layouts:
            if layout.y <= scene_y <= layout.bottom:
                return layout.track_id
        return None

    def _draw_ruler(self, duration_seconds: float) -> None:
        ruler_rect = QRectF(0.0, 0.0, self.sceneRect().width(), self.ruler_height)
        border_pen = QPen(QColor("#414c58"), 1)
        border_pen.setCosmetic(True)

        ruler_item = self.addRect(
            ruler_rect,
            border_pen,
            QBrush(QColor("#242933")),
        )
        ruler_item.setZValue(-10)
        ruler_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

        label_interval, tick_interval = self._get_ruler_intervals(self.pixels_per_second)
        current_tick = 0.0
        while current_tick <= duration_seconds + 1e-6:
            x = self.left_gutter + current_tick * self.pixels_per_second
            is_label_tick = False
            if label_interval > 0:
                remainder = current_tick % label_interval
                if remainder < 1e-6 or remainder > label_interval - 1e-6:
                    is_label_tick = True

            tick_height = 13 if is_label_tick else 8
            tick_item = self.addLine(x, self.ruler_height - tick_height, x, self.ruler_height, QPen(QColor("#7a8794"), 1))
            tick_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

            if is_label_tick:
                self._ruler_label_specs.append((x + 4, format_seconds_label(current_tick)))
            current_tick += tick_interval

    @staticmethod
    def _get_ruler_intervals(pps: float) -> tuple[float, float]:
        possible_intervals = [0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0, 300.0, 600.0]
        target_dist = 95.0
        label_interval = 1.0
        for interval in possible_intervals:
            if interval * pps >= target_dist:
                label_interval = interval
                break
        else:
            label_interval = possible_intervals[-1]
        tick_interval = label_interval / 2 if label_interval <= 0.5 else label_interval / 5
        return label_interval, tick_interval

    def _draw_tracks(self, tracks: list[Track]) -> None:
        for track in tracks:
            layout = self.track_layout_for_id(track.track_id)
            if layout is None:
                continue
            self._draw_track_background(track, layout)
            if not track.is_hidden:
                self._draw_track_clips(track, layout)

    def _draw_track_background(self, track: Track, layout: TrackLayout) -> None:
        border_pen = QPen(QColor("#414c58"), 1)
        border_pen.setCosmetic(True)

        lane_color = QColor("#1f2430")
        if track.is_hidden:
            lane_color = QColor("#1b202a")
        lane_rect = QRectF(
            self.left_gutter,
            layout.y,
            self.sceneRect().width() - self.left_gutter,
            layout.height,
        )
        lane_item = self.addRect(lane_rect, border_pen, QBrush(lane_color))
        lane_item.setZValue(-10)
        lane_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

        button_size = 18.0
        button_gap = 5.0
        start_x = self.left_gutter - 10.0 - button_size
        button_top = layout.y + 7.0
        button_defs = [
            ("hidden", "H", track.is_hidden),
            ("lock", "L", track.is_locked),
            ("mute", "M", track.is_muted),
        ]
        for index, (action, label, active) in enumerate(button_defs):
            button_rect = QRectF(start_x - index * (button_size + button_gap), button_top, button_size, button_size)
            self._header_button_specs.append(
                _HeaderButtonSpec(
                    track_id=track.track_id,
                    action=action,
                    label=label,
                    rect=button_rect,
                    active=active,
                )
            )

    def _draw_track_clips(self, track: Track, layout: TrackLayout) -> None:
        clip_y = layout.y + 5.0
        clip_height = max(12.0, layout.height - 10.0)
        filmstrip_max_tiles = 256

        for clip in track.sorted_clips():
            clip_x = self.left_gutter + clip.timeline_start * self.pixels_per_second
            clip_width = max(clip.duration * self.pixels_per_second, 16.0)
            rect = QRectF(clip_x, clip_y, clip_width, clip_height)

            thumbnails: list[QPixmap] = []
            if self._project is not None and isinstance(clip, VideoClip):
                aspect_ratio_hint = 16.0 / 9.0
                probe_bytes = self._thumbnail_service.get_thumbnail_bytes(
                    project=self._project,
                    clip=clip,
                    project_path=self._project_path,
                )
                if probe_bytes:
                    probe_pixmap = QPixmap()
                    if probe_pixmap.loadFromData(probe_bytes) and probe_pixmap.height() > 0:
                        aspect_ratio_hint = max(0.25, probe_pixmap.width() / probe_pixmap.height())

                estimated_tile_width = max(8.0, clip_height * aspect_ratio_hint)
                tile_count = max(
                    1,
                    min(filmstrip_max_tiles, int(math.ceil(clip_width / estimated_tile_width))),
                )
                frame_payloads = self._thumbnail_service.get_filmstrip_bytes(
                    project=self._project,
                    clip=clip,
                    project_path=self._project_path,
                    frame_count=tile_count,
                )
                for frame_payload in frame_payloads:
                    pixmap = QPixmap()
                    if pixmap.loadFromData(frame_payload):
                        thumbnails.append(pixmap)
            elif self._project is not None and isinstance(clip, ImageClip):
                thumbnail_bytes = self._thumbnail_service.get_thumbnail_bytes(
                    project=self._project,
                    clip=clip,
                    project_path=self._project_path,
                )
                if thumbnail_bytes:
                    pixmap = QPixmap()
                    if pixmap.loadFromData(thumbnail_bytes):
                        thumbnails.append(pixmap)

            peaks: list[float] = []
            if self._project is not None and self._waveform_service is not None and isinstance(clip, (AudioClip, VideoClip)):
                peaks = self._waveform_service.get_peaks(
                    project=self._project,
                    clip=clip,
                    project_path=self._project_path,
                )

            self.addItem(
                ClipItem(
                    clip=clip,
                    rect=rect,
                    color_hex=self._clip_color(clip),
                    thumbnails=thumbnails,
                    waveform_peaks=peaks,
                    is_selected=(clip.clip_id in self._selected_clip_id_set),
                )
            )

    def _refresh_clip_selection_state(self) -> None:
        for item in self.items():
            if isinstance(item, ClipItem):
                item.set_selected_state(item.clip.clip_id in self._selected_clip_id_set)

    def _update_playhead(self, scene_height: float) -> None:
        if self._playhead_item is not None:
            self.removeItem(self._playhead_item)
            self._playhead_item = None

        playhead_x = self.left_gutter + self._playhead_seconds * self.pixels_per_second
        playhead_bounds = QRectF(playhead_x, self.ruler_height, 0.0, scene_height - self.ruler_height)
        self._playhead_item = PlayheadItem(playhead_x, playhead_bounds)
        self.addItem(self._playhead_item)

    @staticmethod
    def _clip_color(clip: BaseClip) -> str:
        if isinstance(clip, VideoClip):
            return "#3f6bb8"
        if isinstance(clip, ImageClip):
            return "#a85fb8"
        if isinstance(clip, TextClip):
            return "#c48a38"
        if isinstance(clip, AudioClip):
            return "#3a9b6f"
        return "#6f8192"

    def show_snap_guide(self, scene_x: float) -> None:
        self.hide_snap_guide()

        pen = QPen(QColor("#ff4d4d"), 1, Qt.PenStyle.DashLine)
        scene_height = self.sceneRect().height()
        self._snap_guide_item = self.addLine(scene_x, self.ruler_height, scene_x, scene_height, pen)
        self._snap_guide_item.setZValue(100)
        self._snap_guide_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def hide_snap_guide(self) -> None:
        if self._snap_guide_item:
            try:
                self.removeItem(self._snap_guide_item)
            except RuntimeError:
                pass
            self._snap_guide_item = None

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawForeground(painter, rect)

        painter.save()

        # Ruler labels scroll with timeline lane.
        painter.setPen(QColor("#b9c2cc"))
        for x_position, label_text in self._ruler_label_specs:
            painter.drawText(
                QRectF(x_position, 0.0, 64.0, self.ruler_height),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                label_text,
            )

        # Sticky header is rendered at the left of visible rect.
        sticky_left = rect.left()
        scene_bottom = self.sceneRect().height()
        header_bg_rect = QRectF(sticky_left, 0.0, self.left_gutter, scene_bottom)
        painter.fillRect(header_bg_rect, QColor("#2d3542"))
        painter.setPen(QPen(QColor("#414c58"), 1))
        separator_x = sticky_left + self.left_gutter
        painter.drawLine(QPointF(separator_x, 0.0), QPointF(separator_x, scene_bottom))

        painter.setPen(QColor("#7a8794"))
        painter.drawText(
            QRectF(sticky_left + 12.0, 0.0, self.left_gutter - 20.0, self.ruler_height),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "TIMELINE",
        )

        for layout in self.track_layouts:
            track = self._project_track(layout.track_id)
            if track is None:
                continue

            title_rect = QRectF(
                sticky_left + 12.0,
                layout.y + 8.0,
                self.left_gutter - 92.0,
                max(12.0, layout.height - 16.0),
            )
            painter.setPen(QColor("#e6edf3" if not track.is_hidden else "#7a8794"))
            painter.drawText(
                title_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                track.name,
            )

            handle_y = layout.bottom
            painter.setPen(QPen(QColor("#414c58"), 1))
            painter.drawLine(
                QPointF(sticky_left, handle_y),
                QPointF(sticky_left + self.left_gutter, handle_y),
            )

        for button_spec in self._header_button_specs:
            button_rect = QRectF(
                sticky_left + button_spec.rect.x(),
                button_spec.rect.y(),
                button_spec.rect.width(),
                button_spec.rect.height(),
            )
            painter.setPen(QColor("#5f7082"))
            fill = QColor("#2b313e")
            if button_spec.active:
                fill = QColor("#f6c453")
            painter.setBrush(fill)
            painter.drawRoundedRect(button_rect, 3.0, 3.0)
            painter.setPen(QColor("#0f141d" if button_spec.active else "#cdd4dc"))
            painter.drawText(button_rect, Qt.AlignmentFlag.AlignCenter, button_spec.label)
        painter.restore()

    def _project_track(self, track_id: str) -> Track | None:
        if self._project is None:
            return None
        for track in self._project.timeline.tracks:
            if track.track_id == track_id:
                return track
        return None
