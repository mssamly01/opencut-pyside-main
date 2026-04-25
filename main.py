from __future__ import annotations

import sys
import types
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QTimer

# Support running both `python -m app.main` and `python app/main.py`.
if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    if "app" not in sys.modules:
        app_package = types.ModuleType("app")
        app_package.__path__ = [str(project_root)]
        sys.modules["app"] = app_package

from app.bootstrap import build_main_window, create_application
from app.infrastructure.logging_config import configure_logging

_MAIN_WINDOW_REF: dict[str, object] = {}


def _collect_crash_context() -> dict[str, str]:
    """Best-effort context metadata for crash reports."""
    window = _MAIN_WINDOW_REF.get("window")
    if window is None:
        return {"main_window": "not initialized"}

    try:
        controller = getattr(window, "_app_controller", None)
        if controller is None:
            return {"main_window": "no controller"}

        settings = getattr(controller, "settings_service", None)
        project_controller = getattr(controller, "project_controller", None)
        project = None
        if project_controller is not None:
            project = getattr(project_controller, "active_project", lambda: None)()

        return {
            "active_project_name": getattr(project, "name", "<none>") if project else "<none>",
            "track_count": str(len(project.timeline.tracks)) if project else "0",
            "last_opened_path": (
                settings.last_opened_project_path() if settings is not None else "<none>"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {"context_collection_error": repr(exc)}


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    cli_args = list(sys.argv[1:] if argv is None else argv)
    smoke_test = "--smoke-test" in cli_args
    simulate_crash = "--simulate-crash" in cli_args

    from app.infrastructure.crash_reporter import CrashReporter

    crash_reporter = CrashReporter(context_provider=_collect_crash_context)
    crash_reporter.install()

    if simulate_crash:
        try:
            raise RuntimeError("Simulated crash for diagnostics")
        except RuntimeError:
            crash_reporter.write_report(*sys.exc_info())
        return 0

    qt_args = [
        sys.argv[0],
        *[arg for arg in cli_args if arg not in {"--smoke-test", "--simulate-crash"}],
    ]
    application = create_application(qt_args)
    main_window = build_main_window()
    main_window.setProperty("opencut_main_window", True)
    _MAIN_WINDOW_REF["window"] = main_window
    main_window.show()

    if smoke_test:
        QTimer.singleShot(0, application.quit)

    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
