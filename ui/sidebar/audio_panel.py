from __future__ import annotations

from pathlib import Path

from app.controllers.project_controller import ProjectController
from app.domain.media_asset import MediaAsset
from app.ui.media_panel.media_item_widget import MediaListWidget
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QLabel, QListWidgetItem, QPushButton, QVBoxLayout, QWidget

_AUDIO_FILTER = "Audio Files (*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus);;All Files (*.*)"
_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}


class AudioPanel(QWidget):
    """Filtered library panel for audio-only assets."""

    def __init__(self, project_controller: ProjectController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project_controller = project_controller

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QLabel("Audio", self)
        header.setStyleSheet("font-weight: 600; color: #e6edf3; padding: 2px 0;")
        layout.addWidget(header)

        self.import_button = QPushButton("Import Audio...", self)
        self.import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_button.clicked.connect(self._on_import_clicked)
        layout.addWidget(self.import_button)

        self.media_list = MediaListWidget(self)
        self.media_list.setAlternatingRowColors(True)
        self.media_list.setWordWrap(True)
        layout.addWidget(self.media_list, 1)

        self._project_controller.project_changed.connect(self._refresh_media_items)
        self._refresh_media_items()

    def _on_import_clicked(self) -> None:
        selected_paths, _ = QFileDialog.getOpenFileNames(self, "Import Audio Files", "", _AUDIO_FILTER)
        if not selected_paths:
            return
        self._project_controller.import_media_files(selected_paths)

    def _refresh_media_items(self) -> None:
        self.media_list.clear()
        project = self._project_controller.active_project()
        if project is None:
            return

        has_items = False
        for media_asset in project.media_items:
            if not self._is_audio(media_asset):
                continue
            label = media_asset.name or Path(media_asset.file_path).name
            item = QListWidgetItem(label, self.media_list)
            item.setData(Qt.ItemDataRole.UserRole, media_asset.media_id)
            item.setToolTip(media_asset.file_path)
            has_items = True

        if has_items:
            return

        placeholder = QListWidgetItem("No audio imported", self.media_list)
        placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
        placeholder.setForeground(Qt.GlobalColor.gray)

    @staticmethod
    def _is_audio(asset: MediaAsset) -> bool:
        if (asset.media_type or "").lower() == "audio":
            return True
        return Path(asset.file_path).suffix.lower() in _AUDIO_EXTS
