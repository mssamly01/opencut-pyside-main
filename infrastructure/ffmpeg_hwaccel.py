"""Detect the best ffmpeg ``-hwaccel`` for the current host.

The probe runs ``ffmpeg -hwaccels`` once per ffmpeg binary and caches
the chosen accelerator. Callers should be prepared to fall back to
software decoding per-file: hwaccel availability does NOT imply that
every codec/profile actually decodes successfully on this GPU/driver.
"""

from __future__ import annotations

import logging
import subprocess
from threading import Lock

logger = logging.getLogger(__name__)

# Priority order for hwaccel selection. NVIDIA NVDEC ("cuda") and Apple
# VideoToolbox give the strongest H.264/HEVC decode acceleration on
# their respective platforms; ``d3d11va`` is the most reliable Windows
# accel; ``qsv`` covers Intel integrated GPUs; ``vaapi`` is the Linux
# fallback when no discrete GPU is present.
_HWACCEL_PRIORITY: tuple[str, ...] = ("cuda", "videotoolbox", "d3d11va", "qsv", "vaapi")

_probe_cache: dict[str, str | None] = {}
_probe_lock = Lock()


def probe_hwaccel(ffmpeg_executable: str, *, force: bool = False) -> str | None:
    """Return the best supported ffmpeg hwaccel name, or ``None``.

    Runs ``ffmpeg -hwaccels`` and intersects the reported list with
    :data:`_HWACCEL_PRIORITY`, picking the highest-priority match.
    Cached per ``ffmpeg_executable``.
    """

    with _probe_lock:
        if not force and ffmpeg_executable in _probe_cache:
            return _probe_cache[ffmpeg_executable]

    try:
        result = subprocess.run(
            [ffmpeg_executable, "-hide_banner", "-hwaccels"],
            capture_output=True,
            check=False,
            timeout=2.0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("ffmpeg hwaccel probe failed: %s", exc)
        with _probe_lock:
            _probe_cache[ffmpeg_executable] = None
        return None

    if result.returncode != 0:
        with _probe_lock:
            _probe_cache[ffmpeg_executable] = None
        return None

    listed = {
        line.strip()
        for line in result.stdout.decode("utf-8", errors="ignore").splitlines()
        if line.strip() and not line.startswith("Hardware acceleration")
    }

    chosen: str | None = None
    for candidate in _HWACCEL_PRIORITY:
        if candidate in listed:
            chosen = candidate
            break

    with _probe_lock:
        _probe_cache[ffmpeg_executable] = chosen
    return chosen


def hwaccel_args(name: str | None) -> list[str]:
    """Return ``["-hwaccel", name]`` or ``[]`` if no accel was chosen."""

    if not name:
        return []
    return ["-hwaccel", name]


def _reset_cache_for_tests() -> None:
    with _probe_lock:
        _probe_cache.clear()
