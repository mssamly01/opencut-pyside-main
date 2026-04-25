"""Deterministic-looking, collision-safe identifiers for domain objects.

Every domain entity (``Project``, ``Track``, ``BaseClip``, ``MediaAsset``,
``Keyframe``, ``Transition``…) needs a unique id that survives
serialization and cross-project clipboard paste. We use ``uuid4`` underneath
so we never rely on process-local counters, and expose a small shim that
prepends a short human-readable prefix for readability in save files
(e.g. ``clip_9f3a1c2d4e6f`` instead of a raw UUID).
"""

from __future__ import annotations

import uuid

__all__ = ["generate_id", "generate_raw_id"]

# 12 hex chars = 48 bits of entropy, more than enough to avoid collisions
# within a single project (which rarely contains more than ~10k items).
# Using the full UUID would bloat save files without adding practical value.
_DEFAULT_ENTROPY_CHARS = 12


def generate_raw_id(entropy_chars: int = _DEFAULT_ENTROPY_CHARS) -> str:
    """Return a raw lowercase hex id with ``entropy_chars`` characters."""
    if entropy_chars < 4 or entropy_chars > 32:
        raise ValueError(
            f"entropy_chars must be between 4 and 32, got {entropy_chars}"
        )
    return uuid.uuid4().hex[:entropy_chars]


def generate_id(prefix: str = "", entropy_chars: int = _DEFAULT_ENTROPY_CHARS) -> str:
    """Return an id of the form ``<prefix>_<hex>``.

    ``prefix`` should be a short ASCII slug describing the kind of entity
    ("clip", "track", "kf", "media"). An empty prefix yields a bare hex id.
    """
    raw = generate_raw_id(entropy_chars)
    if not prefix:
        return raw
    if not prefix.isascii() or any(c.isspace() for c in prefix):
        raise ValueError(f"prefix must be ASCII with no whitespace, got {prefix!r}")
    return f"{prefix}_{raw}"
