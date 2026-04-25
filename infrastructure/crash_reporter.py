"""Crash reporter based on sys.excepthook.

Writes crash details to ~/.opencut-pyside/crash/<timestamp>.log
"""

from __future__ import annotations

import datetime as _dt
import logging
import platform
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from types import TracebackType

logger = logging.getLogger(__name__)

_DEFAULT_CRASH_DIR = Path.home() / ".opencut-pyside" / "crash"


class CrashReporter:
    def __init__(
        self,
        crash_dir: Path | None = None,
        context_provider: Callable[[], dict] | None = None,
    ) -> None:
        self._crash_dir = (crash_dir or _DEFAULT_CRASH_DIR).expanduser()
        self._context_provider = context_provider
        self._previous_excepthook = sys.excepthook
        self._installed = False

    def install(self) -> None:
        if self._installed:
            return
        self._previous_excepthook = sys.excepthook
        sys.excepthook = self._handle_exception
        self._installed = True

    def uninstall(self) -> None:
        if not self._installed:
            return
        sys.excepthook = self._previous_excepthook
        self._installed = False

    def write_report(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> Path | None:
        try:
            self._crash_dir.mkdir(parents=True, exist_ok=True)
            timestamp = _dt.datetime.now().strftime("%Y%m%dT%H%M%S")
            report_path = self._crash_dir / f"{timestamp}.log"

            traceback_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            context = ""
            if self._context_provider is not None:
                try:
                    context_dict = self._context_provider() or {}
                    context = "\n".join(f"{key}: {value}" for key, value in context_dict.items())
                except Exception as exc:  # noqa: BLE001
                    context = f"<context provider failed: {exc!r}>"

            payload = (
                "=== OpenCut crash report ===\n"
                f"timestamp: {_dt.datetime.now().isoformat()}\n"
                f"python: {sys.version}\n"
                f"platform: {platform.platform()}\n"
                f"\n--- Context ---\n{context}\n"
                f"\n--- Traceback ---\n{traceback_text}\n"
            )
            report_path.write_text(payload, encoding="utf-8")
            return report_path
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to write crash report: %s", exc)
            return None

    def _handle_exception(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        report_path = self.write_report(exc_type, exc_value, exc_tb)
        if report_path is not None:
            logger.error("Crash report written: %s", report_path)

        if self._previous_excepthook is not None:
            self._previous_excepthook(exc_type, exc_value, exc_tb)
