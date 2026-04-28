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
from app.services.async_media_loader import AsyncFilmstripLoader
from app.services.thumbnail_service import ThumbnailService
from app.services.waveform_loader import WaveformLoader
from app.services.waveform_service import WaveformService
from app.ui.timeline.clip_item import ClipItem
from app.ui.timeline.playhead_item import PlayheadItem
from app.ui.timeline.ruler_widget import format_seconds_label
from app.ui.timeline.transition_item import TransitionItem
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
        self.main_adjacent_gap = 10.0
        self.main_edge_padding = 12.0
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
        self._decoration_items: list = []
        # Filmstrip pixmaps loaded by the async worker, keyed by a stable
        # (media_id + source range + frame_count) tuple. Survives ``self.clear()``
        # so re-renders (zoom, selection change, …) don't re-spawn ffmpeg.
        self._filmstrip_pixmap_cache: dict[str, list[QPixmap]] = {}
        self._clip_items_by_id: dict[str, ClipItem] = {}
        self._filmstrip_loader = AsyncFilmstripLoader(thumbnail_service, parent=self)
        self._filmstrip_loader.filmstrip_ready.connect(self._on_filmstrip_ready)
        # Async waveform loader: avoids blocking UI thread on cache-miss
        # ffmpeg audio extraction (200-2000 ms for cold media). Survives
        # ``self.clear()`` so re-renders don't re-spawn ffmpeg.
        self._waveform_loader: WaveformLoader | None = None
        self._pending_waveform_media_ids: set[str] = set()
        if waveform_service is not None:
            self._waveform_loader = WaveformLoader(waveform_service, parent=self)
            self._waveform_loader.peaks_loaded.connect(self._on_peaks_loaded)
        self.setBackgroundBrush(QBrush(QColor("#1a1a1a")))
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
        self._decoration_items = []
        # ``self.clear()`` deletes the previous ClipItems, so async filmstrip
        # callbacks must not target stale instances. The pixmap cache itself
        # survives intentionally so re-rendered ClipItems get their thumbnails
        # back instantly without re-spawning ffmpeg.
        self._clip_items_by_id = {}

        tracks = self._project.timeline.tracks if self._project is not None else []
        total_duration = 12.0
        if self._project is not None:
            total_duration = max(total_duration, self._project.timeline.total_duration() + 2.0)

        lane_heights = [self._display_track_height(track) for track in tracks]
        inter_track_gaps = self._build_inter_track_gaps(tracks)
        top_main_padding, bottom_main_padding = self._main_edge_paddings(tracks)
        stack_height = (
            sum(lane_heights)
            + sum(inter_track_gaps)
            + top_main_padding
            + bottom_main_padding
        )

        calculated_width = self.left_gutter + (total_duration * self.pixels_per_second) + self.right_padding
        minimum_scene_height = self.ruler_height + self.top_padding + stack_height + self.bottom_padding
        scene_width = max(calculated_width, self._last_min_width)
        scene_height = max(minimum_scene_height, self._last_min_height)
        self.setSceneRect(0, 0, scene_width, scene_height)

        current_y = self.ruler_height + self.top_padding + top_main_padding
        if self._should_center_stack(tracks):
            available_height = scene_height - self.ruler_height - self.top_padding - self.bottom_padding
            if available_height > stack_height:
                current_y += (available_height - stack_height) / 2.0

        for index, (track, lane_height) in enumerate(zip(tracks, lane_heights, strict=False)):
            self.track_layouts.append(TrackLayout(track_id=track.track_id, y=current_y, height=lane_height))
            current_y += lane_height
            if index < len(inter_track_gaps):
                current_y += inter_track_gaps[index]

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
        border_pen = QPen(QColor("#333333"), 1)
        border_pen.setCosmetic(True)

        ruler_item = self.addRect(
            ruler_rect,
            border_pen,
            QBrush(QColor("#303030")),
        )
        ruler_item.setZValue(-10)
        ruler_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._decoration_items.append(ruler_item)

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
            self._decoration_items.append(tick_item)

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
        lane_color, border_color = self._track_palette(track)
        border_pen = QPen(border_color, 1)
        border_pen.setCosmetic(True)
        lane_rect = QRectF(
            self.left_gutter,
            layout.y,
            self.sceneRect().width() - self.left_gutter,
            layout.height,
        )
        lane_item = self.addRect(lane_rect, border_pen, QBrush(lane_color))
        lane_item.setZValue(-10)
        lane_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._decoration_items.append(lane_item)

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
        # Cap tile count well below the old 256 limit: even at max zoom the
        # filmstrip is tiled to fill the clip width, so 64 source frames is
        # enough visually and bounds the worker subprocess fan-out.
        filmstrip_max_tiles = 64
        clip_items_by_id: dict[str, ClipItem] = {}

        for clip in track.sorted_clips():
            clip_x = self.left_gutter + clip.timeline_start * self.pixels_per_second
            clip_width = max(clip.duration * self.pixels_per_second, 16.0)
            rect = QRectF(clip_x, clip_y, clip_width, clip_height)

            thumbnails: list[QPixmap] = []
            if self._project is not None and isinstance(clip, VideoClip):
                aspect_ratio_hint = self._video_clip_aspect_ratio(clip)
                estimated_tile_width = max(8.0, clip_height * aspect_ratio_hint)
                tile_count = max(
                    1,
                    min(filmstrip_max_tiles, int(math.ceil(clip_width / estimated_tile_width))),
                )
                cache_key = self._filmstrip_cache_key(clip, tile_count)
                cached = self._filmstrip_pixmap_cache.get(cache_key)
                if cached is not None:
                    thumbnails = list(cached)
                else:
                    self._filmstrip_loader.request(
                        cache_key=cache_key,
                        clip_id=clip.clip_id,
                        project=self._project,
                        clip=clip,
                        project_path=self._project_path,
                        frame_count=tile_count,
                    )
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
                peaks = self._cached_or_async_peaks(clip)

            clip_item = ClipItem(
                clip=clip,
                rect=rect,
                color_hex=self._clip_color(clip),
                thumbnails=thumbnails,
                waveform_peaks=peaks,
                is_selected=(clip.clip_id in self._selected_clip_id_set),
            )
            self.addItem(clip_item)
            clip_items_by_id[clip.clip_id] = clip_item
            self._clip_items_by_id[clip.clip_id] = clip_item

        for transition in track.transitions:
            from_item = clip_items_by_id.get(transition.from_clip_id)
            to_item = clip_items_by_id.get(transition.to_clip_id)
            if from_item is None or to_item is None:
                continue

            overlap_width = float(transition.duration_seconds) * self.pixels_per_second
            if overlap_width <= 1.0:
                continue

            rect = QRectF(
                from_item.scenePos().x() + from_item.rect().width() - overlap_width / 2.0,
                from_item.scenePos().y(),
                overlap_width,
                from_item.rect().height(),
            )
            transition_item = TransitionItem(transition, rect)
            transition_item.setZValue(15)
            transition_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.addItem(transition_item)

    def _video_clip_aspect_ratio(self, clip: VideoClip) -> float:
        """Aspect-ratio hint without spawning a synchronous ffmpeg probe.

        Falls back to 16:9 if ffprobe didn't fill in the dimensions during
        media import.
        """

        if self._project is None:
            return 16.0 / 9.0
        for media_asset in self._project.media_items:
            if media_asset.media_id != clip.media_id:
                continue
            if media_asset.width and media_asset.height and media_asset.height > 0:
                return max(0.25, media_asset.width / media_asset.height)
            break
        return 16.0 / 9.0

    @staticmethod
    def _filmstrip_cache_key(clip: VideoClip, frame_count: int) -> str:
        source_end = clip.source_end if clip.source_end is not None else -1.0
        return f"{clip.media_id}|{clip.source_start:.4f}|{source_end:.4f}|{frame_count}"

    def _cached_or_async_peaks(self, clip: BaseClip) -> list[float]:
        """Return cached waveform peaks; queue async extraction on cache miss."""

        if self._project is None or self._waveform_service is None or clip.media_id is None:
            return []
        media_asset = next(
            (asset for asset in self._project.media_items if asset.media_id == clip.media_id),
            None,
        )
        if media_asset is None:
            return []
        cached = self._waveform_service.peek_cached_peaks(media_asset, self._project_path)
        if cached:
            return cached
        if self._waveform_loader is not None and media_asset.media_id not in self._pending_waveform_media_ids:
            self._pending_waveform_media_ids.add(media_asset.media_id)
            self._waveform_loader.request_peaks(media_asset, self._project_path)
        return []

    def _on_peaks_loaded(self, media_id: str, peaks: list) -> None:
        self._pending_waveform_media_ids.discard(media_id)
        if not peaks:
            return
        clipped = [max(0.0, min(float(value), 1.0)) for value in peaks]
        for clip_item in self._clip_items_by_id.values():
            if clip_item.clip.media_id == media_id and isinstance(clip_item.clip, (AudioClip, VideoClip)):
                clip_item.set_waveform_peaks(clipped)

    def _on_filmstrip_ready(self, cache_key: str, clip_id: str, frames: list) -> None:
        pixmaps: list[QPixmap] = []
        for payload in frames:
            if not isinstance(payload, (bytes, bytearray)) or not payload:
                continue
            pixmap = QPixmap()
            if pixmap.loadFromData(bytes(payload)):
                pixmaps.append(pixmap)
        if not pixmaps:
            return
        self._filmstrip_pixmap_cache[cache_key] = pixmaps
        clip_item = self._clip_items_by_id.get(clip_id)
        if clip_item is not None:
            clip_item.set_thumbnails(pixmaps)

    def _refresh_clip_selection_state(self) -> None:
        for item in self.items():
            if isinstance(item, ClipItem):
                item.set_selected_state(item.clip.clip_id in self._selected_clip_id_set)

    def _update_playhead(self, scene_height: float) -> None:
        playhead_x = self.left_gutter + self._playhead_seconds * self.pixels_per_second
        if self._playhead_item is not None:
            self._playhead_item.set_scene_x(playhead_x)
            return

        playhead_bounds = QRectF(playhead_x, self.ruler_height, 0.0, scene_height - self.ruler_height)
        self._playhead_item = PlayheadItem(playhead_x, playhead_bounds)
        self.addItem(self._playhead_item)

    @staticmethod
    def _clip_color(clip: BaseClip) -> str:
        if isinstance(clip, VideoClip):
            return "#4a78d0"
        if isinstance(clip, ImageClip):
            return "#8f6ad4"
        if isinstance(clip, TextClip):
            return "#d39a45"
        if isinstance(clip, AudioClip):
            return "#45a47a"
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

        # Sticky header must follow the view's left edge. Using the repaint
        # rect directly can drift during partial updates and overpaint lanes.
        sticky_left = self._visible_scene_left(rect.left())
        scene_bottom = self.sceneRect().height()
        header_bg_rect = QRectF(sticky_left, 0.0, self.left_gutter, scene_bottom)
        painter.fillRect(header_bg_rect, QColor("#303030"))
        painter.setPen(QPen(QColor("#1a1a1a"), 1))
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
            painter.setPen(self._track_title_color(track))
            painter.drawText(
                title_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                track.name,
            )

            handle_y = layout.bottom
            _, handle_color = self._track_palette(track)
            painter.setPen(QPen(handle_color, 1))
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
                fill = QColor("#00bcd4")
            painter.setBrush(fill)
            painter.drawRoundedRect(button_rect, 3.0, 3.0)
            painter.setPen(QColor("#0f141d" if button_spec.active else "#cdd4dc"))
            painter.drawText(button_rect, Qt.AlignmentFlag.AlignCenter, button_spec.label)
        painter.restore()

    def _visible_scene_left(self, fallback_left: float) -> float:
        views = self.views()
        if not views:
            return fallback_left
        viewport_rect = views[0].viewport().rect()
        if viewport_rect.isNull():
            return fallback_left
        return views[0].mapToScene(viewport_rect).boundingRect().left()

    def _project_track(self, track_id: str) -> Track | None:
        if self._project is None:
            return None
        for track in self._project.timeline.tracks:
            if track.track_id == track_id:
                return track
        return None

    @staticmethod
    def _should_center_stack(tracks: list[Track]) -> bool:
        return len(tracks) == 1 and tracks[0].is_main

    def _build_inter_track_gaps(self, tracks: list[Track]) -> list[float]:
        if len(tracks) < 2:
            return []
        gaps: list[float] = []
        for upper, lower in zip(tracks, tracks[1:], strict=False):
            gap = self.track_gap
            if upper.is_main or lower.is_main:
                gap = max(gap, self.main_adjacent_gap)
            gaps.append(gap)
        return gaps

    def _main_edge_paddings(self, tracks: list[Track]) -> tuple[float, float]:
        if not tracks:
            return 0.0, 0.0
        top_padding = self.main_edge_padding if tracks[0].is_main else 0.0
        bottom_padding = self.main_edge_padding if tracks[-1].is_main else 0.0
        return top_padding, bottom_padding

    @staticmethod
    def _display_track_height(track: Track) -> float:
        base_height = max(28.0, min(float(track.height), 240.0))
        uses_default_height = abs(base_height - 58.0) < 1e-6
        normalized_type = track.track_type.lower()

        if normalized_type == "text" and uses_default_height:
            return 40.0

        if track.is_main and bool(track.clips):
            return max(base_height, 86.0) if not uses_default_height else 86.0

        return base_height

    @staticmethod
    def _track_palette(track: Track) -> tuple[QColor, QColor]:
        if track.is_hidden:
            return QColor("#1a1f27"), QColor("#38424f")

        normalized_type = track.track_type.lower()
        if track.is_main:
            return QColor("#2a2f3a"), QColor("#455a76")
        if normalized_type == "text":
            return QColor("#3a3126"), QColor("#6a5638")
        if normalized_type in {"audio", "mixed"}:
            return QColor("#243530"), QColor("#47695b")
        if normalized_type == "overlay":
            return QColor("#322b42"), QColor("#615884")
        return QColor("#2d333f"), QColor("#414c58")

    @staticmethod
    def _track_title_color(track: Track) -> QColor:
        if track.is_hidden:
            return QColor("#7a8794")

        normalized_type = track.track_type.lower()
        if track.is_main:
            return QColor("#d9e8ff")
        if normalized_type == "text":
            return QColor("#ffd9a3")
        if normalized_type in {"audio", "mixed"}:
            return QColor("#caf3df")
        if normalized_type == "overlay":
            return QColor("#dbcfff")
        return QColor("#e6edf3")
