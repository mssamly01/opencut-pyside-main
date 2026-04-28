"""Tests for the persistent ffmpeg pool that powers preview frame decoding.

These tests use a tiny shell-script stand-in for ``ffmpeg`` so the test
suite can exercise the pool's process lifecycle (spawn, sequential
read, reuse, evict, respawn-on-seek) on any machine that has ``bash``
available — without depending on a real ffmpeg binary.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from app.infrastructure.ffmpeg_gateway import FFmpegGateway
from app.infrastructure.persistent_ffmpeg_reader import (
    PersistentFFmpegFramePool,
    wrap_bgra_as_bmp,
)


def _write_fake_ffmpeg(tmp_path: Path, frame_count: int, width: int, height: int) -> Path:
    """Write a fake ffmpeg that emits ``frame_count`` raw BGRA frames on stdout.

    Frame N is filled with the byte ``N`` (mod 256) so tests can assert the
    pool returned the expected sequence. The script ignores all arguments
    other than its own existence, which is exactly the contract the pool
    needs because the pool only cares about the stdout byte stream.

    On POSIX we return a Python script with a shebang. On Windows we return
    a ``.cmd`` shim that invokes the same Python script, because Windows
    cannot exec ``.py`` files via ``Popen([path, ...])`` directly.
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
        return cmd_path
    return script_path


class _FakeFFmpegGateway(FFmpegGateway):
    def __init__(self, executable: Path) -> None:
        super().__init__(ffmpeg_executable=str(executable))
        self._is_available_cache = True


def _bmp_pixel_byte(frame_payload: bytes, width: int, height: int) -> int:
    """Return the constant-fill byte of a BMP frame produced by the fake binary."""
    expected_size = width * height * 4 + 14 + 108
    assert len(frame_payload) == expected_size
    pixel_offset = 14 + 108
    return frame_payload[pixel_offset]


def test_wrap_bgra_as_bmp_produces_loadable_bmp() -> None:
    width, height = 4, 2
    bgra = bytes(range(width * height * 4))
    bmp = wrap_bgra_as_bmp(bgra, width, height)

    assert bmp.startswith(b"BM")
    # File size at offset 2..6.
    assert int.from_bytes(bmp[2:6], "little") == len(bmp)
    # Pixel data offset at 10..14.
    assert int.from_bytes(bmp[10:14], "little") == 14 + 108
    # BGRA payload follows the headers verbatim.
    assert bmp[14 + 108 :] == bgra


def _media_file(tmp_path: Path) -> Path:
    media = tmp_path / "fake_video.mp4"
    media.write_bytes(b"placeholder")
    return media


def test_pool_reads_sequential_frames_from_one_process(tmp_path: Path) -> None:
    width, height = 2, 2
    fake_ffmpeg = _write_fake_ffmpeg(tmp_path, frame_count=4, width=width, height=height)
    media_file = _media_file(tmp_path)

    pool = PersistentFFmpegFramePool(_FakeFFmpegGateway(fake_ffmpeg), max_active=2)
    try:
        first = pool.read_frames(
            media_path=str(media_file),
            fps=30.0,
            start_frame_index=0,
            frame_count=2,
            width=width,
            height=height,
            extra_video_filters=None,
        )
        assert [idx for idx, _ in first] == [0, 1]
        assert _bmp_pixel_byte(first[0][1], width, height) == 0
        assert _bmp_pixel_byte(first[1][1], width, height) == 1

        second = pool.read_frames(
            media_path=str(media_file),
            fps=30.0,
            start_frame_index=2,
            frame_count=2,
            width=width,
            height=height,
            extra_video_filters=None,
        )
        assert [idx for idx, _ in second] == [2, 3]
        assert _bmp_pixel_byte(second[0][1], width, height) == 2
        assert _bmp_pixel_byte(second[1][1], width, height) == 3
    finally:
        pool.close()


def test_pool_respawns_when_caller_seeks_backwards(tmp_path: Path) -> None:
    width, height = 2, 2
    fake_ffmpeg = _write_fake_ffmpeg(tmp_path, frame_count=4, width=width, height=height)
    media_file = _media_file(tmp_path)

    pool = PersistentFFmpegFramePool(_FakeFFmpegGateway(fake_ffmpeg), max_active=4)
    try:
        forward = pool.read_frames(
            media_path=str(media_file),
            fps=30.0,
            start_frame_index=2,
            frame_count=1,
            width=width,
            height=height,
            extra_video_filters=None,
        )
        assert [idx for idx, _ in forward] == [2]

        # The fake script always restarts at frame 0 when respawned, so a
        # backward seek to index 0 must indeed be served by a new process.
        seek_back = pool.read_frames(
            media_path=str(media_file),
            fps=30.0,
            start_frame_index=0,
            frame_count=1,
            width=width,
            height=height,
            extra_video_filters=None,
        )
        assert [idx for idx, _ in seek_back] == [0]
        assert _bmp_pixel_byte(seek_back[0][1], width, height) == 0
        # Multi-reader pool keeps the earlier (forward-position) reader
        # alive for future scrub-back-to-here reuse, alongside the new
        # backward reader. Per-key cap defaults to 3.
        assert pool.active_reader_count() == 2
    finally:
        pool.close()


def test_pool_evicts_oldest_when_capacity_reached(tmp_path: Path) -> None:
    width, height = 2, 2
    fake_ffmpeg = _write_fake_ffmpeg(tmp_path, frame_count=2, width=width, height=height)
    pool = PersistentFFmpegFramePool(_FakeFFmpegGateway(fake_ffmpeg), max_active=2)
    media_a = tmp_path / "a.mp4"
    media_b = tmp_path / "b.mp4"
    media_c = tmp_path / "c.mp4"
    for media in (media_a, media_b, media_c):
        media.write_bytes(b"x")

    try:
        for media in (media_a, media_b, media_c):
            pool.read_frames(
                media_path=str(media),
                fps=30.0,
                start_frame_index=0,
                frame_count=1,
                width=width,
                height=height,
                extra_video_filters=None,
            )
        assert pool.active_reader_count() == 2
    finally:
        pool.close()


def test_pool_returns_empty_when_ffmpeg_unavailable(tmp_path: Path) -> None:
    media = tmp_path / "video.mp4"
    media.write_bytes(b"x")

    class _Unavailable(FFmpegGateway):
        def is_available(self) -> bool:  # type: ignore[override]
            return False

    pool = PersistentFFmpegFramePool(_Unavailable(ffmpeg_executable="/nonexistent/ffmpeg"))
    assert (
        pool.read_frames(
            media_path=str(media),
            fps=30.0,
            start_frame_index=0,
            frame_count=2,
            width=4,
            height=4,
            extra_video_filters=None,
        )
        == []
    )


def test_pool_returns_empty_when_media_path_missing(tmp_path: Path) -> None:
    fake_ffmpeg = _write_fake_ffmpeg(tmp_path, frame_count=1, width=2, height=2)
    pool = PersistentFFmpegFramePool(_FakeFFmpegGateway(fake_ffmpeg))
    try:
        assert (
            pool.read_frames(
                media_path=str(tmp_path / "does-not-exist.mp4"),
                fps=30.0,
                start_frame_index=0,
                frame_count=1,
                width=2,
                height=2,
                extra_video_filters=None,
            )
            == []
        )
    finally:
        pool.close()


def test_video_decoder_uses_pool_when_dimensions_provided(tmp_path: Path) -> None:
    from app.infrastructure.video_decoder import VideoDecoder

    width, height = 2, 2
    fake_ffmpeg = _write_fake_ffmpeg(tmp_path, frame_count=3, width=width, height=height)
    media = tmp_path / "v.mp4"
    media.write_bytes(b"x")

    pool = PersistentFFmpegFramePool(_FakeFFmpegGateway(fake_ffmpeg))
    decoder = VideoDecoder(frame_pool=pool)
    try:
        frames = decoder.decode_window(
            media_path=str(media),
            fps=30.0,
            start_frame_index=0,
            frame_count=3,
            media_duration_seconds=None,
            extra_video_filters=None,
            frame_dimensions=(width, height),
        )
        assert [frame.frame_index for frame in frames] == [0, 1, 2]
        assert all(frame.payload.startswith(b"BM") for frame in frames)
    finally:
        pool.close()
