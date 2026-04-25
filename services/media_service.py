from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.domain.media_asset import MediaAsset
from app.infrastructure.ffprobe_gateway import FFprobeGateway


class MediaService:
    _VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
    _AUDIO_EXTENSIONS = {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a"}
    _IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}

    def __init__(self, ffprobe_gateway: FFprobeGateway | None = None) -> None:
        self._ffprobe_gateway = ffprobe_gateway or FFprobeGateway()

    def import_files(self, file_paths: list[str]) -> list[MediaAsset]:
        imported_assets: list[MediaAsset] = []
        seen_paths: set[str] = set()

        for file_path in file_paths:
            normalized_path = self._normalize_path(file_path)
            if normalized_path is None or normalized_path in seen_paths:
                continue
            seen_paths.add(normalized_path)

            try:
                media_asset = self.load_media_metadata(normalized_path)
            except OSError:
                continue
            imported_assets.append(media_asset)

        return imported_assets

    def load_media_metadata(self, file_path: str) -> MediaAsset:
        resolved_path = Path(file_path).expanduser().resolve()
        if not resolved_path.exists() or not resolved_path.is_file():
            raise FileNotFoundError(f"Media file does not exist: {resolved_path}")

        media_type = self._infer_media_type(resolved_path.suffix.lower())
        file_size_bytes = resolved_path.stat().st_size
        media_id = f"media_{uuid4().hex[:10]}"

        probe_result = self._probe_media(str(resolved_path), media_type)

        return MediaAsset(
            media_id=media_id,
            name=resolved_path.stem,
            file_path=str(resolved_path),
            media_type=media_type,
            duration_seconds=probe_result.duration_seconds if probe_result else None,
            file_size_bytes=file_size_bytes,
            width=probe_result.width if probe_result else None,
            height=probe_result.height if probe_result else None,
            video_codec=probe_result.video_codec if probe_result else None,
            audio_codec=probe_result.audio_codec if probe_result else None,
            fps=probe_result.fps if probe_result else None,
            sample_rate=probe_result.sample_rate if probe_result else None,
        )

    def _probe_media(self, resolved_path: str, media_type: str):
        if media_type not in {"video", "audio"}:
            return None
        return self._ffprobe_gateway.probe(resolved_path)

    def _infer_media_type(self, extension: str) -> str:
        if extension in self._VIDEO_EXTENSIONS:
            return "video"
        if extension in self._AUDIO_EXTENSIONS:
            return "audio"
        if extension in self._IMAGE_EXTENSIONS:
            return "image"
        return "unknown"

    @staticmethod
    def _normalize_path(file_path: str) -> str | None:
        if not file_path:
            return None
        return str(Path(file_path).expanduser().resolve())
