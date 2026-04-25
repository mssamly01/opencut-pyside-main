from __future__ import annotations

from pathlib import Path

from app.domain.clips.base_clip import BaseClip
from app.domain.clips.image_clip import ImageClip
from app.domain.clips.video_clip import VideoClip
from app.domain.media_asset import MediaAsset
from app.domain.project import Project
from app.infrastructure.ffmpeg_gateway import FFmpegGateway


class ThumbnailService:
    def __init__(
        self,
        ffmpeg_gateway: FFmpegGateway | None = None,
        cache_root: Path | None = None,
    ) -> None:
        self._ffmpeg_gateway = ffmpeg_gateway or FFmpegGateway()
        self._cache_root = cache_root or (Path.home() / ".opencut-pyside" / "cache" / "thumbnails")
        self._memory_cache: dict[str, bytes] = {}

    def get_thumbnail_bytes(
        self,
        project: Project,
        clip: BaseClip,
        project_path: str | None = None,
    ) -> bytes | None:
        if not isinstance(clip, (VideoClip, ImageClip)):
            return None

        media_asset = self._find_media_asset(project, clip.media_id)
        if media_asset is None:
            return None

        project_root = self._project_root(project_path)
        media_path = self._resolve_media_path(media_asset.file_path, project_root)
        if not media_path.exists() or not media_path.is_file():
            return None

        source_time = self._thumbnail_source_time(clip, media_asset)
        if isinstance(clip, ImageClip) or media_asset.media_type.lower() == "image":
            return self._get_image_bytes(media_path, media_asset.media_id, source_time)
        return self._get_video_frame_bytes(media_path, media_asset.media_id, source_time)

    def get_filmstrip_bytes(
        self,
        project: Project,
        clip: BaseClip,
        project_path: str | None = None,
        frame_count: int = 8,
    ) -> list[bytes]:
        if frame_count <= 0 or not isinstance(clip, VideoClip):
            return []

        media_asset = self._find_media_asset(project, clip.media_id)
        if media_asset is None:
            return []

        project_root = self._project_root(project_path)
        media_path = self._resolve_media_path(media_asset.file_path, project_root)
        if not media_path.exists() or not media_path.is_file():
            return []

        source_start, source_end = self._source_range(clip, media_asset)
        span = source_end - source_start
        if span <= 0.0 or frame_count == 1:
            sample_times = [source_start]
        else:
            sample_times = [
                max(0.0, source_start + span * (index + 0.5) / frame_count)
                for index in range(frame_count)
            ]

        frames: list[bytes] = []
        for source_time in sample_times:
            frame_bytes = self._get_video_frame_bytes(media_path, media_asset.media_id, source_time)
            if frame_bytes is not None:
                frames.append(frame_bytes)
        return frames

    def get_media_asset_thumbnail_bytes(
        self,
        media_asset: MediaAsset,
        project_path: str | None = None,
        source_time: float = 0.0,
    ) -> bytes | None:
        """Return a thumbnail directly from a MediaAsset (for media library UI)."""
        media_type = (media_asset.media_type or "").lower()
        if media_type not in ("video", "image"):
            return None

        project_root = self._project_root(project_path)
        media_path = self._resolve_media_path(media_asset.file_path, project_root)
        if not media_path.exists() or not media_path.is_file():
            return None

        effective_time = max(0.0, source_time)
        if media_asset.duration_seconds is not None and media_asset.duration_seconds > 0:
            effective_time = min(effective_time, max(0.0, media_asset.duration_seconds - 0.001))

        cache_path = self._cache_path(media_asset.media_id, effective_time)
        cached_bytes = self._read_cached_bytes(cache_path)
        if cached_bytes is not None:
            return cached_bytes

        if media_type == "image":
            try:
                image_bytes = media_path.read_bytes()
            except OSError:
                return None
            if not image_bytes:
                return None
            self._write_cached_bytes(cache_path, image_bytes)
            return image_bytes

        frame_bytes = self._ffmpeg_gateway.extract_frame_png(str(media_path), effective_time)
        if frame_bytes is None:
            return None
        self._write_cached_bytes(cache_path, frame_bytes)
        return frame_bytes

    def clear_memory_cache(self) -> None:
        self._memory_cache.clear()

    def _persist_cache(self, cache_path: Path, payload: bytes) -> None:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(payload)
        except OSError:
            return

    @staticmethod
    def _find_media_asset(project: Project, media_id: str | None) -> MediaAsset | None:
        if media_id is None:
            return None
        for media_asset in project.media_items:
            if media_asset.media_id == media_id:
                return media_asset
        return None

    @staticmethod
    def _thumbnail_source_time(clip: BaseClip, media_asset: MediaAsset) -> float:
        source_start, source_end = ThumbnailService._source_range(clip, media_asset)
        midpoint = source_start + (source_end - source_start) * 0.5
        return max(source_start, midpoint)

    @staticmethod
    def _source_range(clip: BaseClip, media_asset: MediaAsset) -> tuple[float, float]:
        source_start = max(0.0, clip.source_start)
        source_end = clip.source_end
        if source_end is None:
            source_end = clip.source_start + max(clip.duration, 0.0)
        if media_asset.duration_seconds is not None and media_asset.duration_seconds > 0:
            source_end = min(source_end, max(0.0, media_asset.duration_seconds - 0.001))
        return source_start, max(source_start, source_end)

    def _get_image_bytes(self, media_path: Path, media_id: str, source_time: float) -> bytes | None:
        cache_path = self._cache_path(media_id, source_time)
        cached_bytes = self._read_cached_bytes(cache_path)
        if cached_bytes is not None:
            return cached_bytes

        try:
            image_bytes = media_path.read_bytes()
        except OSError:
            return None
        if not image_bytes:
            return None

        self._write_cached_bytes(cache_path, image_bytes)
        return image_bytes

    def _get_video_frame_bytes(self, media_path: Path, media_id: str, source_time: float) -> bytes | None:
        cache_path = self._cache_path(media_id, source_time)
        cached_bytes = self._read_cached_bytes(cache_path)
        if cached_bytes is not None:
            return cached_bytes

        frame_bytes = self._ffmpeg_gateway.extract_frame_png(str(media_path), source_time)
        if frame_bytes is None:
            return None

        self._write_cached_bytes(cache_path, frame_bytes)
        return frame_bytes

    def _read_cached_bytes(self, cache_path: Path) -> bytes | None:
        cache_key = str(cache_path)
        cached = self._memory_cache.get(cache_key)
        if cached is not None:
            return cached

        if cache_path.exists() and cache_path.is_file():
            try:
                cached = cache_path.read_bytes()
            except OSError:
                cached = None
            if cached:
                self._memory_cache[cache_key] = cached
                return cached

        return None

    def _write_cached_bytes(self, cache_path: Path, payload: bytes) -> None:
        self._persist_cache(cache_path, payload)
        self._memory_cache[str(cache_path)] = payload

    def _cache_path(self, media_id: str, source_time: float) -> Path:
        normalized_media_id = media_id.strip() or "unknown"
        time_millis = int(round(max(0.0, source_time) * 1000.0))
        return self._cache_root / normalized_media_id / f"{time_millis}.png"

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
