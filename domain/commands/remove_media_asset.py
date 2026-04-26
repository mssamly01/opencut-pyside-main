from __future__ import annotations

from app.domain.commands.base_command import BaseCommand
from app.domain.media_asset import MediaAsset
from app.domain.project import Project


class RemoveMediaAssetCommand(BaseCommand):
    """Remove a MediaAsset from Project.media_items, restoring it on undo at the same index."""

    def __init__(self, project: Project, media_id: str) -> None:
        self._project = project
        self._media_id = media_id
        self._removed_asset: MediaAsset | None = None
        self._removed_index: int | None = None

    def execute(self) -> None:
        for index, asset in enumerate(self._project.media_items):
            if asset.media_id == self._media_id:
                if self._removed_asset is None:
                    self._removed_asset = asset
                    self._removed_index = index
                self._project.media_items.pop(index)
                return
        raise ValueError(f"Media asset '{self._media_id}' not found in project")

    def undo(self) -> None:
        if self._removed_asset is None or self._removed_index is None:
            raise RuntimeError("Cannot undo before command execution")
        insert_index = min(self._removed_index, len(self._project.media_items))
        self._project.media_items.insert(insert_index, self._removed_asset)
