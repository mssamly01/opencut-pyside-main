from __future__ import annotations

import struct
from pathlib import Path

from app.domain.clips.audio_clip import AudioClip
from app.domain.clips.base_clip import BaseClip
from app.domain.clips.video_clip import VideoClip
from app.domain.media_asset import MediaAsset
from app.domain.project import Project
from app.infrastructure.ffmpeg_gateway import FFmpegGateway


class WaveformService:
    """Generate and cache normalized audio peaks for timeline clips."""

    _SAMPLE_RATE = 8000
    _PEAKS_PER_SECOND = 40
    _MAX_PEAKS = 4000

    def __init__(
        self,
        ffmpeg_gateway: FFmpegGateway | None = None,
        cache_root: Path | None = None,
    ) -> None:
        self._ffmpeg_gateway = ffmpeg_gateway or FFmpegGateway()
        self._cache_root = cache_root or (Path.home() / ".opencut-pyside" / "cache" / "waveforms")
        self._memory_cache: dict[str, list[float]] = {}

    def get_peaks(
        self,
        project: Project,
        clip: BaseClip,
        project_path: str | None = None,
    ) -> list[float]:
        if not isinstance(clip, (AudioClip, VideoClip)):
            return []

        media_asset = self._find_media_asset(project, clip.media_id)
        if media_asset is None:
            return []
        return self.get_peaks_for_asset(media_asset, project_path)

    def get_peaks_for_asset(
        self,
        media_asset: MediaAsset,
        project_path: str | None = None,
    ) -> list[float]:
        if media_asset.media_type.lower() not in {"audio", "video"}:
            return []

        project_root = self._project_root(project_path)
        media_path = self._resolve_media_path(media_asset.file_path, project_root)
        if not media_path.exists() or not media_path.is_file():
            return []

        cache_path = self._cache_path(media_asset.media_id)
        cache_key = str(cache_path)
        in_memory = self._memory_cache.get(cache_key)
        if in_memory is not None:
            return in_memory

        disk_cached = self._read_peaks_from_disk(cache_path)
        if disk_cached:
            self._memory_cache[cache_key] = disk_cached
            return disk_cached

        samples = self._ffmpeg_gateway.extract_audio_samples_s16le(str(media_path), self._SAMPLE_RATE)
        if samples is None or len(samples) < 2:
            return []

        peaks = self._build_peaks(samples, media_asset.duration_seconds)
        if not peaks:
            return []

        self._persist_peaks(cache_path, peaks)
        self._memory_cache[cache_key] = peaks
        return peaks

    def clear_memory_cache(self) -> None:
        self._memory_cache.clear()

    def _build_peaks(self, samples: bytes, duration_seconds: float | None) -> list[float]:
        total_samples = len(samples) // 2
        if total_samples == 0:
            return []

        duration = float(duration_seconds) if duration_seconds and duration_seconds > 0 else total_samples / self._SAMPLE_RATE
        target_peaks = max(16, min(int(duration * self._PEAKS_PER_SECOND), self._MAX_PEAKS))
        bucket_size = max(1, total_samples // target_peaks)

        peaks: list[float] = []
        bucket_max = 0
        bucket_count = 0
        cursor = 0
        while cursor < len(samples) - 1:
            sample = struct.unpack_from("<h", samples, cursor)[0]
            bucket_max = max(bucket_max, abs(sample))
            bucket_count += 1
            if bucket_count >= bucket_size:
                peaks.append(min(1.0, bucket_max / 32768.0))
                bucket_max = 0
                bucket_count = 0
                if len(peaks) >= target_peaks:
                    break
            cursor += 2

        if bucket_count > 0 and len(peaks) < target_peaks:
            peaks.append(min(1.0, bucket_max / 32768.0))
        return peaks

    def _persist_peaks(self, cache_path: Path, peaks: list[float]) -> None:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = struct.pack(f"<I{len(peaks)}f", len(peaks), *peaks)
            cache_path.write_bytes(payload)
        except OSError:
            return

    def _read_peaks_from_disk(self, cache_path: Path) -> list[float]:
        if not cache_path.exists() or not cache_path.is_file():
            return []
        try:
            payload = cache_path.read_bytes()
        except OSError:
            return []

        if len(payload) < 4:
            return []

        (count,) = struct.unpack_from("<I", payload, 0)
        expected_size = 4 + count * 4
        if count <= 0 or count > self._MAX_PEAKS or len(payload) < expected_size:
            return []

        return list(struct.unpack_from(f"<{count}f", payload, 4))

    def _cache_path(self, media_id: str) -> Path:
        normalized = media_id.strip() or "unknown"
        return self._cache_root / f"{normalized}.peaks"

    @staticmethod
    def _find_media_asset(project: Project, media_id: str | None) -> MediaAsset | None:
        if media_id is None:
            return None
        for media_asset in project.media_items:
            if media_asset.media_id == media_id:
                return media_asset
        return None

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
