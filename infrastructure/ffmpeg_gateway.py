from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _bundled_ffmpeg_candidates(bin_dir: Path) -> list[Path]:
    """Return possible bundled ffmpeg binaries for the current platform."""

    if sys.platform.startswith("win"):
        names = ["ffmpeg.exe"]
    else:
        names = ["ffmpeg"]
    return [bin_dir / name for name in names]


class FFmpegGateway:
    def __init__(self, ffmpeg_executable: str | None = None, timeout_seconds: float = 8.0) -> None:
        self._ffmpeg_executable = self._resolve_ffmpeg_executable(ffmpeg_executable)
        self._timeout_seconds = timeout_seconds
        self._is_available_cache: bool | None = None

    def is_available(self) -> bool:
        if self._is_available_cache is None:
            executable_path = Path(self._ffmpeg_executable)
            self._is_available_cache = executable_path.exists() or shutil.which(self._ffmpeg_executable) is not None
        return self._is_available_cache

    def extract_frame_png(self, file_path: str, time_seconds: float) -> bytes | None:
        if not self.is_available():
            return None

        try:
            source_path = Path(file_path).expanduser().resolve()
        except OSError:
            return None

        if not source_path.exists() or not source_path.is_file():
            return None

        safe_time = max(0.0, float(time_seconds))

        command = self._build_extract_frame_command(source_path, safe_time, seek_before_input=True)
        frame_bytes = self._run_ffmpeg(command)
        if frame_bytes is not None:
            return frame_bytes

        # Fallback seek order for files that decode better with post-input seeking.
        fallback_command = self._build_extract_frame_command(source_path, safe_time, seek_before_input=False)
        return self._run_ffmpeg(fallback_command)

    def extract_frame_sequence_png(
        self,
        file_path: str,
        start_time_seconds: float,
        fps: float,
        frame_count: int,
    ) -> list[bytes]:
        if frame_count <= 0 or fps <= 0:
            return []

        if not self.is_available():
            return []

        try:
            source_path = Path(file_path).expanduser().resolve()
        except OSError:
            return []

        if not source_path.exists() or not source_path.is_file():
            return []

        safe_time = max(0.0, float(start_time_seconds))
        safe_fps = max(1.0, float(fps))
        safe_frame_count = max(1, int(frame_count))

        command = self._build_extract_frame_sequence_command(
            source_path=source_path,
            start_time_seconds=safe_time,
            fps=safe_fps,
            frame_count=safe_frame_count,
        )
        payload = self._run_ffmpeg(command)
        if payload is None:
            return []
        return self._split_png_stream(payload)

    def extract_audio_samples_s16le(self, file_path: str, sample_rate: int = 8000) -> bytes | None:
        if sample_rate <= 0 or not self.is_available():
            return None

        try:
            source_path = Path(file_path).expanduser().resolve()
        except OSError:
            return None

        if not source_path.exists() or not source_path.is_file():
            return None

        safe_sample_rate = max(1000, min(int(sample_rate), 192000))
        command = [
            self._ffmpeg_executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-i",
            str(source_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(safe_sample_rate),
            "-f",
            "s16le",
            "pipe:1",
        ]
        return self._run_ffmpeg(command)

    def _build_extract_frame_command(self, source_path: Path, time_seconds: float, seek_before_input: bool) -> list[str]:
        command = [self._ffmpeg_executable, "-hide_banner", "-loglevel", "error", "-nostdin"]
        if seek_before_input:
            command.extend(["-ss", f"{time_seconds:.6f}"])
        command.extend(["-i", str(source_path)])
        if not seek_before_input:
            command.extend(["-ss", f"{time_seconds:.6f}"])
        command.extend(
            [
                "-frames:v",
                "1",
                "-an",
                "-sn",
                "-dn",
                "-f",
                "image2pipe",
                "-vcodec",
                "png",
                "pipe:1",
            ]
        )
        return command

    def _build_extract_frame_sequence_command(
        self,
        source_path: Path,
        start_time_seconds: float,
        fps: float,
        frame_count: int,
    ) -> list[str]:
        return [
            self._ffmpeg_executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-ss",
            f"{start_time_seconds:.6f}",
            "-i",
            str(source_path),
            "-vf",
            f"fps={fps:.6f}",
            "-frames:v",
            str(frame_count),
            "-an",
            "-sn",
            "-dn",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "pipe:1",
        ]

    def _run_ffmpeg(self, command: list[str]) -> bytes | None:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                check=False,
                timeout=self._timeout_seconds,
            )
        except OSError as exc:
            logger.warning("ffmpeg OS error: %s", exc)
            return None
        except subprocess.SubprocessError as exc:
            logger.warning("ffmpeg subprocess error: %s", exc)
            return None

        if result.returncode != 0:
            stderr_text = result.stderr.decode("utf-8", errors="ignore").strip()
            logger.debug("ffmpeg failed (returncode=%s) cmd=%s stderr=%s", result.returncode, " ".join(command), stderr_text)
            return None

        if not result.stdout:
            logger.debug("ffmpeg produced no output for cmd=%s", " ".join(command))
            return None

        return bytes(result.stdout)

    @staticmethod
    def _split_png_stream(payload: bytes) -> list[bytes]:
        if not payload:
            return []

        signature = b"\x89PNG\r\n\x1a\n"
        frames: list[bytes] = []
        index = 0

        while index < len(payload):
            frame_start = payload.find(signature, index)
            if frame_start < 0:
                break

            cursor = frame_start + len(signature)
            frame_end: int | None = None
            while cursor + 8 <= len(payload):
                chunk_length = int.from_bytes(payload[cursor : cursor + 4], byteorder="big")
                chunk_type = payload[cursor + 4 : cursor + 8]
                cursor += 8
                chunk_data_end = cursor + chunk_length
                chunk_crc_end = chunk_data_end + 4

                if chunk_crc_end > len(payload):
                    frame_end = None
                    break

                cursor = chunk_crc_end
                if chunk_type == b"IEND":
                    frame_end = cursor
                    break

            if frame_end is None:
                break

            frames.append(payload[frame_start:frame_end])
            index = frame_end

        return frames

    @staticmethod
    def _resolve_ffmpeg_executable(explicit_executable: str | None) -> str:
        """Resolve the ffmpeg executable across Windows/macOS/Linux.

        Preference order:
            1. Explicit path passed in (if it exists).
            2. Explicit name resolvable via ``shutil.which``.
            3. Platform-appropriate bundled binary in ``<repo>/bin``.
            4. System ``ffmpeg`` / ``ffmpeg.exe`` on ``PATH``.
            5. Fallback string ``"ffmpeg"`` so callers can still fail gracefully.
        """

        if explicit_executable:
            explicit_path = Path(explicit_executable).expanduser()
            if explicit_path.exists():
                return str(explicit_path.resolve())

            system_explicit = shutil.which(explicit_executable)
            if system_explicit is not None:
                return system_explicit

            return explicit_executable

        bin_dir = Path(__file__).resolve().parents[1] / "bin"
        for candidate in _bundled_ffmpeg_candidates(bin_dir):
            if candidate.exists():
                return str(candidate)

        for name in ("ffmpeg", "ffmpeg.exe"):
            system_executable = shutil.which(name)
            if system_executable is not None:
                return system_executable

        return "ffmpeg"
