"""LUT (.cube) preset registry and validation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Repo-relative directory holding the bundled preset .cube files. Computed
# lazily so the service module imports cheaply at startup.
_PRESETS_DIRNAME = "luts"


@dataclass(frozen=True, slots=True)
class LutPreset:
    """A bundled LUT preset visible in the EffectsPanel dropdown."""

    preset_id: str  # opaque, stable id stored in clip.lut_path (e.g. "preset:cinematic")
    display_name: str  # untranslated source string (Vietnamese), wrapped with tr() at UI layer
    filename: str  # relative to assets/luts/


PRESET_ID_PREFIX = "preset:"

# Order = order shown in the dropdown.
PRESETS: tuple[LutPreset, ...] = (
    LutPreset(preset_id="preset:cinematic", display_name="Điện ảnh", filename="cinematic.cube"),
    LutPreset(preset_id="preset:vintage", display_name="Hoài cổ", filename="vintage.cube"),
    LutPreset(preset_id="preset:black_and_white", display_name="Đen trắng", filename="black_and_white.cube"),
)


def assets_root() -> Path:
    """Return the absolute path to the bundled LUT assets directory."""
    # services/ lives directly under the repo root.
    return Path(__file__).resolve().parent.parent / "assets" / _PRESETS_DIRNAME


def find_preset(preset_id: str) -> LutPreset | None:
    for preset in PRESETS:
        if preset.preset_id == preset_id:
            return preset
    return None


def resolve_lut_path(stored_path: str) -> Path | None:
    """Resolve a stored ``lut_path`` to an existing file on disk.

    ``stored_path`` may be:
      - empty → no LUT applied (returns None)
      - a preset id (``preset:<key>``) → resolved against assets/luts/
      - an absolute filesystem path → returned if it exists
    """
    if not stored_path:
        return None
    if stored_path.startswith(PRESET_ID_PREFIX):
        preset = find_preset(stored_path)
        if preset is None:
            logger.warning("LUT preset %r not found", stored_path)
            return None
        path = assets_root() / preset.filename
        return path if path.is_file() else None
    candidate = Path(stored_path).expanduser()
    if candidate.is_absolute() and candidate.is_file():
        return candidate
    return None


def is_valid_cube_file(path: str | Path) -> bool:
    """Quick structural check: file is readable and declares LUT_3D_SIZE."""
    p = Path(path)
    if not p.is_file():
        return False
    try:
        # Read at most ~4 KiB; the header always appears in the first lines.
        with p.open(encoding="utf-8", errors="ignore") as fh:
            head = fh.read(4096)
    except OSError:
        return False
    for line in head.splitlines():
        token = line.strip().split()
        if len(token) >= 2 and token[0].upper() == "LUT_3D_SIZE":
            try:
                size = int(token[1])
            except ValueError:
                return False
            return 2 <= size <= 256
    return False


def display_label_for_path(stored_path: str) -> str:
    """Best-effort label for a stored lut_path (used by inspector tooltips)."""
    if not stored_path:
        return ""
    if stored_path.startswith(PRESET_ID_PREFIX):
        preset = find_preset(stored_path)
        return preset.display_name if preset else stored_path
    return Path(stored_path).name
