"""Tests for the multi-reader scrub-aware behaviour of PersistentFFmpegFramePool.

The pool keeps multiple readers per (file, fps, filter, dims) so that
scrub-heavy access can hit a recently warmed reader without paying the
~80 ms ffmpeg respawn cost on every backward seek. Selection prefers
exact next_frame_index matches and falls back to a small forward-skip
budget; otherwise a new reader is spawned (with LRU eviction inside
the per-key cap).
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

from app.infrastructure.ffmpeg_gateway import FFmpegGateway
from app.infrastructure.persistent_ffmpeg_reader import PersistentFFmpegFramePool


def _write_fake_ffmpeg(tmp_path: Path, frame_count: int, width: int, height: int) -> Path:
    """Fake ffmpeg that emits ``frame_count`` raw BGRA frames on stdout.

    Frame N is filled with the byte ``N`` (mod 256). Argument-agnostic:
    the same script handles both fresh spawns and "respawn at frame X"
    requests because the pool just consumes the byte stream.
    """

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


class _FakeGateway(FFmpegGateway):
    def __init__(self, executable: Path) -> None:
        super().__init__(ffmpeg_executable=str(executable), use_hwaccel=False)
        self._is_available_cache = True


def _media(tmp_path: Path, name: str = "clip.mp4") -> Path:
    media = tmp_path / name
    media.write_bytes(b"x")
    return media


def test_pool_keeps_multiple_readers_per_clip(tmp_path: Path) -> None:
    """A backward seek must spawn a second reader and KEEP the first alive."""

    width, height = 2, 2
    fake_ffmpeg = _write_fake_ffmpeg(tmp_path, frame_count=8, width=width, height=height)
    media = _media(tmp_path)

    pool = PersistentFFmpegFramePool(_FakeGateway(fake_ffmpeg), max_active=4, max_per_key=3)
    try:
        # Reader A spawned at frame 5, advances to 6.
        a_first = pool.read_frames(
            media_path=str(media),
            fps=30.0,
            start_frame_index=5,
            frame_count=1,
            width=width,
            height=height,
            extra_video_filters=None,
        )
        assert [idx for idx, _ in a_first] == [5]

        # Backward seek to frame 0 → Reader B is spawned. Reader A
        # should still be alive (positioned at frame 6) so that a
        # subsequent scrub back to 6 can reuse it.
        b_first = pool.read_frames(
            media_path=str(media),
            fps=30.0,
            start_frame_index=0,
            frame_count=1,
            width=width,
            height=height,
            extra_video_filters=None,
        )
        assert [idx for idx, _ in b_first] == [0]
        assert pool.active_reader_count() == 2
    finally:
        pool.close()


def test_pool_reuses_warm_reader_for_scrub_back(tmp_path: Path) -> None:
    """User scrubs to frame X, then to Y, then back to X+1: reader-X is reused."""

    width, height = 2, 2
    fake_ffmpeg = _write_fake_ffmpeg(tmp_path, frame_count=8, width=width, height=height)
    media = _media(tmp_path)

    pool = PersistentFFmpegFramePool(_FakeGateway(fake_ffmpeg), max_active=4, max_per_key=3)
    try:
        # Spawn reader at frame 4 → next position 5.
        first = pool.read_frames(
            media_path=str(media),
            fps=30.0,
            start_frame_index=4,
            frame_count=1,
            width=width,
            height=height,
            extra_video_filters=None,
        )
        assert [idx for idx, _ in first] == [4]
        assert pool.active_reader_count() == 1

        # Spawn reader at frame 0 → next position 1.
        second = pool.read_frames(
            media_path=str(media),
            fps=30.0,
            start_frame_index=0,
            frame_count=1,
            width=width,
            height=height,
            extra_video_filters=None,
        )
        assert [idx for idx, _ in second] == [0]
        assert pool.active_reader_count() == 2

        # Scrub back to frame 5: the first reader is still positioned
        # at next_frame_index=5, so it must be reused without a third
        # spawn.
        third = pool.read_frames(
            media_path=str(media),
            fps=30.0,
            start_frame_index=5,
            frame_count=1,
            width=width,
            height=height,
            extra_video_filters=None,
        )
        assert [idx for idx, _ in third] == [5]
        assert pool.active_reader_count() == 2
    finally:
        pool.close()


def test_pool_uses_forward_skip_within_budget(tmp_path: Path) -> None:
    """A small forward gap re-uses the existing reader by discarding frames."""

    width, height = 2, 2
    fake_ffmpeg = _write_fake_ffmpeg(tmp_path, frame_count=8, width=width, height=height)
    media = _media(tmp_path)

    pool = PersistentFFmpegFramePool(
        _FakeGateway(fake_ffmpeg), max_active=4, max_per_key=3, skip_budget_frames=4
    )
    try:
        # Reader spawned at 0 → after 1 frame, next=1.
        pool.read_frames(
            media_path=str(media),
            fps=30.0,
            start_frame_index=0,
            frame_count=1,
            width=width,
            height=height,
            extra_video_filters=None,
        )
        assert pool.active_reader_count() == 1

        # Request frame 4 (gap = 3, within budget). Reader is reused
        # and 3 frames are discarded; no new reader is spawned.
        result = pool.read_frames(
            media_path=str(media),
            fps=30.0,
            start_frame_index=4,
            frame_count=1,
            width=width,
            height=height,
            extra_video_filters=None,
        )
        assert [idx for idx, _ in result] == [4]
        assert pool.active_reader_count() == 1
    finally:
        pool.close()


def test_pool_respects_skip_budget(tmp_path: Path) -> None:
    """A forward gap larger than the budget must spawn a new reader."""

    width, height = 2, 2
    fake_ffmpeg = _write_fake_ffmpeg(tmp_path, frame_count=8, width=width, height=height)
    media = _media(tmp_path)

    pool = PersistentFFmpegFramePool(
        _FakeGateway(fake_ffmpeg), max_active=4, max_per_key=3, skip_budget_frames=1
    )
    try:
        pool.read_frames(
            media_path=str(media),
            fps=30.0,
            start_frame_index=0,
            frame_count=1,
            width=width,
            height=height,
            extra_video_filters=None,
        )
        # Gap = 5, budget = 1 → must spawn a fresh reader.
        result = pool.read_frames(
            media_path=str(media),
            fps=30.0,
            start_frame_index=6,
            frame_count=1,
            width=width,
            height=height,
            extra_video_filters=None,
        )
        assert [idx for idx, _ in result] == [6]
        assert pool.active_reader_count() == 2
    finally:
        pool.close()


def test_pool_enforces_per_key_cap_with_lru_eviction(tmp_path: Path) -> None:
    """Spawning beyond ``max_per_key`` evicts the LRU reader for that clip."""

    width, height = 2, 2
    fake_ffmpeg = _write_fake_ffmpeg(tmp_path, frame_count=8, width=width, height=height)
    media = _media(tmp_path)

    pool = PersistentFFmpegFramePool(
        _FakeGateway(fake_ffmpeg), max_active=10, max_per_key=2, skip_budget_frames=0
    )
    try:
        for start in (0, 4, 6):
            pool.read_frames(
                media_path=str(media),
                fps=30.0,
                start_frame_index=start,
                frame_count=1,
                width=width,
                height=height,
                extra_video_filters=None,
            )
        # Three distinct backward-incompatible positions, but per-key
        # cap is 2 → only 2 readers may remain alive for this clip.
        assert pool.active_reader_count() == 2
    finally:
        pool.close()
