"""Thin ffprobe wrapper used to pull duration and stream metadata from media."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class MediaProbeResult:
    duration_seconds: float | None
    has_video_stream: bool
    has_audio_stream: bool
    width: int | None = None
    height: int | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    fps: float | None = None
    sample_rate: int | None = None


def _bundled_ffprobe_candidates(bin_dir: Path) -> list[Path]:
    if sys.platform.startswith("win"):
        names = ["ffprobe.exe"]
    else:
        names = ["ffprobe"]
    return [bin_dir / name for name in names]


class FFprobeGateway:
    """Wrapper that shells out to ffprobe to introspect media files."""

    def __init__(self, ffprobe_executable: str | None = None, timeout_seconds: float = 6.0) -> None:
        self._ffprobe_executable = self._resolve_ffprobe_executable(ffprobe_executable)
        self._timeout_seconds = timeout_seconds
        self._is_available_cache: bool | None = None

    def is_available(self) -> bool:
        if self._is_available_cache is None:
            executable_path = Path(self._ffprobe_executable)
            self._is_available_cache = (
                executable_path.exists() or shutil.which(self._ffprobe_executable) is not None
            )
        return self._is_available_cache

    def probe(self, file_path: str) -> MediaProbeResult | None:
        """Return duration / stream metadata for ``file_path`` or ``None`` on failure."""

        if not self.is_available():
            return None

        try:
            source_path = Path(file_path).expanduser().resolve()
        except OSError:
            return None

        if not source_path.exists() or not source_path.is_file():
            return None

        command = [
            self._ffprobe_executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(source_path),
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                check=False,
                timeout=self._timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("ffprobe failed for %s: %s", source_path, exc)
            return None

        if result.returncode != 0 or not result.stdout:
            return None

        try:
            payload = json.loads(result.stdout.decode("utf-8", errors="ignore"))
        except json.JSONDecodeError:
            return None

        duration = self._extract_duration(payload)
        has_video, has_audio = self._extract_stream_flags(payload)
        stream_details = self._extract_stream_details(payload)
        return MediaProbeResult(
            duration_seconds=duration,
            has_video_stream=has_video,
            has_audio_stream=has_audio,
            width=stream_details["width"],
            height=stream_details["height"],
            video_codec=stream_details["video_codec"],
            audio_codec=stream_details["audio_codec"],
            fps=stream_details["fps"],
            sample_rate=stream_details["sample_rate"],
        )

    @staticmethod
    def _extract_duration(payload: dict) -> float | None:
        format_info = payload.get("format")
        if isinstance(format_info, dict):
            raw_duration = format_info.get("duration")
            try:
                if raw_duration is not None:
                    value = float(raw_duration)
                    if value > 0:
                        return value
            except (TypeError, ValueError):
                pass

        streams = payload.get("streams")
        best_duration: float | None = None
        if isinstance(streams, list):
            for stream in streams:
                if not isinstance(stream, dict):
                    continue
                raw_duration = stream.get("duration")
                try:
                    if raw_duration is None:
                        continue
                    value = float(raw_duration)
                except (TypeError, ValueError):
                    continue
                if value <= 0:
                    continue
                if best_duration is None or value > best_duration:
                    best_duration = value
        return best_duration

    @staticmethod
    def _extract_stream_flags(payload: dict) -> tuple[bool, bool]:
        has_video = False
        has_audio = False
        streams = payload.get("streams")
        if isinstance(streams, list):
            for stream in streams:
                if not isinstance(stream, dict):
                    continue
                codec_type = str(stream.get("codec_type", "")).lower()
                if codec_type == "video":
                    has_video = True
                elif codec_type == "audio":
                    has_audio = True
        return has_video, has_audio

    @staticmethod
    def _extract_stream_details(payload: dict) -> dict:
        """Extract metadata from first video/audio streams where available."""
        details: dict = {
            "width": None,
            "height": None,
            "video_codec": None,
            "audio_codec": None,
            "fps": None,
            "sample_rate": None,
        }
        streams = payload.get("streams")
        if not isinstance(streams, list):
            return details

        for stream in streams:
            if not isinstance(stream, dict):
                continue
            codec_type = str(stream.get("codec_type", "")).lower()
            if codec_type == "video" and details["video_codec"] is None:
                codec_name = stream.get("codec_name")
                if isinstance(codec_name, str) and codec_name:
                    details["video_codec"] = codec_name

                width = stream.get("width")
                height = stream.get("height")
                if isinstance(width, int) and width > 0:
                    details["width"] = width
                if isinstance(height, int) and height > 0:
                    details["height"] = height

                rate_str = stream.get("avg_frame_rate") or stream.get("r_frame_rate")
                details["fps"] = FFprobeGateway._parse_frame_rate(rate_str)
            elif codec_type == "audio" and details["audio_codec"] is None:
                codec_name = stream.get("codec_name")
                if isinstance(codec_name, str) and codec_name:
                    details["audio_codec"] = codec_name
                sample_rate_str = stream.get("sample_rate")
                try:
                    if sample_rate_str is not None:
                        sample_rate = int(sample_rate_str)
                        if sample_rate > 0:
                            details["sample_rate"] = sample_rate
                except (TypeError, ValueError):
                    continue
        return details

    @staticmethod
    def _parse_frame_rate(rate_str: str | None) -> float | None:
        if not isinstance(rate_str, str) or not rate_str:
            return None
        if "/" not in rate_str:
            try:
                value = float(rate_str)
            except (TypeError, ValueError):
                return None
            return value if value > 0 else None
        try:
            num_str, den_str = rate_str.split("/", 1)
            num = float(num_str)
            den = float(den_str)
            if num <= 0 or den <= 0:
                return None
            return num / den
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _resolve_ffprobe_executable(explicit_executable: str | None) -> str:
        if explicit_executable:
            explicit_path = Path(explicit_executable).expanduser()
            if explicit_path.exists():
                return str(explicit_path.resolve())

            system_explicit = shutil.which(explicit_executable)
            if system_explicit is not None:
                return system_explicit

            return explicit_executable

        bin_dir = Path(__file__).resolve().parents[1] / "bin"
        for candidate in _bundled_ffprobe_candidates(bin_dir):
            if candidate.exists():
                return str(candidate)

        for name in ("ffprobe", "ffprobe.exe"):
            system_executable = shutil.which(name)
            if system_executable is not None:
                return system_executable

        return "ffprobe"
