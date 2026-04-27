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
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget


class DetailsInspector(QWidget):
    """Single-page details panel."""

    def __init__(self, app_controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app_controller = app_controller
        self._subtitle_rows: list[tuple[str, int]] = []
        self._subtitle_list_refreshing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(0)

        self._rows_container = QWidget(self)
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(8)
        layout.addWidget(self._rows_container)

        layout.addSpacing(10)
        self._subtitle_title = QLabel(self.tr("All Subtitle Lines"), self)
        self._subtitle_title.setObjectName("details_subtitle_title")
        self._subtitle_title.setVisible(False)
        layout.addWidget(self._subtitle_title)

        self._subtitle_list = QListWidget(self)
        self._subtitle_list.setAlternatingRowColors(True)
        self._subtitle_list.setWordWrap(True)
        self._subtitle_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._subtitle_list.currentRowChanged.connect(self._on_subtitle_row_changed)
        self._subtitle_list.setVisible(False)
        layout.addWidget(self._subtitle_list)

        layout.addStretch(1)

        self._app_controller.project_controller.project_changed.connect(self._refresh)
        self._app_controller.timeline_controller.timeline_edited.connect(self._refresh)
        self._app_controller.selection_controller.selection_changed.connect(self._refresh)
        self._app_controller.subtitle_selection_changed.connect(self._refresh)
        self._app_controller.subtitle_library_changed.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        self._clear_rows()
        self._set_subtitle_lines_visible(False)
        self._subtitle_rows = []
        self._subtitle_list.clear()

        project = self._app_controller.project_controller.active_project()
        subtitle_segment = self._app_controller.selected_subtitle_segment()
        if subtitle_segment is not None:
            self._populate_subtitle_segment(subtitle_segment)
            self._populate_subtitle_lines(
                entry_id=subtitle_segment.entry_id,
                selected_segment_index=subtitle_segment.segment_index,
            )
            return

        clip = self._selected_clip(project)
        if clip is not None:
            self._populate_clip(clip, project)
            return

        if project is not None:
            self._populate_project(project)
            return

        self._add_row(self.tr("Status"), self.tr("No project opened"))

    def _populate_project(self, project: Project) -> None:
        self._add_row(self.tr("Project"), project.name or self.tr("Untitled"))
        self._add_row(self.tr("Resolution"), f"{project.width} x {project.height}")
        self._add_row(self.tr("FPS"), f"{project.fps:g}")
        self._add_row(self.tr("Duration"), _format_duration(project.timeline.total_duration()))
        self._add_row(self.tr("Tracks"), str(len(project.timeline.tracks)))
        self._add_row(self.tr("Assets"), str(len(project.media_items)))

    def _populate_clip(self, clip: BaseClip, project: Project | None) -> None:
        self._add_row(self.tr("Name"), clip.name or "-")
        self._add_row(self.tr("Type"), _clip_type_label(clip))
        self._add_row(self.tr("Start"), _format_duration(clip.timeline_start))
        self._add_row(self.tr("Clip duration"), _format_duration(clip.duration))

        asset = self._media_asset_for_clip(clip, project)
        if asset is not None:
            self._add_row(self.tr("Path"), asset.file_path)
            if asset.width is not None and asset.height is not None:
                self._add_row(self.tr("Resolution"), f"{asset.width} x {asset.height}")
            if asset.fps is not None:
                self._add_row(self.tr("FPS"), f"{asset.fps:.2f}")
            if asset.video_codec:
                self._add_row(self.tr("Video codec"), asset.video_codec)
            if asset.audio_codec:
                self._add_row(self.tr("Audio codec"), asset.audio_codec)
            if asset.sample_rate is not None:
                self._add_row(self.tr("Sample rate"), f"{asset.sample_rate} Hz")
            if asset.duration_seconds is not None:
                self._add_row(self.tr("Source duration"), _format_duration(asset.duration_seconds))
            if asset.file_size_bytes is not None:
                self._add_row(self.tr("Size"), _format_file_size(asset.file_size_bytes))
                bitrate = _estimate_bitrate(asset.file_size_bytes, asset.duration_seconds)
                if bitrate is not None:
                    self._add_row(self.tr("Bitrate"), bitrate)

        if isinstance(clip, TextClip):
            self._add_row(self.tr("Content"), (clip.content or "").strip() or "-")
            self._add_row(self.tr("Font size"), str(clip.font_size))
            self._add_row(self.tr("Color"), clip.color)

    def _populate_subtitle_segment(self, segment) -> None:
        self._add_row(self.tr("File"), segment.source_name or "-")
        self._add_row(self.tr("Type"), self.tr("Subtitle (library)"))
        self._add_row(self.tr("Start"), _format_duration(segment.start_seconds))
        self._add_row(
            self.tr("Clip duration"),
            _format_duration(max(0.0, segment.end_seconds - segment.start_seconds)),
        )
        self._add_row(self.tr("Content"), (segment.text or "").strip() or "-")
        self._add_row(self.tr("Path"), segment.source_path or "-")
        self._add_row(self.tr("Line"), str(int(segment.segment_index) + 1))

    def _set_subtitle_lines_visible(self, visible: bool) -> None:
        show = bool(visible)
        self._subtitle_title.setVisible(show)
        self._subtitle_list.setVisible(show)

    def _populate_subtitle_lines(self, entry_id: str, selected_segment_index: int | None = None) -> None:
        entry = next(
            (item for item in self._app_controller.subtitle_library_entries() if item.entry_id == entry_id),
            None,
        )
        if entry is None or not entry.segments:
            self._set_subtitle_lines_visible(False)
            return

        self._set_subtitle_lines_visible(True)
        self._subtitle_rows = []
        self._subtitle_list.clear()

        for segment_index, (segment_start, segment_end, segment_text) in enumerate(entry.segments):
            clean_text = (segment_text or "").replace("\n", " ").strip() or "-"
            item = QListWidgetItem(
                self.tr("{index}. {text}").format(index=segment_index + 1, text=clean_text),
                self._subtitle_list,
            )
            item.setToolTip(
                self.tr("{start} - {end}").format(
                    start=_format_duration(segment_start),
                    end=_format_duration(segment_end),
                )
            )
            self._subtitle_rows.append((entry.entry_id, segment_index))

        if not self._subtitle_rows:
            return

        target_row = 0
        if selected_segment_index is not None:
            key = (entry.entry_id, int(selected_segment_index))
            if key in self._subtitle_rows:
                target_row = self._subtitle_rows.index(key)

        self._subtitle_list_refreshing = True
        try:
            self._subtitle_list.setCurrentRow(target_row)
        finally:
            self._subtitle_list_refreshing = False

    def _on_subtitle_row_changed(self, row: int) -> None:
        if self._subtitle_list_refreshing:
            return
        if row < 0 or row >= len(self._subtitle_rows):
            return

        entry_id, segment_index = self._subtitle_rows[row]
        self._app_controller.select_subtitle_segment(entry_id, segment_index)
        selected = self._app_controller.selected_subtitle_segment()
        if selected is not None:
            self._app_controller.playback_controller.seek(selected.start_seconds)

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
        key_label.setFixedWidth(112)
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
        return translate("DetailsInspector", "Audio")
    if isinstance(clip, ImageClip):
        return translate("DetailsInspector", "Image")
    if isinstance(clip, TextClip):
        return translate("DetailsInspector", "Text")
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
