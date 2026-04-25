from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tempfile import gettempdir

from app.domain.project import Project
from app.services.project_service import ProjectService


class AutosaveService:
    def __init__(
        self,
        project_service: ProjectService | None = None,
        autosave_dir: str | None = None,
        autosave_filename: str = "opencut-pyside-autosave.json",
    ) -> None:
        self._project_service = project_service or ProjectService()
        base_dir = Path(autosave_dir).expanduser().resolve() if autosave_dir else Path(gettempdir()).resolve() / "opencut-pyside"
        self._autosave_path = base_dir / autosave_filename

    def autosave_path(self) -> str:
        return str(self._autosave_path)

    def has_autosave_snapshot(self) -> bool:
        return self._autosave_path.exists() and self._autosave_path.is_file()

    def save_snapshot(self, project: Project) -> str:
        self._autosave_path.parent.mkdir(parents=True, exist_ok=True)
        return self._project_service.save_project(project, str(self._autosave_path))

    def load_snapshot(self) -> Project:
        return self._project_service.load_project(str(self._autosave_path))

    def discard_snapshot(self) -> None:
        if not self.has_autosave_snapshot():
            return
        self._autosave_path.unlink(missing_ok=True)

    def snapshot_modified_at(self) -> datetime | None:
        if not self.has_autosave_snapshot():
            return None
        timestamp = self._autosave_path.stat().st_mtime
        return datetime.fromtimestamp(timestamp)
