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
