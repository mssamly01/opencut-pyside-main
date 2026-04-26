from __future__ import annotations

from pathlib import Path

from app.controllers.project_controller import ProjectController
from app.controllers.timeline_controller import TimelineController
from app.domain.media_asset import MediaAsset
from app.services.waveform_loader import WaveformLoader
from app.ui.media_panel.media_item_widget import MediaListWidget
from app.ui.sidebar.audio_row_widget import AudioRowWidget
from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_AUDIO_FILTER = "Audio Files (*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus);;All Files (*.*)"
_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}


class AudioPanel(QWidget):
    """Filtered library panel for audio-only assets."""

    def __init__(
        self,
        project_controller: ProjectController,
        waveform_loader: WaveformLoader | None = None,
        timeline_controller: TimelineController | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._project_controller = project_controller
        self._waveform_loader = waveform_loader
        self._timeline_controller = timeline_controller

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
        self.media_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.media_list.customContextMenuRequested.connect(self._on_context_menu_requested)
        layout.addWidget(self.media_list, 1)

        self._project_controller.project_changed.connect(self._refresh_media_items)
        self._project_controller.media_assets_changed.connect(self._refresh_media_items)
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
            item = QListWidgetItem(self.media_list)
            item.setData(Qt.ItemDataRole.UserRole, media_asset.media_id)
            item.setToolTip(AudioRowWidget.format_tooltip(media_asset))
            item.setSizeHint(QSize(0, 32))
            row_widget = AudioRowWidget(
                media_asset=media_asset,
                waveform_loader=self._waveform_loader,
                project_path=self._project_controller.active_project_path(),
                parent=self.media_list,
            )
            self.media_list.setItemWidget(item, row_widget)
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

    def _on_context_menu_requested(self, position) -> None:
        item = self.media_list.itemAt(position)
        if item is None:
            return

        media_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(media_id, str):
            return

        media_asset = self._find_media_asset(media_id)
        if media_asset is None:
            return

        menu = QMenu(self.media_list)
        reveal_action = QAction("Reveal in Folder", menu)
        copy_path_action = QAction("Copy File Path", menu)
        menu.addAction(reveal_action)
        menu.addAction(copy_path_action)

        remove_action: QAction | None = None
        if self._timeline_controller is not None:
            menu.addSeparator()
            remove_action = QAction("Remove from Project", menu)
            menu.addAction(remove_action)

        triggered = menu.exec(self.media_list.viewport().mapToGlobal(position))
        if triggered == reveal_action:
            self._reveal_in_folder(media_asset.file_path)
        elif triggered == copy_path_action:
            self._copy_file_path(media_asset.file_path)
        elif remove_action is not None and triggered == remove_action:
            self._remove_media_asset(media_asset)

    def _find_media_asset(self, media_id: str) -> MediaAsset | None:
        project = self._project_controller.active_project()
        if project is None:
            return None
        for media_asset in project.media_items:
            if media_asset.media_id == media_id:
                return media_asset
        return None

    def _resolve_media_path(self, file_path: str) -> Path:
        path = Path(file_path).expanduser()
        if path.is_absolute():
            return path.resolve()
        project_path = self._project_controller.active_project_path()
        if project_path is not None:
            return (Path(project_path).resolve().parent / path).resolve()
        return path.resolve()

    def _reveal_in_folder(self, file_path: str) -> None:
        resolved = self._resolve_media_path(file_path)
        if resolved.exists():
            target = resolved if resolved.is_dir() else resolved.parent
        else:
            target = resolved.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    @staticmethod
    def _copy_file_path(file_path: str) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(file_path)

    def _remove_media_asset(self, media_asset: MediaAsset) -> None:
        timeline_controller = self._timeline_controller
        if timeline_controller is None:
            return
        clip_count = len(timeline_controller.clips_using_media(media_asset.media_id))
        display_name = media_asset.name or Path(media_asset.file_path).name
        if clip_count > 0:
            message = (
                f"Có {clip_count} clip đang dùng \"{display_name}\". "
                "Xóa asset sẽ xóa luôn các clip này (có thể Undo). Tiếp tục?"
            )
        else:
            message = f"Xóa \"{display_name}\" khỏi project?"
        reply = QMessageBox.question(
            self,
            "Xóa khỏi project",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        timeline_controller.remove_media(media_asset.media_id)
