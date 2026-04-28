"""Persistent ffmpeg process pool for raw-BGRA frame decoding.

The preview hot path used to spawn one ``ffmpeg`` subprocess per frame
request and read PNG-encoded output back through a pipe. Subprocess fork
overhead (~30-80 ms) plus PNG encoding of a 1080p frame (~30-80 ms) put
us well above the 33 ms-per-frame budget needed for 30 fps playback.

This module keeps a small pool of long-lived ``ffmpeg`` processes, each
producing raw BGRA frames at a fixed fps. Sequential reads (the common
playback case) reuse the live process; seeks/scrubs respawn it. Frames
are wrapped in a tiny BMP container so existing consumers can keep
loading them via ``QImage.fromData`` without changes — BMP encoding of
an already-BGRA buffer is essentially memcpy plus a 122-byte header,
costing well under 5 ms even at 1080p.
"""

from __future__ import annotations

import hashlib
import logging
import struct
import subprocess
import threading
from collections import OrderedDict
from pathlib import Path

from app.infrastructure.ffmpeg_gateway import FFmpegGateway

logger = logging.getLogger(__name__)


def wrap_bgra_as_bmp(bgra: bytes, width: int, height: int) -> bytes:
    """Wrap a top-down BGRA buffer in a BITMAPV4HEADER BMP container."""

    row_bytes = width * 4
    image_size = row_bytes * height
    header_size = 14 + 108
    file_size = header_size + image_size

    bmp = bytearray()
    # BITMAPFILEHEADER (14 bytes).
    bmp += b"BM"
    bmp += struct.pack("<I", file_size)
    bmp += struct.pack("<HH", 0, 0)
    bmp += struct.pack("<I", header_size)
    # BITMAPV4HEADER (108 bytes) — needed because BI_BITFIELDS BGRA needs
    # explicit channel masks to be loadable on every Qt platform.
    bmp += struct.pack("<I", 108)              # bV4Size
    bmp += struct.pack("<i", int(width))       # bV4Width
    bmp += struct.pack("<i", -int(height))     # negative => top-down rows
    bmp += struct.pack("<H", 1)                # bV4Planes
    bmp += struct.pack("<H", 32)               # bV4BitCount
    bmp += struct.pack("<I", 3)                # bV4V4Compression = BI_BITFIELDS
    bmp += struct.pack("<I", image_size)       # bV4SizeImage
    bmp += struct.pack("<i", 2835)             # bV4XPelsPerMeter (~72 dpi)
    bmp += struct.pack("<i", 2835)             # bV4YPelsPerMeter
    bmp += struct.pack("<I", 0)                # bV4ClrUsed
    bmp += struct.pack("<I", 0)                # bV4ClrImportant
    # ffmpeg ``-pix_fmt bgra`` writes bytes in B,G,R,A order, which means
    # the little-endian 32-bit pixel value is 0xAARRGGBB.
    bmp += struct.pack("<I", 0x00FF0000)       # red mask
    bmp += struct.pack("<I", 0x0000FF00)       # green mask
    bmp += struct.pack("<I", 0x000000FF)       # blue mask
    bmp += struct.pack("<I", 0xFF000000)       # alpha mask
    bmp += b"BGRs"                              # bV4CSType = LCS_sRGB
    bmp += b"\x00" * 36                         # CIEXYZTRIPLE (ignored when sRGB)
    bmp += struct.pack("<I", 0)                 # GammaRed
    bmp += struct.pack("<I", 0)                 # GammaGreen
    bmp += struct.pack("<I", 0)                 # GammaBlue
    bmp += bgra
    return bytes(bmp)


class _PersistentFrameReader:
    """One live ffmpeg process emitting raw BGRA frames at a fixed fps."""

    def __init__(
        self,
        ffmpeg_executable: str,
        media_path: str,
        fps: float,
        start_frame_index: int,
        width: int,
        height: int,
        extra_video_filters: list[str] | None,
        hwaccel_args: list[str] | None = None,
    ) -> None:
        self._ffmpeg_executable = ffmpeg_executable
        self._media_path = media_path
        self._fps = max(1.0, float(fps))
        self._width = int(width)
        self._height = int(height)
        self._extra_filters = list(extra_video_filters or [])
        self._hwaccel_args = list(hwaccel_args or [])
        self._frame_size = self._width * self._height * 4
        self._next_frame_index = max(0, int(start_frame_index))
        self._process: subprocess.Popen | None = None
        self._closed = False
        self._spawn(self._next_frame_index)

    @property
    def next_frame_index(self) -> int:
        return self._next_frame_index

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def used_hwaccel(self) -> bool:
        return bool(self._hwaccel_args)

    def _spawn(self, start_frame_index: int) -> None:
        start_seconds = max(0.0, start_frame_index / self._fps)
        filter_chain = [f"fps={self._fps:.6f}", *self._extra_filters]
        command = [
            self._ffmpeg_executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
        ]
        if self._hwaccel_args:
            command.extend(self._hwaccel_args)
        command.extend([
            "-ss",
            f"{start_seconds:.6f}",
            "-i",
            self._media_path,
            "-vf",
            ",".join(filter_chain),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgra",
            "pipe:1",
        ])
        try:
            self._process = subprocess.Popen(  # noqa: S603 - executable resolved by gateway
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )
        except OSError as exc:
            logger.warning("persistent ffmpeg spawn failed for %s: %s", self._media_path, exc)
            self._process = None

    def is_alive(self) -> bool:
        if self._process is None:
            return False
        return self._process.poll() is None

    def read_next(self) -> bytes | None:
        if self._closed or self._process is None or self._process.stdout is None:
            return None

        remaining = self._frame_size
        chunks: list[bytes] = []
        try:
            while remaining > 0:
                chunk = self._process.stdout.read(remaining)
                if not chunk:
                    return None  # EOF or process died mid-frame
                chunks.append(chunk)
                remaining -= len(chunk)
        except OSError as exc:
            logger.debug("persistent ffmpeg read error: %s", exc)
            return None

        bgra = b"".join(chunks)
        self._next_frame_index += 1
        return wrap_bgra_as_bmp(bgra, self._width, self._height)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        proc = self._process
        self._process = None
        if proc is None:
            return
        try:
            if proc.stdout is not None:
                proc.stdout.close()
        except OSError:
            pass
        try:
            proc.terminate()
            try:
                proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    pass
        except OSError:
            pass


class PersistentFFmpegFramePool:
    """Pool of persistent ffmpeg readers keyed by (media, fps, filter, dims).

    The pool now keeps **multiple** readers per ``base_key`` (up to
    ``max_per_key``) so scrub-heavy access can hit a recently warmed
    reader without paying the ~80 ms ffmpeg respawn cost on every
    backward seek. Selection order:

      1. Exact match: a reader whose ``next_frame_index`` equals the
         requested start frame is reused (sequential continuation).
      2. Forward-skip match: among readers positioned just before the
         requested start, pick the closest one and discard up to
         ``skip_budget_frames`` frames to align it. Reading and
         dropping a few frames over the raw-BGRA pipe is significantly
         cheaper than respawning ffmpeg for small gaps.
      3. Spawn fresh: if no candidate is reusable the pool spawns a
         new reader. When the per-key cap is reached the LRU reader
         under that key is evicted first; the global ``max_active``
         cap still applies as a hard upper bound.

    Internally the OrderedDict is keyed by ``(*base_key, reader_id)``
    so multiple readers can coexist under the same base_key while
    OrderedDict's recency ordering still drives LRU eviction.
    """

    def __init__(
        self,
        ffmpeg_gateway: FFmpegGateway | None = None,
        max_active: int = 6,
        max_per_key: int = 3,
        skip_budget_frames: int = 4,
    ) -> None:
        self._gateway = ffmpeg_gateway or FFmpegGateway()
        self._max_active = max(1, int(max_active))
        self._max_per_key = max(1, int(max_per_key))
        self._skip_budget_frames = max(0, int(skip_budget_frames))
        self._lock = threading.Lock()
        self._readers: OrderedDict[tuple, _PersistentFrameReader] = OrderedDict()
        self._next_reader_id = 0
        # Files for which hwaccel decoding has been observed to fail. Once a
        # file lands here we always spawn the reader without -hwaccel.
        self._sw_only_paths: set[str] = set()

    def is_available(self) -> bool:
        return self._gateway.is_available()

    @staticmethod
    def _key(
        media_path: str,
        fps: float,
        filter_token: str,
        width: int,
        height: int,
    ) -> tuple:
        fps_token = int(round(max(1.0, fps) * 1000.0))
        return (media_path, fps_token, filter_token, int(width), int(height))

    @staticmethod
    def _filter_token(extra_video_filters: list[str] | None) -> str:
        if not extra_video_filters:
            return ""
        joined = "|".join(extra_video_filters)
        return hashlib.sha1(joined.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]

    def read_frames(
        self,
        media_path: str,
        fps: float,
        start_frame_index: int,
        frame_count: int,
        width: int,
        height: int,
        extra_video_filters: list[str] | None = None,
        filter_token: str | None = None,
    ) -> list[tuple[int, bytes]]:
        """Read ``frame_count`` sequential frames starting at ``start_frame_index``.

        Returns a list of ``(frame_index, bmp_bytes)`` pairs. May return
        fewer entries than requested if the stream ends or the process
        dies. Returns an empty list if ffmpeg is unavailable or
        dimensions are invalid.
        """

        if frame_count <= 0 or width <= 0 or height <= 0:
            return []
        if not self._gateway.is_available():
            return []

        try:
            resolved_path = str(Path(media_path).expanduser().resolve())
        except OSError:
            return []
        if not Path(resolved_path).is_file():
            return []

        ffmpeg_executable = self._gateway._ffmpeg_executable
        token = filter_token if filter_token is not None else self._filter_token(extra_video_filters)
        key = self._key(resolved_path, fps, token, width, height)
        safe_start = max(0, int(start_frame_index))

        with self._lock:
            results, fallback_to_sw = self._read_locked(
                key=key,
                ffmpeg_executable=ffmpeg_executable,
                resolved_path=resolved_path,
                fps=fps,
                start_frame_index=safe_start,
                frame_count=int(frame_count),
                width=width,
                height=height,
                extra_video_filters=extra_video_filters,
                allow_hwaccel=resolved_path not in self._sw_only_paths,
            )
            if fallback_to_sw:
                self._sw_only_paths.add(resolved_path)
                results, _ = self._read_locked(
                    key=key,
                    ffmpeg_executable=ffmpeg_executable,
                    resolved_path=resolved_path,
                    fps=fps,
                    start_frame_index=safe_start,
                    frame_count=int(frame_count),
                    width=width,
                    height=height,
                    extra_video_filters=extra_video_filters,
                    allow_hwaccel=False,
                )

        return results

    def _read_locked(
        self,
        *,
        key: tuple,
        ffmpeg_executable: str,
        resolved_path: str,
        fps: float,
        start_frame_index: int,
        frame_count: int,
        width: int,
        height: int,
        extra_video_filters: list[str] | None,
        allow_hwaccel: bool,
    ) -> tuple[list[tuple[int, bytes]], bool]:
        """Try to fill ``frame_count`` frames; report whether hwaccel must be retired.

        Returns ``(results, fallback_to_sw)``. ``fallback_to_sw`` is True
        only when this attempt used hwaccel AND the very first read
        returned no payload (i.e. the codec is not supported by the
        accelerator on this host). The caller is expected to retry with
        ``allow_hwaccel=False`` in that case.
        """

        accel = self._gateway._resolved_hwaccel_args() if allow_hwaccel else []
        results: list[tuple[int, bytes]] = []

        chosen_full_key, chosen_reader, skip_count = self._select_reuse_locked(
            base_key=key, start_frame_index=start_frame_index
        )
        spawned_fresh = False

        if chosen_reader is not None:
            assert chosen_full_key is not None
            self._readers.move_to_end(chosen_full_key)
            for _ in range(skip_count):
                discard = chosen_reader.read_next()
                if discard is None:
                    # The reader died mid-skip; drop it and fall through to
                    # the spawn path below.
                    chosen_reader.close()
                    self._readers.pop(chosen_full_key, None)
                    chosen_reader = None
                    chosen_full_key = None
                    break

        if chosen_reader is None:
            # Make room for a fresh reader under this base_key first, then
            # respect the global cap.
            self._evict_per_key_locked(base_key=key)
            full_key = (*key, self._next_reader_id)
            self._next_reader_id += 1
            chosen_reader = _PersistentFrameReader(
                ffmpeg_executable=ffmpeg_executable,
                media_path=resolved_path,
                fps=fps,
                start_frame_index=start_frame_index,
                width=width,
                height=height,
                extra_video_filters=extra_video_filters,
                hwaccel_args=accel,
            )
            if not chosen_reader.is_alive():
                chosen_reader.close()
                return [], bool(accel)
            self._readers[full_key] = chosen_reader
            self._evict_overflow_locked(except_key=full_key)
            chosen_full_key = full_key
            spawned_fresh = True

        for _ in range(frame_count):
            frame_index = chosen_reader.next_frame_index
            payload = chosen_reader.read_next()
            if payload is None:
                chosen_reader.close()
                if chosen_full_key is not None:
                    self._readers.pop(chosen_full_key, None)
                # Treat "fresh hwaccel reader produced zero frames" as a
                # decoder-unsupported signal. Reuse paths or partial reads
                # do NOT fall back: those typically mean EOF or a transient
                # process exit, not a codec mismatch.
                if spawned_fresh and chosen_reader.used_hwaccel and not results:
                    return [], True
                break
            results.append((frame_index, payload))

        return results, False

    def _select_reuse_locked(
        self, base_key: tuple, start_frame_index: int
    ) -> tuple[tuple | None, _PersistentFrameReader | None, int]:
        """Pick the cheapest reusable reader under ``base_key``.

        Returns ``(full_key, reader, skip_count)``. ``skip_count`` is
        the number of frames to discard from the chosen reader before
        emitting useful payloads (0 for an exact match).
        """

        exact: tuple | None = None
        best: tuple | None = None
        best_gap = self._skip_budget_frames + 1
        for full_key, reader in self._readers.items():
            if full_key[:5] != base_key:
                continue
            if not reader.is_alive():
                continue
            gap = start_frame_index - reader.next_frame_index
            if gap == 0:
                exact = (full_key, reader, 0)
                break
            if 0 < gap <= self._skip_budget_frames and gap < best_gap:
                best = (full_key, reader, gap)
                best_gap = gap
        chosen = exact or best
        if chosen is None:
            return None, None, 0
        return chosen

    def _evict_per_key_locked(self, base_key: tuple) -> None:
        """Drop the LRU reader under ``base_key`` if the per-key cap is full."""

        peers: list[tuple] = [
            full_key for full_key in self._readers if full_key[:5] == base_key
        ]
        if len(peers) < self._max_per_key:
            return
        # OrderedDict iterates oldest-first, so peers[0] is the LRU candidate
        # under this base_key.
        evict_key = peers[0]
        self._readers[evict_key].close()
        self._readers.pop(evict_key, None)

    def _evict_overflow_locked(self, except_key: tuple | None) -> None:
        while len(self._readers) > self._max_active:
            evict_key, evict_reader = next(iter(self._readers.items()))
            if evict_key == except_key:
                self._readers.move_to_end(evict_key)
                continue
            evict_reader.close()
            self._readers.pop(evict_key, None)

    def invalidate(self, media_path: str | None = None) -> None:
        """Close all readers (or just those for ``media_path``) and drop them."""

        with self._lock:
            if media_path is None:
                for reader in self._readers.values():
                    reader.close()
                self._readers.clear()
                return
            try:
                resolved = str(Path(media_path).expanduser().resolve())
            except OSError:
                return
            stale_keys = [key for key in self._readers if key[0] == resolved]
            for key in stale_keys:
                self._readers[key].close()
                self._readers.pop(key, None)

    def close(self) -> None:
        self.invalidate()

    def active_reader_count(self) -> int:
        with self._lock:
            return len(self._readers)
