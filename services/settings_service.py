from __future__ import annotations

import json
from pathlib import Path


class SettingsService:
    def __init__(
        self,
        settings_path: str | None = None,
        max_recent_projects: int = 10,
    ) -> None:
        default_path = Path.home() / ".opencut-pyside" / "settings.json"
        self._settings_path = Path(settings_path).expanduser() if settings_path else default_path
        self._max_recent_projects = max(1, max_recent_projects)
        self._settings = {
            "last_opened_project_path": None,
            "last_export_directory": None,
            "recent_project_paths": [],
            "subtitle_extractor_model_dir": None,
        }
        self._load_from_disk()

    def settings_path(self) -> str:
        return str(self._settings_path)

    def last_opened_project_path(self) -> str | None:
        value = self._settings.get("last_opened_project_path")
        return value if isinstance(value, str) and value.strip() else None

    def last_export_directory(self) -> str | None:
        value = self._settings.get("last_export_directory")
        return value if isinstance(value, str) and value.strip() else None

    def recent_project_paths(self) -> list[str]:
        value = self._settings.get("recent_project_paths")
        if not isinstance(value, list):
            return []
        return [path for path in value if isinstance(path, str) and path.strip()]

    def subtitle_extractor_model_dir(self) -> str | None:
        value = self._settings.get("subtitle_extractor_model_dir")
        return value if isinstance(value, str) and value.strip() else None

    def set_subtitle_extractor_model_dir(self, model_dir: str | None) -> None:
        normalized = self._normalize_path(model_dir) if model_dir else None
        self._settings["subtitle_extractor_model_dir"] = normalized
        self._save_to_disk()

    def record_project_opened(self, project_path: str) -> None:
        normalized_path = self._normalize_path(project_path)
        if normalized_path is None:
            return

        self._settings["last_opened_project_path"] = normalized_path
        self._settings["recent_project_paths"] = self._updated_recent_paths(normalized_path)
        self._save_to_disk()

    def record_project_saved(self, project_path: str) -> None:
        self.record_project_opened(project_path)

    def record_export_output(self, output_path: str) -> None:
        normalized_path = self._normalize_path(output_path)
        if normalized_path is None:
            return

        export_directory = str(Path(normalized_path).parent)
        self._settings["last_export_directory"] = export_directory
        self._save_to_disk()

    def _updated_recent_paths(self, newest_path: str) -> list[str]:
        existing_paths = self.recent_project_paths()
        filtered_paths = [path for path in existing_paths if path.casefold() != newest_path.casefold()]
        return [newest_path, *filtered_paths][: self._max_recent_projects]

    def _load_from_disk(self) -> None:
        if not self._settings_path.exists() or not self._settings_path.is_file():
            return

        try:
            payload = json.loads(self._settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return

        if not isinstance(payload, dict):
            return

        for key in (
            "last_opened_project_path",
            "last_export_directory",
            "recent_project_paths",
            "subtitle_extractor_model_dir",
        ):
            if key in payload:
                self._settings[key] = payload[key]

        self._settings["recent_project_paths"] = self.recent_project_paths()[: self._max_recent_projects]
        self._settings["last_opened_project_path"] = self.last_opened_project_path()
        self._settings["last_export_directory"] = self.last_export_directory()

    def _save_to_disk(self) -> None:
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        self._settings_path.write_text(
            json.dumps(self._settings, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

    @staticmethod
    def _normalize_path(file_path: str | None) -> str | None:
        if file_path is None or not file_path.strip():
            return None
        return str(Path(file_path).expanduser().resolve())
