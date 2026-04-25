"""Install ``QTranslator`` instances on a ``QApplication``.

The editor's default UI language is Vietnamese. English is provided as a
translation that the user can select at runtime (via ``OPENCUT_LANG`` for
now — a proper settings store comes in Sprint 1–2 of ROADMAP M0).

Translation files live under ``i18n/`` at the repo root:

* ``opencut_vi.ts`` / ``opencut_vi.qm`` — Vietnamese (source language).
* ``opencut_en.ts`` / ``opencut_en.qm`` — English.

If a compiled ``.qm`` is missing (e.g. during local dev before anyone has
run ``scripts/update_translations.sh``) the function is a no-op — the UI
falls back to the literal string passed to ``self.tr(...)``, which is the
Vietnamese source text.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QLocale, QTranslator
from PySide6.QtWidgets import QApplication

__all__ = ["DEFAULT_LANGUAGE", "resolve_language", "install_translators"]

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "vi"
SUPPORTED_LANGUAGES = ("vi", "en")


def _repo_root() -> Path:
    # Inside a PyInstaller bundle the ``app`` package is packaged under
    # ``<_MEIPASS>/app/`` (see packaging/opencut-pyside.spec) but bundled
    # data files like ``i18n/*.qm`` are placed at ``<_MEIPASS>/i18n/``.
    # Walking up from ``__file__`` would therefore land in the wrong
    # place — use ``sys._MEIPASS`` in frozen builds so callers resolve
    # the bundle root where the data lives.
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
    # translation_manager.py lives at <repo>/infrastructure/.
    return Path(__file__).resolve().parent.parent


def resolve_language(explicit: str | None = None) -> str:
    """Decide which UI language to load.

    Priority (highest first):

    1. ``explicit`` argument passed in by the caller.
    2. ``OPENCUT_LANG`` environment variable (handy for dev / CI).
    3. The system locale — used only if it matches a supported language.
    4. :data:`DEFAULT_LANGUAGE` (``"vi"``).
    """
    if explicit:
        return _normalise(explicit)
    env = os.environ.get("OPENCUT_LANG")
    if env:
        return _normalise(env)
    # For the system locale we must NOT run through ``_normalise`` (which
    # itself falls back to DEFAULT_LANGUAGE for anything unsupported) —
    # otherwise the membership guard would always succeed and the final
    # ``return DEFAULT_LANGUAGE`` below would be dead code. Instead we only
    # reshape the string and check membership directly, so unknown system
    # locales fall through to step 4.
    system = QLocale.system().name().split("_", 1)[0].strip().lower()
    if system in SUPPORTED_LANGUAGES:
        return system
    return DEFAULT_LANGUAGE


def _normalise(language: str) -> str:
    language = language.strip().lower().replace("-", "_").split("_", 1)[0]
    if language not in SUPPORTED_LANGUAGES:
        return DEFAULT_LANGUAGE
    return language


def install_translators(
    app: QApplication,
    language: str | None = None,
    i18n_dir: Path | None = None,
) -> list[QTranslator]:
    """Load and install translators for ``language`` on ``app``.

    Returns the list of installed translators so the caller can retain a
    reference (Qt otherwise garbage-collects them).
    """
    resolved = resolve_language(language)
    directory = i18n_dir or (_repo_root() / "i18n")
    installed: list[QTranslator] = []

    qm_file = directory / f"opencut_{resolved}.qm"
    if qm_file.is_file():
        translator = QTranslator(app)
        if translator.load(str(qm_file)):
            app.installTranslator(translator)
            installed.append(translator)
            logger.info("Loaded UI translation %s (%s)", resolved, qm_file)
        else:
            logger.warning("Failed to load translation file %s", qm_file)
    elif resolved != DEFAULT_LANGUAGE:
        logger.info(
            "No translation file for %s; falling back to source strings (%s)",
            resolved,
            DEFAULT_LANGUAGE,
        )

    return installed
