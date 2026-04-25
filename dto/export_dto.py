from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ExportResult:
    output_path: str
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ExportOptions:
    in_point_seconds: float | None = None
    out_point_seconds: float | None = None
    width_override: int | None = None
    height_override: int | None = None
    fps_override: float | None = None
    codec: str = "libx264"  # libx264 | libx265 | libvpx-vp9
    preset: str = "veryfast"
    crf: int = 23
    # None = software encode path.
    # "auto" = resolve first available H.264 GPU encoder.
    # explicit values: "h264_nvenc" | "h264_qsv" | "h264_amf" | "h264_videotoolbox"
    gpu_codec_override: str | None = None
