from __future__ import annotations

from pathlib import Path

from app.domain.project import Project, build_demo_project, build_empty_project
from app.services.media_service import MediaService
from app.services.project_service import ProjectService
from PySide6.QtCore import QObject, Signal


class ProjectController(QObject):
    project_changed = Signal()
    project_modified = Signal()

    def __init__(
        self,
        parent: QObject | None = None,
        media_service: MediaService | None = None,
        project_service: ProjectService | None = None,
    ) -> None:
        super().__init__(parent)
        self._active_project: Project | None = None
        self._active_project_path: str | None = None
        self._media_service = media_service or MediaService()
        self._project_service = project_service or ProjectService()

    def set_active_project(self, project: Project | None, project_path: str | None = None) -> None:
        normalized_path = self._normalize_project_path(project_path)
        if project is self._active_project and normalized_path == self._active_project_path:
            return
        self._active_project = project
        self._active_project_path = normalized_path
        self.project_changed.emit()

    def active_project(self) -> Project | None:
        return self._active_project

    def active_project_path(self) -> str | None:
        return self._active_project_path

    def load_empty_project(self) -> Project:
        project = build_empty_project()
        self.set_active_project(project, project_path=None)
        return project

    def load_demo_project(self) -> Project:
        project = build_demo_project()
        self.set_active_project(project, project_path=None)
        return project

    def import_media_files(self, file_paths: list[str]) -> list[str]:
        project = self._active_project
        if project is None:
            return []

        existing_paths = {self._path_key(asset.file_path) for asset in project.media_items}
        imported_assets = []
        for asset in self._media_service.import_files(file_paths):
            path_key = self._path_key(asset.file_path)
            if path_key in existing_paths:
                continue
            existing_paths.add(path_key)
            imported_assets.append(asset)

        if not imported_assets:
            return []

        project.media_items.extend(imported_assets)
        self.project_changed.emit()
        self.project_modified.emit()
        return [asset.media_id for asset in imported_assets]

    def save_active_project(self, file_path: str | None = None) -> str | None:
        project = self._active_project
        if project is None:
            return None

        target_path = self._normalize_project_path(file_path) or self._active_project_path
        if target_path is None:
            return None

        saved_path = self._project_service.save_project(project, target_path)
        self._active_project_path = self._normalize_project_path(saved_path)
        return self._active_project_path

    def load_project_from_file(self, file_path: str) -> Project:
        project = self._project_service.load_project(file_path)
        self.set_active_project(project, project_path=file_path)
        return project

    def set_project_resolution(self, width: int, height: int) -> bool:
        project = self._active_project
        if project is None:
            return False

        new_width = max(16, int(width))
        new_height = max(16, int(height))
        if project.width == new_width and project.height == new_height:
            return False

        project.width = new_width
        project.height = new_height
        self.project_changed.emit()
        self.project_modified.emit()
        return True

    @staticmethod
    def _path_key(file_path: str) -> str:
        return str(Path(file_path)).casefold()

    @staticmethod
    def _normalize_project_path(file_path: str | None) -> str | None:
        if file_path is None or not file_path.strip():
            return None
        return str(Path(file_path).expanduser().resolve())
