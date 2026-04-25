"""GPU encoder probing utilities.

Probe ffmpeg encoders once and cache availability for this process.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GpuCodec:
    name: str
    description: str
    family: str


_KNOWN_GPU_CODECS: tuple[GpuCodec, ...] = (
    GpuCodec("h264_nvenc", "NVIDIA NVENC (H.264)", "nvenc"),
    GpuCodec("hevc_nvenc", "NVIDIA NVENC (H.265)", "nvenc"),
    GpuCodec("h264_qsv", "Intel Quick Sync (H.264)", "qsv"),
    GpuCodec("hevc_qsv", "Intel Quick Sync (H.265)", "qsv"),
    GpuCodec("h264_amf", "AMD AMF (H.264)", "amf"),
    GpuCodec("hevc_amf", "AMD AMF (H.265)", "amf"),
    GpuCodec("h264_videotoolbox", "Apple VideoToolbox (H.264)", "videotoolbox"),
    GpuCodec("hevc_videotoolbox", "Apple VideoToolbox (H.265)", "videotoolbox"),
)


class GpuEncoderProbe:
    def __init__(self, ffmpeg_executable: str = "ffmpeg") -> None:
        self._ffmpeg_executable = ffmpeg_executable
        self._available_cache: tuple[GpuCodec, ...] | None = None

    def available(self) -> tuple[GpuCodec, ...]:
        if self._available_cache is not None:
            return self._available_cache

        try:
            process = subprocess.run(
                [self._ffmpeg_executable, "-hide_banner", "-encoders"],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("GPU probe failed: %s", exc)
            self._available_cache = ()
            return ()

        output = (process.stdout or "") + (process.stderr or "")
        encoder_pattern = re.compile(r"^\s*[VAS\.]+\s+(\S+)", re.MULTILINE)
        present_names = set(encoder_pattern.findall(output))

        available = tuple(codec for codec in _KNOWN_GPU_CODECS if codec.name in present_names)
        self._available_cache = available
        return available

    def first_available_h264(self) -> GpuCodec | None:
        for codec in self.available():
            if "h264" in codec.name:
                return codec
        return None

    def codec_for_target(self, target: str) -> GpuCodec | None:
        target_lower = target.lower()
        for codec in self.available():
            if target_lower in codec.name.lower():
                return codec
        return None

    def reset_cache(self) -> None:
        self._available_cache = None
