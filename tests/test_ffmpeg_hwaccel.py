"""Tests for the ffmpeg hwaccel probe and per-file fallback path.

The probe runs ``ffmpeg -hwaccels`` once per binary; the gateway and
PersistentFFmpegFramePool inject ``-hwaccel <name>`` if a usable accel
was reported and fall back to software decoding when the accelerated
attempt produces no output (codec/profile not supported by the GPU).
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from unittest.mock import patch

from app.infrastructure import ffmpeg_hwaccel
from app.infrastructure.ffmpeg_gateway import FFmpegGateway
from app.infrastructure.ffmpeg_hwaccel import (
    _reset_cache_for_tests,
    hwaccel_args,
    probe_hwaccel,
)
from app.infrastructure.persistent_ffmpeg_reader import PersistentFFmpegFramePool


class _FakeProcess:
    def __init__(self, stdout: bytes = b"", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = b""
        self.returncode = returncode


def test_probe_hwaccel_picks_highest_priority_listed() -> None:
    _reset_cache_for_tests()
    fake_listing = b"Hardware acceleration methods:\nvaapi\ncuda\nqsv\nvdpau\n"
    with patch.object(
        ffmpeg_hwaccel.subprocess,
        "run",
        return_value=_FakeProcess(stdout=fake_listing),
    ):
        assert probe_hwaccel("/fake/ffmpeg") == "cuda"


def test_probe_hwaccel_returns_none_when_no_supported_accel() -> None:
    _reset_cache_for_tests()
    fake_listing = b"Hardware acceleration methods:\nvdpau\nopencl\ndrm\n"
    with patch.object(
        ffmpeg_hwaccel.subprocess,
        "run",
        return_value=_FakeProcess(stdout=fake_listing),
    ):
        assert probe_hwaccel("/fake/ffmpeg") is None


def test_probe_hwaccel_returns_none_when_subprocess_fails() -> None:
    _reset_cache_for_tests()

    def _raises(*_args, **_kwargs):
        raise OSError("no such binary")

    with patch.object(ffmpeg_hwaccel.subprocess, "run", side_effect=_raises):
        assert probe_hwaccel("/fake/missing") is None


def test_probe_hwaccel_caches_first_result() -> None:
    _reset_cache_for_tests()
    fake_listing = b"Hardware acceleration methods:\nvaapi\n"
    call_count = {"n": 0}

    def _counted(*_args, **_kwargs):
        call_count["n"] += 1
        return _FakeProcess(stdout=fake_listing)

    with patch.object(ffmpeg_hwaccel.subprocess, "run", side_effect=_counted):
        first = probe_hwaccel("/fake/ffmpeg")
        second = probe_hwaccel("/fake/ffmpeg")
        third = probe_hwaccel("/fake/ffmpeg")

    assert first == second == third == "vaapi"
    assert call_count["n"] == 1


def test_hwaccel_args_helper() -> None:
    assert hwaccel_args(None) == []
    assert hwaccel_args("") == []
    assert hwaccel_args("cuda") == ["-hwaccel", "cuda"]


def test_gateway_hwaccel_disabled_returns_no_args() -> None:
    gateway = FFmpegGateway(ffmpeg_executable="/fake/ffmpeg", use_hwaccel=False)
    assert gateway.hwaccel_name() is None
    assert gateway._resolved_hwaccel_args() == []  # noqa: SLF001


def test_gateway_uses_probed_hwaccel_when_enabled() -> None:
    _reset_cache_for_tests()
    fake_listing = b"Hardware acceleration methods:\ncuda\n"
    with patch.object(
        ffmpeg_hwaccel.subprocess,
        "run",
        return_value=_FakeProcess(stdout=fake_listing),
    ):
        gateway = FFmpegGateway(ffmpeg_executable="/fake/ffmpeg")
        assert gateway.hwaccel_name() == "cuda"
        assert gateway._resolved_hwaccel_args() == ["-hwaccel", "cuda"]  # noqa: SLF001


def test_extract_frame_command_injects_hwaccel_before_input() -> None:
    gateway = FFmpegGateway(ffmpeg_executable="/fake/ffmpeg", use_hwaccel=False)
    command = gateway._build_extract_frame_command(  # noqa: SLF001
        Path("/tmp/clip.mp4"),
        time_seconds=1.0,
        seek_before_input=True,
        extra_video_filters=None,
        hwaccel_args=["-hwaccel", "cuda"],
    )
    # -hwaccel must precede -i so ffmpeg applies it to the input demux.
    assert "-hwaccel" in command
    hwaccel_pos = command.index("-hwaccel")
    input_pos = command.index("-i")
    assert hwaccel_pos < input_pos
    assert command[hwaccel_pos + 1] == "cuda"


def test_extract_frame_sequence_command_injects_hwaccel_before_input() -> None:
    gateway = FFmpegGateway(ffmpeg_executable="/fake/ffmpeg", use_hwaccel=False)
    command = gateway._build_extract_frame_sequence_command(  # noqa: SLF001
        source_path=Path("/tmp/clip.mp4"),
        start_time_seconds=0.0,
        fps=30.0,
        frame_count=4,
        extra_video_filters=None,
        hwaccel_args=["-hwaccel", "vaapi"],
    )
    hwaccel_pos = command.index("-hwaccel")
    input_pos = command.index("-i")
    assert hwaccel_pos < input_pos
    assert command[hwaccel_pos + 1] == "vaapi"


# ---------------------------------------------------------------------------
# Per-file fallback in PersistentFFmpegFramePool.
# ---------------------------------------------------------------------------


def _write_fake_ffmpeg_with_hwaccel_fail(
    tmp_path: Path, frame_count: int, width: int, height: int
) -> Path:
    """Fake ffmpeg that emits zero bytes when ``-hwaccel`` is in argv.

    On the first call the pool will pass ``-hwaccel <name>``. The fake
    detects this and exits with no output to simulate "codec not
    supported by GPU". The second call (sw fallback) emits real
    frames so the pool can return a valid result.
    """

    import sys

    script_path = tmp_path / "fake_ffmpeg.py"
    frame_size = width * height * 4
    script_path.write_text(
        "\n".join(
            [
                f"#!{sys.executable}",
                "import sys",
                f"FRAME_COUNT = {frame_count}",
                f"FRAME_SIZE = {frame_size}",
                'if "-hwaccel" in sys.argv:',
                "    sys.exit(0)",
                "for i in range(FRAME_COUNT):",
                "    sys.stdout.buffer.write(bytes([(i + 1) % 256]) * FRAME_SIZE)",
                "    sys.stdout.buffer.flush()",
                "",
            ]
        )
    )
    script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    if os.name == "nt":
        cmd_path = tmp_path / "fake_ffmpeg.cmd"
        cmd_path.write_text(f'@"{sys.executable}" "{script_path}" %*\r\n')
        return cmd_path
    return script_path


class _HwaccelGateway(FFmpegGateway):
    """Gateway that pretends ``cuda`` was probed without hitting the network."""

    def __init__(self, executable: Path, hwaccel_name: str | None = "cuda") -> None:
        super().__init__(ffmpeg_executable=str(executable))
        self._is_available_cache = True
        self._hwaccel_resolved = True
        self._hwaccel_name = hwaccel_name


def test_pool_falls_back_to_sw_when_hwaccel_yields_no_frames(tmp_path: Path) -> None:
    width, height = 2, 2
    fake_ffmpeg = _write_fake_ffmpeg_with_hwaccel_fail(
        tmp_path, frame_count=2, width=width, height=height
    )
    media = tmp_path / "video.mp4"
    media.write_bytes(b"x")

    gateway = _HwaccelGateway(fake_ffmpeg, hwaccel_name="cuda")
    pool = PersistentFFmpegFramePool(gateway, max_active=2)
    try:
        frames = pool.read_frames(
            media_path=str(media),
            fps=30.0,
            start_frame_index=0,
            frame_count=2,
            width=width,
            height=height,
            extra_video_filters=None,
        )
        # SW fallback succeeded: pool returned frames despite hwaccel failure.
        assert len(frames) == 2
        assert [idx for idx, _ in frames] == [0, 1]

        # Subsequent reads on the same file must skip hwaccel entirely
        # (sticky per-file blacklist) so the pool does not pay the
        # respawn cost on every miss.
        resolved = str(Path(media).resolve())
        assert resolved in pool._sw_only_paths  # noqa: SLF001
    finally:
        pool.close()


def test_pool_uses_hwaccel_when_decode_succeeds(tmp_path: Path) -> None:
    width, height = 2, 2
    import sys

    script_path = tmp_path / "fake_ffmpeg.py"
    frame_size = width * height * 4
    script_path.write_text(
        "\n".join(
            [
                f"#!{sys.executable}",
                "import sys",
                f"FRAME_COUNT = {2}",
                f"FRAME_SIZE = {frame_size}",
                "for i in range(FRAME_COUNT):",
                "    sys.stdout.buffer.write(bytes([i % 256]) * FRAME_SIZE)",
                "    sys.stdout.buffer.flush()",
                "",
            ]
        )
    )
    script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    if os.name == "nt":
        cmd_path = tmp_path / "fake_ffmpeg.cmd"
        cmd_path.write_text(f'@"{sys.executable}" "{script_path}" %*\r\n')
        executable = cmd_path
    else:
        executable = script_path

    media = tmp_path / "video.mp4"
    media.write_bytes(b"x")

    gateway = _HwaccelGateway(executable, hwaccel_name="cuda")
    pool = PersistentFFmpegFramePool(gateway)
    try:
        frames = pool.read_frames(
            media_path=str(media),
            fps=30.0,
            start_frame_index=0,
            frame_count=2,
            width=width,
            height=height,
            extra_video_filters=None,
        )
        assert len(frames) == 2
        # Hwaccel succeeded → no entry in the sw-only set.
        resolved = str(Path(media).resolve())
        assert resolved not in pool._sw_only_paths  # noqa: SLF001
    finally:
        pool.close()
