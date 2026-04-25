from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MediaAsset:
    media_id: str
    name: str
    file_path: str
    media_type: str
    duration_seconds: float | None = None
    file_size_bytes: int | None = None
    width: int | None = None
    height: int | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    fps: float | None = None
    sample_rate: int | None = None
