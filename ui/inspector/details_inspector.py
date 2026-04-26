from __future__ import annotations

from app.controllers.app_controller import AppController
from app.domain.clips.audio_clip import AudioClip
from app.domain.clips.base_clip import BaseClip
from app.domain.clips.image_clip import ImageClip
from app.domain.clips.text_clip import TextClip
from app.domain.clips.video_clip import VideoClip
from app.domain.media_asset import MediaAsset
from app.domain.project import Project
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class DetailsInspector(QWidget):
    """Readonly key-value details panel."""

    def __init__(self, app_controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app_controller = app_controller

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(0)

        title = QLabel(self.tr("Chi tiết"), self)
        title.setObjectName("details_title")
        layout.addWidget(title)

        separator = QFrame(self)
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setObjectName("details_separator")
        layout.addWidget(separator)
        layout.addSpacing(8)

        self._rows_container = QWidget(self)
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(6)
        layout.addWidget(self._rows_container)
        layout.addStretch(1)

        self._app_controller.project_controller.project_changed.connect(self._refresh)
        self._app_controller.timeline_controller.timeline_edited.connect(self._refresh)
        self._app_controller.selection_controller.selection_changed.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        self._clear_rows()
        project = self._app_controller.project_controller.active_project()
        clip = self._selected_clip(project)
        if clip is not None:
            self._populate_clip(clip, project)
            return
        if project is not None:
            self._populate_project(project)
            return
        self._add_row(self.tr("Trạng thái"), self.tr("Chưa mở dự án"))

    def _populate_project(self, project: Project) -> None:
        self._add_row(self.tr("Dự án"), project.name or self.tr("Không có tiêu đề"))
        self._add_row(self.tr("Độ phân giải"), f"{project.width} x {project.height}")
        self._add_row(self.tr("FPS"), f"{project.fps:g}")
        self._add_row(self.tr("Thời lượng"), _format_duration(project.timeline.total_duration()))
        self._add_row(self.tr("Số track"), str(len(project.timeline.tracks)))
        self._add_row(self.tr("Phương tiện"), str(len(project.media_items)))

    def _populate_clip(self, clip: BaseClip, project: Project | None) -> None:
        self._add_row(self.tr("Tên"), clip.name or "-")
        self._add_row(self.tr("Loại"), _clip_type_label(clip))
        self._add_row(self.tr("Điểm bắt đầu"), _format_duration(clip.timeline_start))
        self._add_row(self.tr("Thời lượng clip"), _format_duration(clip.duration))

        asset = self._media_asset_for_clip(clip, project)
        if asset is not None:
            self._add_row(self.tr("Đường dẫn"), asset.file_path)
            if asset.width is not None and asset.height is not None:
                self._add_row(self.tr("Độ phân giải"), f"{asset.width} x {asset.height}")
            if asset.fps is not None:
                self._add_row(self.tr("FPS"), f"{asset.fps:.2f}")
            if asset.video_codec:
                self._add_row(self.tr("Codec video"), asset.video_codec)
            if asset.audio_codec:
                self._add_row(self.tr("Codec âm thanh"), asset.audio_codec)
            if asset.sample_rate is not None:
                self._add_row(self.tr("Tần số mẫu"), f"{asset.sample_rate} Hz")
            if asset.duration_seconds is not None:
                self._add_row(self.tr("Thời lượng nguồn"), _format_duration(asset.duration_seconds))
            if asset.file_size_bytes is not None:
                self._add_row(self.tr("Kích thước"), _format_file_size(asset.file_size_bytes))
                bitrate = _estimate_bitrate(asset.file_size_bytes, asset.duration_seconds)
                if bitrate is not None:
                    self._add_row(self.tr("Bitrate"), bitrate)

        if isinstance(clip, TextClip):
            self._add_row(self.tr("Nội dung"), (clip.content or "").strip() or "-")
            self._add_row(self.tr("Cỡ chữ"), str(clip.font_size))
            self._add_row(self.tr("Màu sắc"), clip.color)

    def _media_asset_for_clip(self, clip: BaseClip, project: Project | None) -> MediaAsset | None:
        if project is None:
            return None
        if not isinstance(clip, (VideoClip, ImageClip, AudioClip)):
            return None
        media_id = getattr(clip, "media_id", None)
        if not media_id:
            return None
        for asset in project.media_items:
            if asset.media_id == media_id:
                return asset
        return None

    def _add_row(self, key: str, value: str) -> None:
        row = QWidget(self._rows_container)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        key_label = QLabel(key, row)
        key_label.setObjectName("details_key")
        key_label.setFixedWidth(110)
        key_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        row_layout.addWidget(key_label)

        value_label = QLabel(value or "-", row)
        value_label.setObjectName("details_value")
        value_label.setWordWrap(True)
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row_layout.addWidget(value_label, 1)

        self._rows_layout.addWidget(row)

    def _clear_rows(self) -> None:
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            child = item.widget()
            if child is None:
                continue
            child.setParent(None)
            child.deleteLater()

    def _selected_clip(self, project: Project | None) -> BaseClip | None:
        if project is None:
            return None
        clip_id = self._app_controller.selection_controller.selected_clip_id()
        if clip_id is None:
            return None
        for track in project.timeline.tracks:
            for clip in track.clips:
                if clip.clip_id == clip_id:
                    return clip
        return None


def _clip_type_label(clip: BaseClip) -> str:
    translate = QCoreApplication.translate
    if isinstance(clip, VideoClip):
        return translate("DetailsInspector", "Video")
    if isinstance(clip, AudioClip):
        return translate("DetailsInspector", "Âm thanh")
    if isinstance(clip, ImageClip):
        return translate("DetailsInspector", "Hình ảnh")
    if isinstance(clip, TextClip):
        return translate("DetailsInspector", "Văn bản")
    return clip.__class__.__name__


def _format_duration(seconds: float) -> str:
    value = max(0.0, float(seconds))
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    secs = value - hours * 3600 - minutes * 60
    return f"{hours:02d}:{minutes:02d}:{secs:05.2f}"


def _format_file_size(size_bytes: int) -> str:
    value = float(max(0, int(size_bytes)))
    units = ["B", "KB", "MB", "GB", "TB"]
    unit = units[0]
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            break
        value /= 1024.0
    if unit == "B":
        return f"{int(value)} {unit}"
    return f"{value:.2f} {unit}"


def _estimate_bitrate(file_size_bytes: int, duration_seconds: float | None) -> str | None:
    if duration_seconds is None or duration_seconds <= 1e-6:
        return None
    bits_per_second = (float(file_size_bytes) * 8.0) / float(duration_seconds)
    kbps = bits_per_second / 1000.0
    return f"{kbps:.0f} kbps"
