from __future__ import annotations

import hashlib
from collections import OrderedDict
from dataclasses import dataclass

from app.infrastructure.ffmpeg_gateway import FFmpegGateway


@dataclass(slots=True, frozen=True)
class DecodedFrame:
    frame_index: int
    payload: bytes


def _filter_token(extra_video_filters: list[str] | None) -> str:
    """Stable, short token identifying a filter chain. Empty for no filters."""
    if not extra_video_filters:
        return ""
    joined = "|".join(extra_video_filters)
    return hashlib.sha1(joined.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


class VideoDecoder:
    """Cache-backed decoder facade for timeline preview frames."""

    def __init__(
        self,
        ffmpeg_gateway: FFmpegGateway | None = None,
        max_cache_entries: int = 360,
    ) -> None:
        self._ffmpeg_gateway = ffmpeg_gateway or FFmpegGateway()
        self._max_cache_entries = max(60, max_cache_entries)
        # Cache key: (media_path, fps_token, frame_index, filter_token).
        self._frame_cache: OrderedDict[tuple[str, int, int, str], bytes] = OrderedDict()
        # Prefetch tracking: max frame index reached per (media_path, fps_token, filter_token).
        self._prefetched_until: dict[tuple[str, int, str], int] = {}

    def get_frame(
        self,
        media_path: str,
        fps: float,
        frame_index: int,
        extra_video_filters: list[str] | None = None,
    ) -> bytes | None:
        key = self._cache_key(media_path, fps, frame_index, extra_video_filters)
        payload = self._frame_cache.get(key)
        if payload is None:
            return None
        self._frame_cache.move_to_end(key)
        return payload

    def has_frame(
        self,
        media_path: str,
        fps: float,
        frame_index: int,
        extra_video_filters: list[str] | None = None,
    ) -> bool:
        key = self._cache_key(media_path, fps, frame_index, extra_video_filters)
        return key in self._frame_cache

    def has_prefetched_until(
        self,
        media_path: str,
        fps: float,
        frame_index: int,
        extra_video_filters: list[str] | None = None,
    ) -> bool:
        token = self._media_fps_token(media_path, fps, extra_video_filters)
        max_index = self._prefetched_until.get(token)
        if max_index is None:
            return False
        return frame_index <= max_index

    def decode_window(
        self,
        media_path: str,
        fps: float,
        start_frame_index: int,
        frame_count: int,
        media_duration_seconds: float | None,
        extra_video_filters: list[str] | None = None,
    ) -> list[DecodedFrame]:
        safe_fps = fps if fps > 0 else 30.0
        safe_start = max(0, int(start_frame_index))
        safe_count = max(1, int(frame_count))

        max_frame_index = self._max_frame_index_for_duration(media_duration_seconds, safe_fps)
        start_time_seconds = safe_start / safe_fps
        sequence = self._ffmpeg_gateway.extract_frame_sequence_png(
            file_path=media_path,
            start_time_seconds=start_time_seconds,
            fps=safe_fps,
            frame_count=safe_count,
            extra_video_filters=extra_video_filters,
        )
        if not sequence:
            return []

        decoded_frames: list[DecodedFrame] = []
        for offset, payload in enumerate(sequence):
            frame_index = safe_start + offset
            if max_frame_index is not None and frame_index > max_frame_index:
                break
            decoded_frames.append(DecodedFrame(frame_index=frame_index, payload=payload))

        if not decoded_frames:
            return []

        highest_index = decoded_frames[-1].frame_index
        token = self._media_fps_token(media_path, safe_fps, extra_video_filters)
        current_max = self._prefetched_until.get(token, -1)
        if highest_index > current_max:
            self._prefetched_until[token] = highest_index

        for decoded in decoded_frames:
            key = self._cache_key(media_path, safe_fps, decoded.frame_index, extra_video_filters)
            if key in self._frame_cache:
                continue
            self._frame_cache[key] = decoded.payload
            self._frame_cache.move_to_end(key)

        while len(self._frame_cache) > self._max_cache_entries:
            self._frame_cache.popitem(last=False)

        return decoded_frames

    def cache_size(self) -> int:
        """Return the number of frames currently cached."""

        return len(self._frame_cache)

    def shrink_cache_to(self, target_count: int) -> int:
        """Evict oldest frames until at most ``target_count`` remain.

        Returns the number of entries evicted. Used by the memory guard to
        release RAM when the system is under pressure. The prefetch
        watermark is cleared on any eviction so the next preview request
        re-runs ``decode_window`` instead of trusting a watermark whose
        backing payloads we just dropped.
        """

        target = max(0, int(target_count))
        evicted = 0
        while len(self._frame_cache) > target:
            self._frame_cache.popitem(last=False)
            evicted += 1
        if evicted:
            self._prefetched_until.clear()
        return evicted

    def put_frame(
        self,
        media_path: str,
        fps: float,
        frame_index: int,
        payload: bytes,
        extra_video_filters: list[str] | None = None,
    ) -> None:
        key = self._cache_key(media_path, fps, frame_index, extra_video_filters)
        self._frame_cache[key] = payload
        self._frame_cache.move_to_end(key)
        token = self._media_fps_token(media_path, fps, extra_video_filters)
        current_max = self._prefetched_until.get(token, -1)
        if frame_index > current_max:
            self._prefetched_until[token] = frame_index
        while len(self._frame_cache) > self._max_cache_entries:
            self._frame_cache.popitem(last=False)

    @staticmethod
    def _cache_key(
        media_path: str,
        fps: float,
        frame_index: int,
        extra_video_filters: list[str] | None,
    ) -> tuple[str, int, int, str]:
        fps_token = int(round(max(1.0, fps) * 1000.0))
        return (media_path, fps_token, max(0, int(frame_index)), _filter_token(extra_video_filters))

    @staticmethod
    def _media_fps_token(
        media_path: str,
        fps: float,
        extra_video_filters: list[str] | None,
    ) -> tuple[str, int, str]:
        fps_token = int(round(max(1.0, fps) * 1000.0))
        return (media_path, fps_token, _filter_token(extra_video_filters))

    @staticmethod
    def _max_frame_index_for_duration(media_duration_seconds: float | None, fps: float) -> int | None:
        if media_duration_seconds is None:
            return None
        safe_duration = max(0.0, media_duration_seconds)
        if safe_duration <= 0:
            return 0
        return int(max(0.0, safe_duration - 0.001) * fps)
