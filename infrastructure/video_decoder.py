from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from app.infrastructure.ffmpeg_gateway import FFmpegGateway


@dataclass(slots=True, frozen=True)
class DecodedFrame:
    frame_index: int
    payload: bytes


class VideoDecoder:
    """Cache-backed decoder facade for timeline preview frames."""

    def __init__(
        self,
        ffmpeg_gateway: FFmpegGateway | None = None,
        max_cache_entries: int = 360,
    ) -> None:
        self._ffmpeg_gateway = ffmpeg_gateway or FFmpegGateway()
        self._max_cache_entries = max(60, max_cache_entries)
        self._frame_cache: OrderedDict[tuple[str, int, int], bytes] = OrderedDict()
        self._prefetched_until: dict[tuple[str, int], int] = {}

    def get_frame(self, media_path: str, fps: float, frame_index: int) -> bytes | None:
        key = self._cache_key(media_path, fps, frame_index)
        payload = self._frame_cache.get(key)
        if payload is None:
            return None
        self._frame_cache.move_to_end(key)
        return payload

    def has_frame(self, media_path: str, fps: float, frame_index: int) -> bool:
        key = self._cache_key(media_path, fps, frame_index)
        return key in self._frame_cache

    def has_prefetched_until(self, media_path: str, fps: float, frame_index: int) -> bool:
        token = self._media_fps_token(media_path, fps)
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
        token = self._media_fps_token(media_path, safe_fps)
        current_max = self._prefetched_until.get(token, -1)
        if highest_index > current_max:
            self._prefetched_until[token] = highest_index

        for decoded in decoded_frames:
            key = self._cache_key(media_path, safe_fps, decoded.frame_index)
            if key in self._frame_cache:
                continue
            self._frame_cache[key] = decoded.payload
            self._frame_cache.move_to_end(key)

        while len(self._frame_cache) > self._max_cache_entries:
            self._frame_cache.popitem(last=False)

        return decoded_frames

    def put_frame(self, media_path: str, fps: float, frame_index: int, payload: bytes) -> None:
        key = self._cache_key(media_path, fps, frame_index)
        self._frame_cache[key] = payload
        self._frame_cache.move_to_end(key)
        token = self._media_fps_token(media_path, fps)
        current_max = self._prefetched_until.get(token, -1)
        if frame_index > current_max:
            self._prefetched_until[token] = frame_index
        while len(self._frame_cache) > self._max_cache_entries:
            self._frame_cache.popitem(last=False)

    @staticmethod
    def _cache_key(media_path: str, fps: float, frame_index: int) -> tuple[str, int, int]:
        fps_token = int(round(max(1.0, fps) * 1000.0))
        return (media_path, fps_token, max(0, int(frame_index)))

    @staticmethod
    def _media_fps_token(media_path: str, fps: float) -> tuple[str, int]:
        fps_token = int(round(max(1.0, fps) * 1000.0))
        return (media_path, fps_token)

    @staticmethod
    def _max_frame_index_for_duration(media_duration_seconds: float | None, fps: float) -> int | None:
        if media_duration_seconds is None:
            return None
        safe_duration = max(0.0, media_duration_seconds)
        if safe_duration <= 0:
            return 0
        return int(max(0.0, safe_duration - 0.001) * fps)
