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


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    cli_args = list(sys.argv[1:] if argv is None else argv)
    smoke_test = "--smoke-test" in cli_args

    qt_args = [sys.argv[0], *[arg for arg in cli_args if arg != "--smoke-test"]]
    application = create_application(qt_args)
    main_window = build_main_window()
    main_window.show()

    if smoke_test:
        QTimer.singleShot(0, application.quit)

    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
