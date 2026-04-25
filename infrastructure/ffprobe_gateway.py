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
        return MediaProbeResult(
            duration_seconds=duration,
            has_video_stream=has_video,
            has_audio_stream=has_audio,
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
