from __future__ import annotations

from pathlib import Path

from app.controllers.project_controller import ProjectController
from app.domain.media_asset import MediaAsset
from app.services.thumbnail_service import ThumbnailService
from app.ui.media_panel.media_item_widget import MediaListWidget
from app.ui.shared.icons import build_icon, build_pixmap, icon_size
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
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
    ) -> None:
        super().__init__(parent)
        self._project_controller = project_controller
        self._thumbnail_service = thumbnail_service or ThumbnailService()

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
        layout.addWidget(self.media_list, 1)

        self._project_controller.project_changed.connect(self._refresh_media_items)
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
