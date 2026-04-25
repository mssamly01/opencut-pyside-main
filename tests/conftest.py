"""Pytest bootstrap.

The repository is laid out so that the folder itself is the importable
``app`` package (``python -m app.main`` works when the *parent* directory
is on ``sys.path``). Tests expect the same import path, so we register the
repository root as the ``app`` package directly via ``importlib`` — this
works uniformly on Linux, macOS, and Windows without requiring symlink
permissions (which are not granted by default on Windows).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _ensure_app_import_path() -> None:
    if "app" in sys.modules:
        return

    package_init = REPO_ROOT / "__init__.py"
    if not package_init.exists():
        raise RuntimeError(
            f"Expected an __init__.py at {package_init} so the repository root "
            "can be loaded as the 'app' package."
        )

    spec = importlib.util.spec_from_file_location(
        "app",
        package_init,
        submodule_search_locations=[str(REPO_ROOT)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to build an importlib spec for the 'app' package.")

    module = importlib.util.module_from_spec(spec)
    sys.modules["app"] = module
    spec.loader.exec_module(module)


def _ensure_offscreen_qt() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


_ensure_offscreen_qt()
_ensure_app_import_path()
