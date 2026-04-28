from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.domain.clips.base_clip import BaseClip
from app.domain.clips.image_clip import ImageClip
from app.domain.clips.text_clip import TextClip
from app.domain.clips.video_clip import VideoClip
from app.domain.media_asset import MediaAsset
from app.domain.project import Project
from app.infrastructure.ffmpeg_gateway import FFmpegGateway
from app.infrastructure.persistent_ffmpeg_reader import PersistentFFmpegFramePool
from app.infrastructure.video_decoder import VideoDecoder
from app.services.export_service import ExportService
from app.services.keyframe_evaluator import clip_has_keyframes
from app.services.memory_guard import MemoryGuard


@dataclass(slots=True, frozen=True)
class PreviewFrameResult:
    frame_bytes: bytes | None
    message: str


class PlaybackService:
    _PREFETCH_WINDOW_SECONDS = 0.35
    _MIN_PREFETCH_FRAME_COUNT = 6
    _MAX_PREFETCH_FRAME_COUNT = 18
    _headless_qt_app: object | None = None

    def __init__(
        self,
        ffmpeg_gateway: FFmpegGateway | None = None,
        video_decoder: VideoDecoder | None = None,
        memory_guard: MemoryGuard | None = None,
        frame_pool: PersistentFFmpegFramePool | None = None,
    ) -> None:
        self._ffmpeg_gateway = ffmpeg_gateway or FFmpegGateway()
        if video_decoder is None:
            self._frame_pool = frame_pool or PersistentFFmpegFramePool(ffmpeg_gateway=self._ffmpeg_gateway)
            self._video_decoder = VideoDecoder(
                ffmpeg_gateway=self._ffmpeg_gateway,
                max_cache_entries=420,
                frame_pool=self._frame_pool,
            )
        else:
            self._frame_pool = frame_pool
            self._video_decoder = video_decoder
        self._memory_guard = memory_guard or MemoryGuard()
        self._image_bytes_cache: dict[str, bytes] = {}

    def get_preview_frame(
        self,
        project: Project | None,
        time_seconds: float,
        project_path: str | None = None,
    ) -> PreviewFrameResult:
        # Run before the cache lookup: if RAM is tight, drop oldest frames so
        # the next decode/prefetch doesn't push us further into pressure.
        self._memory_guard.maybe_shrink(self._video_decoder)

        if project is None:
            return PreviewFrameResult(frame_bytes=None, message="No project loaded")

        active_clip = self._find_active_visual_clip(project, time_seconds)
        if active_clip is None:
            return PreviewFrameResult(frame_bytes=None, message="No visual clip at current time")

        if isinstance(active_clip, TextClip):
            return self._render_text_clip(active_clip, project, current_time=time_seconds)

        media_asset = self._find_media_asset(project, active_clip.media_id)
        if media_asset is None:
            return PreviewFrameResult(frame_bytes=None, message="Missing media asset")

        project_root = self._project_root(project_path)
        media_path = self._resolve_media_path(media_asset.file_path, project_root)

        if isinstance(active_clip, ImageClip) or media_asset.media_type.lower() == "image":
            image_bytes = self._load_image_bytes(media_path)
            if image_bytes is None:
                return PreviewFrameResult(frame_bytes=None, message="Unable to load image")
            return PreviewFrameResult(frame_bytes=image_bytes, message=media_asset.name)

        source_time = self._clip_source_time(active_clip, time_seconds)
        source_time = self._clamp_source_time_to_media(source_time, media_asset)
        safe_fps = self._safe_fps(project.fps)
        frame_index = self._frame_index(source_time, safe_fps)
        normalized_media_path = str(media_path)
        # Per-clip color/LUT filter chain.  Re-uses the export-time builder
        # but passes ``time_in_clip`` so any color keyframes are evaluated and
        # baked at the current playhead — the per-frame ffmpeg invocation
        # gets a constant chain, and the cache key naturally varies with t.
        time_in_clip = max(0.0, float(time_seconds) - float(active_clip.timeline_start))
        extra_filters = ExportService._color_adjust_filters_for_clip(
            active_clip, time_in_clip=time_in_clip
        )
        # When the filter chain depends on time (any color keyframes), prefetched
        # neighbour frames would be baked with the *current* time's value and
        # never match future cache lookups — wasted work that also evicts useful
        # entries from the LRU.  Decode just the requested frame instead.
        prefetch_enabled = not self._has_animated_color(active_clip)
        frame_dimensions = self._frame_dimensions_for_asset(media_asset)
        cached_frame = self._video_decoder.get_frame(
            normalized_media_path, safe_fps, frame_index, extra_video_filters=extra_filters
        )
        if cached_frame is not None:
            return PreviewFrameResult(frame_bytes=cached_frame, message=media_asset.name)

        if prefetch_enabled:
            self._prefetch_window(
                media_path=normalized_media_path,
                fps=safe_fps,
                frame_index=frame_index,
                media_asset=media_asset,
                extra_video_filters=extra_filters,
                frame_dimensions=frame_dimensions,
            )
            cached_frame = self._video_decoder.get_frame(
                normalized_media_path, safe_fps, frame_index, extra_video_filters=extra_filters
            )
            if cached_frame is not None:
                return PreviewFrameResult(frame_bytes=cached_frame, message=media_asset.name)

        frame_bytes = self._decode_single_frame(
            media_path=normalized_media_path,
            fps=safe_fps,
            frame_index=frame_index,
            frame_dimensions=frame_dimensions,
            extra_video_filters=extra_filters,
        )
        if frame_bytes is None:
            return PreviewFrameResult(frame_bytes=None, message="Unable to decode video frame")

        self._video_decoder.put_frame(
            normalized_media_path, safe_fps, frame_index, frame_bytes, extra_video_filters=extra_filters
        )
        return PreviewFrameResult(frame_bytes=frame_bytes, message=media_asset.name)

    def _find_active_visual_clip(self, project: Project, time_seconds: float) -> BaseClip | None:
        epsilon = 1e-6
        for track in reversed(project.timeline.tracks):
            if track.is_hidden or track.is_muted:
                continue
            for clip in reversed(track.sorted_clips()):
                if not isinstance(clip, (VideoClip, ImageClip, TextClip)):
                    continue
                if clip.is_muted:
                    continue
                if clip.timeline_start - epsilon <= time_seconds < clip.timeline_end + epsilon:
                    return clip
        return None

    @staticmethod
    def _find_media_asset(project: Project, media_id: str | None) -> MediaAsset | None:
        if media_id is None:
            return None
        for media_asset in project.media_items:
            if media_asset.media_id == media_id:
                return media_asset
        return None

    @staticmethod
    def _has_animated_color(clip: BaseClip) -> bool:
        """True when any color channel has at least one keyframe.

        Time-varying color filters poison the prefetch window — a single
        ffmpeg call that bakes one playhead's value into many frames is
        purely wasted work because the cache token includes the filter hash.
        """
        for name in ("brightness", "contrast", "saturation", "hue"):
            if clip_has_keyframes(clip, name):
                return True
        return False

    @staticmethod
    def _clip_source_time(clip: BaseClip, time_seconds: float) -> float:
        local_offset = max(0.0, time_seconds - clip.timeline_start)
        source_time = clip.source_start + local_offset
        if clip.source_end is None:
            return source_time
        return max(clip.source_start, min(source_time, clip.source_end))

    @staticmethod
    def _clamp_source_time_to_media(source_time: float, media_asset: MediaAsset) -> float:
        if media_asset.duration_seconds is None:
            return max(0.0, source_time)

        media_duration = max(0.0, media_asset.duration_seconds)
        if media_duration <= 0.0:
            return 0.0

        safe_end = max(0.0, media_duration - 0.001)
        return max(0.0, min(source_time, safe_end))

    @staticmethod
    def _safe_fps(fps: float) -> float:
        return fps if fps > 0 else 30.0

    @staticmethod
    def _frame_index(time_seconds: float, fps: float) -> int:
        safe_fps = fps if fps > 0 else 30.0
        return int(max(0.0, time_seconds) * safe_fps)

    @staticmethod
    def _time_from_frame_index(frame_index: int, fps: float) -> float:
        safe_fps = fps if fps > 0 else 30.0
        safe_index = max(0, frame_index)
        return safe_index / safe_fps

    @staticmethod
    def _project_root(project_path: str | None) -> Path | None:
        if project_path is None or not project_path.strip():
            return None

        resolved_path = Path(project_path).expanduser().resolve()
        if resolved_path.is_dir():
            return resolved_path
        return resolved_path.parent

    @staticmethod
    def _resolve_media_path(file_path: str, project_root: Path | None) -> Path:
        raw_path = Path(file_path).expanduser()
        if raw_path.is_absolute():
            return raw_path.resolve()

        if project_root is not None:
            return (project_root / raw_path).resolve()

        return raw_path.resolve()

    def _load_image_bytes(self, file_path: Path) -> bytes | None:
        normalized_path = str(file_path.expanduser().resolve())
        cached = self._image_bytes_cache.get(normalized_path)
        if cached is not None:
            return cached

        try:
            image_bytes = Path(normalized_path).read_bytes()
        except OSError:
            return None

        if not image_bytes:
            return None

        self._image_bytes_cache[normalized_path] = image_bytes
        return image_bytes

    def _prefetch_window(
        self,
        media_path: str,
        fps: float,
        frame_index: int,
        media_asset: MediaAsset,
        extra_video_filters: list[str] | None = None,
        frame_dimensions: tuple[int, int] | None = None,
    ) -> None:
        frame_count = self._prefetch_frame_count_for_fps(fps)
        window_start = max(0, frame_index)
        if self._video_decoder.has_prefetched_until(
            media_path, fps, window_start, extra_video_filters=extra_video_filters
        ):
            return
        self._video_decoder.decode_window(
            media_path=media_path,
            fps=fps,
            start_frame_index=window_start,
            frame_count=frame_count,
            media_duration_seconds=media_asset.duration_seconds,
            extra_video_filters=extra_video_filters,
            frame_dimensions=frame_dimensions,
        )

    def _decode_single_frame(
        self,
        media_path: str,
        fps: float,
        frame_index: int,
        frame_dimensions: tuple[int, int] | None,
        extra_video_filters: list[str] | None,
    ) -> bytes | None:
        if self._frame_pool is not None and frame_dimensions is not None:
            width, height = frame_dimensions
            if width > 0 and height > 0:
                pool_frames = self._frame_pool.read_frames(
                    media_path=media_path,
                    fps=fps,
                    start_frame_index=frame_index,
                    frame_count=1,
                    width=int(width),
                    height=int(height),
                    extra_video_filters=extra_video_filters,
                )
                if pool_frames:
                    return pool_frames[0][1]

        quantized_source_time = self._time_from_frame_index(frame_index, fps)
        return self._ffmpeg_gateway.extract_frame_png(
            media_path, quantized_source_time, extra_video_filters=extra_video_filters
        )

    @staticmethod
    def _frame_dimensions_for_asset(media_asset: MediaAsset) -> tuple[int, int] | None:
        width = media_asset.width
        height = media_asset.height
        if width is None or height is None:
            return None
        if int(width) <= 0 or int(height) <= 0:
            return None
        return (int(width), int(height))

    @classmethod
    def _prefetch_frame_count_for_fps(cls, fps: float) -> int:
        safe_fps = fps if fps > 0 else 30.0
        dynamic_count = int(round(safe_fps * cls._PREFETCH_WINDOW_SECONDS))
        return max(cls._MIN_PREFETCH_FRAME_COUNT, min(cls._MAX_PREFETCH_FRAME_COUNT, dynamic_count))

    @classmethod
    def _ensure_qt_gui_application(cls) -> None:
        from PySide6.QtWidgets import QApplication

        if QApplication.instance() is not None:
            return
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls._headless_qt_app = QApplication([])

    @classmethod
    def _render_text_clip(
        cls,
        clip: TextClip,
        project: Project,
        current_time: float = 0.0,
    ) -> PreviewFrameResult:
        cls._ensure_qt_gui_application()
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
        from PySide6.QtGui import (
            QBrush,
            QColor,
            QFont,
            QFontMetricsF,
            QImage,
            QPainter,
            QPainterPath,
            QPen,
        )

        width = max(2, int(project.width))
        height = max(2, int(project.height))
        image = QImage(width, height, QImage.Format.Format_RGBA8888)
        image.fill(QColor(0, 0, 0, 0))

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        font = QFont(clip.font_family or "Arial", clip.font_size)
        font.setBold(bool(clip.bold))
        font.setItalic(bool(clip.italic))
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        painter.setFont(font)

        metrics = QFontMetricsF(font)
        raw_text = clip.content if clip.content else "Text"
        lines = raw_text.split("\n")
        line_height = metrics.height()
        total_height = max(line_height, line_height * len(lines))
        line_widths = [metrics.horizontalAdvance(line) for line in lines]
        block_width = max(line_widths) if line_widths else 0.0

        alignment = (clip.alignment or "center").lower()
        anchor_x = clip.position_x * width
        anchor_y = clip.position_y * height

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
            background_rect = QRectF(
                block_left - pad_x,
                block_top - pad_y,
                block_width + 2 * pad_x,
                total_height + 2 * pad_y,
            )
            bg_color = QColor(clip.background_color or "#000000")
            bg_color.setAlphaF(max(0.0, min(1.0, float(clip.background_opacity))))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(bg_color))
            painter.drawRoundedRect(background_rect, pad_y, pad_y)

        fill_color = QColor(clip.color or "#ffffff")
        highlight_color = QColor(clip.highlight_color or "#ffd166")
        outline_color = QColor(clip.outline_color or "#000000")
        shadow_color = QColor(clip.shadow_color or "#000000")
        outline_width = max(0.0, float(clip.outline_width))
        has_shadow = abs(clip.shadow_offset_x) > 0.0 or abs(clip.shadow_offset_y) > 0.0

        ascent = metrics.ascent()
        active_word_index: int | None = None
        if clip.word_timings:
            clip_local_time = float(current_time) - float(clip.timeline_start)
            for index, word_timing in enumerate(clip.word_timings):
                if float(word_timing.start_seconds) <= clip_local_time < float(word_timing.end_seconds):
                    active_word_index = index
                    break

        line_tokens_text: list[list[str]] = [line.split() for line in lines]
        total_text_tokens = sum(len(tokens) for tokens in line_tokens_text)
        use_per_word = (
            bool(clip.word_timings)
            and total_text_tokens == len(clip.word_timings)
            and total_text_tokens > 0
        )

        if use_per_word:
            space_width = metrics.horizontalAdvance(" ")
            global_word_index = 0
            for line_index, line_tokens in enumerate(line_tokens_text):
                if not line_tokens:
                    continue

                token_widths = [metrics.horizontalAdvance(token_text) for token_text in line_tokens]
                content_width = sum(token_widths) + max(0, len(line_tokens) - 1) * space_width

                if alignment == "left":
                    line_x = block_left
                elif alignment == "right":
                    line_x = block_left + (block_width - content_width)
                else:
                    line_x = block_left + (block_width - content_width) / 2.0
                line_y = block_top + ascent + line_index * line_height

                cursor_x = line_x
                for token_index, token_text in enumerate(line_tokens):
                    path = QPainterPath()
                    path.addText(QPointF(cursor_x, line_y), font, token_text)

                    if has_shadow:
                        shadow_path = QPainterPath(path)
                        shadow_path.translate(float(clip.shadow_offset_x), float(clip.shadow_offset_y))
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.setBrush(QBrush(shadow_color))
                        painter.drawPath(shadow_path)

                    if outline_width > 0.0:
                        pen = QPen(outline_color, outline_width * 2.0)
                        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                        painter.setPen(pen)
                        painter.setBrush(Qt.BrushStyle.NoBrush)
                        painter.drawPath(path)

                    is_active = active_word_index is not None and active_word_index == global_word_index
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QBrush(highlight_color if is_active else fill_color))
                    painter.drawPath(path)

                    cursor_x += token_widths[token_index]
                    if token_index + 1 < len(line_tokens):
                        cursor_x += space_width
                    global_word_index += 1
        else:
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
                    shadow_path.translate(float(clip.shadow_offset_x), float(clip.shadow_offset_y))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QBrush(shadow_color))
                    painter.drawPath(shadow_path)

                if outline_width > 0.0:
                    pen = QPen(outline_color, outline_width * 2.0)
                    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                    painter.setPen(pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawPath(path)

                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(fill_color))
                painter.drawPath(path)
        painter.end()

        encoded = QByteArray()
        buffer = QBuffer(encoded)
        if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
            return PreviewFrameResult(frame_bytes=None, message="Unable to encode text frame")
        try:
            if not image.save(buffer, "PNG"):
                return PreviewFrameResult(frame_bytes=None, message="Unable to encode text frame")
        finally:
            buffer.close()
        frame_bytes = bytes(encoded)

        return PreviewFrameResult(frame_bytes=frame_bytes, message=raw_text)
