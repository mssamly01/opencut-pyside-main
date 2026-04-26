from __future__ import annotations

from pathlib import Path

from app.controllers.project_controller import ProjectController
from app.controllers.timeline_controller import TimelineController
from app.domain.media_asset import MediaAsset
from app.services.thumbnail_service import ThumbnailService
from app.ui.media_panel.media_item_widget import MediaListWidget
from app.ui.shared.icons import build_icon, build_pixmap, icon_size
from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QAction, QBrush, QColor, QDesktopServices, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

THUMBNAIL_SIZE = QSize(152, 100)


class MediaPanel(QWidget):
    def __init__(
        self,
        project_controller: ProjectController,
        parent: QWidget | None = None,
        thumbnail_service: ThumbnailService | None = None,
        timeline_controller: TimelineController | None = None,
    ) -> None:
        super().__init__(parent)
        self._project_controller = project_controller
        self._thumbnail_service = thumbnail_service or ThumbnailService()
        self._timeline_controller = timeline_controller

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QLabel("Media Library", self)
        header.setStyleSheet("font-weight: 600; color: #e6edf3; padding: 2px 0;")
        layout.addWidget(header)

        self.import_button = QPushButton("  Import Media...", self)
        self.import_button.setIcon(build_icon("import-media"))
        self.import_button.setIconSize(icon_size(16))
        self.import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_button.clicked.connect(self._on_import_clicked)
        layout.addWidget(self.import_button)

        self.media_list = MediaListWidget(self)
        self.media_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.media_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.media_list.setMovement(QListWidget.Movement.Static)
        self.media_list.setSpacing(6)
        self.media_list.setUniformItemSizes(True)
        self.media_list.setWordWrap(True)
        self.media_list.setIconSize(THUMBNAIL_SIZE)
        self.media_list.setGridSize(QSize(THUMBNAIL_SIZE.width() + 18, THUMBNAIL_SIZE.height() + 42))
        self.media_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.media_list.customContextMenuRequested.connect(self._on_context_menu_requested)
        layout.addWidget(self.media_list, 1)

        self._project_controller.project_changed.connect(self._refresh_media_items)
        self._project_controller.media_assets_changed.connect(self._refresh_media_items)
        self._refresh_media_items()

    def open_import_dialog(self) -> None:
        self._on_import_clicked()

    def _on_import_clicked(self) -> None:
        selected_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Import Media Files",
            "",
            "Media Files (*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.mp3 *.wav *.aac *.flac *.ogg *.m4a *.png *.jpg *.jpeg *.bmp *.gif *.webp);;All Files (*.*)",
        )
        if not selected_paths:
            return

        self._project_controller.import_media_files(selected_paths)

    def _refresh_media_items(self) -> None:
        self.media_list.clear()

        project = self._project_controller.active_project()
        if project is None or not project.media_items:
            placeholder = QListWidgetItem("No media imported")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            placeholder.setForeground(Qt.GlobalColor.gray)
            self.media_list.addItem(placeholder)
            return

        project_path = self._project_controller.active_project_path()
        for media_asset in project.media_items:
            item = QListWidgetItem(self._format_short_label(media_asset))
            item.setData(Qt.ItemDataRole.UserRole, media_asset.media_id)
            item.setToolTip(self._format_tooltip(media_asset))
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            item.setSizeHint(QSize(THUMBNAIL_SIZE.width() + 16, THUMBNAIL_SIZE.height() + 40))
            item.setIcon(self._build_media_icon(media_asset, project_path))
            self.media_list.addItem(item)

    def _build_media_icon(self, media_asset: MediaAsset, project_path: str | None) -> QIcon:
        media_type = (media_asset.media_type or "").lower()

        if media_type in ("video", "image"):
            try:
                thumbnail_bytes = self._thumbnail_service.get_media_asset_thumbnail_bytes(
                    media_asset,
                    project_path=project_path,
                    source_time=0.0,
                )
            except Exception:
                thumbnail_bytes = None
            if thumbnail_bytes:
                pixmap = QPixmap()
                if pixmap.loadFromData(thumbnail_bytes):
                    canvas = QPixmap(THUMBNAIL_SIZE)
                    canvas.fill(Qt.GlobalColor.transparent)
                    painter = QPainter(canvas)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                    painter.setBrush(QBrush(QColor("#0f1217")))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawRoundedRect(canvas.rect(), 6, 6)
                    scaled = pixmap.scaled(
                        THUMBNAIL_SIZE,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    draw_x = (THUMBNAIL_SIZE.width() - scaled.width()) // 2
                    draw_y = (THUMBNAIL_SIZE.height() - scaled.height()) // 2
                    painter.drawPixmap(draw_x, draw_y, scaled)
                    painter.end()
                    return QIcon(canvas)

        placeholder_color = {
            "video": "#3f6bb8",
            "image": "#a85fb8",
            "audio": "#3a9b6f",
        }.get(media_type, "#c48a38")
        glyph = {
            "video": "import-media",
            "image": "import-media",
            "audio": "volume",
        }.get(media_type, "import-subtitle")

        placeholder = QPixmap(THUMBNAIL_SIZE)
        placeholder.fill(Qt.GlobalColor.transparent)

        painter = QPainter(placeholder)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QBrush(QColor(placeholder_color)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(placeholder.rect(), 6, 6)
        glyph_pixmap = build_pixmap(glyph, 40, "#ffffff")
        painter.drawPixmap(
            (THUMBNAIL_SIZE.width() - glyph_pixmap.width()) // 2,
            (THUMBNAIL_SIZE.height() - glyph_pixmap.height()) // 2,
            glyph_pixmap,
        )
        painter.end()
        return QIcon(placeholder)

    @staticmethod
    def _format_short_label(media_asset: MediaAsset) -> str:
        file_name = Path(media_asset.file_path).name if media_asset.file_path else media_asset.name
        if len(file_name) <= 22:
            return file_name
        return file_name[:19] + "..."

    @staticmethod
    def _format_tooltip(media_asset: MediaAsset) -> str:
        file_name = Path(media_asset.file_path).name if media_asset.file_path else media_asset.name
        parts = [
            file_name,
            f"Type: {media_asset.media_type}",
        ]
        if media_asset.duration_seconds:
            parts.append(f"Duration: {media_asset.duration_seconds:.2f}s")
        if media_asset.file_size_bytes:
            parts.append(f"Size: {media_asset.file_size_bytes / (1024 * 1024):.1f} MB")
        return "\n".join(parts)

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
