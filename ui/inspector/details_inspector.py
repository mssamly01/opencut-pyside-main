from __future__ import annotations

from app.controllers.app_controller import AppController
from app.domain.clips.base_clip import BaseClip
from app.domain.clips.text_clip import TextClip
from app.domain.clips.video_clip import VideoClip
from app.domain.clips.audio_clip import AudioClip
from app.domain.clips.image_clip import ImageClip
from app.domain.project import Project
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class DetailsInspector(QWidget):
    """Inspector details/subtitle views."""

    MODE_DETAILS = "details"
    MODE_SUBTITLES = "subtitles"

    def __init__(self, app_controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app_controller = app_controller
        self._mode = self.MODE_DETAILS
        self._title_base = ""
        self._title_context: tuple[str, str | None] | None = None
        self._title_edit_allowed = False
        self._title_committing = False
        self._subtitle_rows: list[tuple[str, int]] = []
        self._subtitle_list_refreshing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        self._title_edit = QLineEdit(self)
        self._title_edit.setObjectName("details_project_name_inline")
        self._title_edit.setFrame(False)
        self._title_edit.setReadOnly(True)
        self._title_edit.setMaxLength(180)
        self._title_edit.installEventFilter(self)
        self._title_edit.returnPressed.connect(self._commit_title_change)
        self._title_edit.editingFinished.connect(self._commit_title_change)
        layout.addWidget(self._title_edit)

        self._stack = QStackedWidget(self)
        layout.addWidget(self._stack, 1)

        self._details_page = QWidget(self._stack)
        details_layout = QVBoxLayout(self._details_page)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(8)

        self._rows_container = QWidget(self._details_page)
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(8)
        details_layout.addWidget(self._rows_container)
        details_layout.addStretch(1)
        self._stack.addWidget(self._details_page)

        self._subtitle_page = QWidget(self._stack)
        subtitle_layout = QVBoxLayout(self._subtitle_page)
        subtitle_layout.setContentsMargins(0, 0, 0, 0)
        subtitle_layout.setSpacing(6)

        self._subtitle_list = QListWidget(self._subtitle_page)
        self._subtitle_list.setAlternatingRowColors(True)
        self._subtitle_list.setWordWrap(True)
        self._subtitle_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._subtitle_list.currentRowChanged.connect(self._on_subtitle_row_changed)
        self._subtitle_list.itemChanged.connect(self._on_subtitle_item_changed)
        subtitle_layout.addWidget(self._subtitle_list, 1)
        self._stack.addWidget(self._subtitle_page)

        self._app_controller.project_controller.project_changed.connect(self._refresh)
        self._app_controller.timeline_controller.timeline_edited.connect(self._refresh)
        self._app_controller.selection_controller.selection_changed.connect(self._refresh)
        self._app_controller.subtitle_selection_changed.connect(self._refresh)
        self._app_controller.subtitle_library_changed.connect(self._refresh)
        self._refresh()

    def set_mode(self, mode: str) -> None:
        normalized = mode if mode in {self.MODE_DETAILS, self.MODE_SUBTITLES} else self.MODE_DETAILS
        if normalized == self._mode:
            self._refresh()
            return
        if not self._title_edit.isReadOnly():
            self._commit_title_change()
        self._mode = normalized
        self._refresh()

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched is self._title_edit and event.type() == QEvent.Type.MouseButtonPress:
            if self._title_edit_allowed and self._title_edit.isReadOnly():
                self._begin_title_edit()
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def _begin_title_edit(self) -> None:
        if not self._title_edit_allowed:
            return
        self._title_edit.setReadOnly(False)
        self._title_edit.setText(self._title_base)
        self._title_edit.setFocus(Qt.FocusReason.MouseFocusReason)
        self._title_edit.selectAll()

    def _commit_title_change(self) -> None:
        if self._title_edit.isReadOnly() or self._title_committing:
            return
        self._title_committing = True
        try:
            value = self._title_edit.text().strip() or self._title_base
            previous = self._title_base
            context = self._title_context

            renamed = False
            if context is not None and value != previous:
                context_type, context_id = context
                if context_type == "project":
                    renamed = self._app_controller.rename_active_project(value)
                elif context_type == "clip" and context_id is not None:
                    renamed = self._app_controller.rename_clip(context_id, value)
                if renamed:
                    self._title_base = value

            self._title_edit.setReadOnly(True)
            self._title_edit.clearFocus()
            self._title_edit.setText(self._title_base)

            if renamed:
                self._refresh()
        finally:
            self._title_committing = False

    def _refresh(self) -> None:
        if self._mode == self.MODE_SUBTITLES:
            self._refresh_subtitle_mode()
            return
        self._refresh_details_mode()

    def _refresh_details_mode(self) -> None:
        self._stack.setCurrentWidget(self._details_page)
        self._clear_rows()
        self._subtitle_rows = []
        self._subtitle_list.clear()

        project = self._app_controller.project_controller.active_project()
        clip = self._selected_clip(project)
        if clip is not None:
            self._title_edit.setVisible(True)
            clip_name = (clip.name or "").strip() or self.tr("Untitled clip")
            self._set_title_state(clip_name, editable=True, context=("clip", clip.clip_id))
            self._populate_clip(clip)
            return

        if project is not None:
            self._title_edit.setVisible(False)
            self._set_title_state("", editable=False, context=None)
            self._populate_project(project)
            return

        self._title_edit.setVisible(False)
        self._set_title_state(self.tr("No project opened"), editable=False, context=None)
        self._add_row(self.tr("Status"), self.tr("No project opened"))

    def _refresh_subtitle_mode(self) -> None:
        self._title_edit.setVisible(False)
        self._stack.setCurrentWidget(self._subtitle_page)
        self._clear_rows()
        self._set_title_state("", editable=False, context=None)
        selected = self._app_controller.selected_subtitle_segment()
        if selected is None:
            self._subtitle_rows = []
            self._subtitle_list.clear()
            return
        self._populate_subtitle_lines(selected.entry_id, selected.segment_index)

    def _populate_project(self, project: Project) -> None:
        self._add_row(self.tr("Project"), (project.name or "").strip() or self.tr("Untitled"))
        self._add_row(self.tr("Tracks"), str(len(project.timeline.tracks)))
        self._add_row(self.tr("Assets"), str(len(project.media_items)))

    def _populate_clip(self, clip: BaseClip) -> None:
        self._add_row(self.tr("Type"), _clip_type_label(clip))
        self._add_row(self.tr("Start"), _format_duration(clip.timeline_start))
        self._add_row(self.tr("Clip duration"), _format_duration(clip.duration))
        if isinstance(clip, TextClip):
            self._add_row(self.tr("Content"), (clip.content or "").strip() or "-")
            self._add_row(self.tr("Font size"), str(clip.font_size))
            self._add_row(self.tr("Color"), clip.color)

    def _set_title_state(
        self,
        value: str,
        *,
        editable: bool,
        context: tuple[str, str | None] | None,
    ) -> None:
        self._title_base = value or "-"
        self._title_context = context if editable else None
        self._title_edit_allowed = editable
        if not self._title_edit_allowed:
            self._title_edit.setReadOnly(True)
        if self._title_edit.isReadOnly():
            self._title_edit.setText(self._title_base)

    def _populate_subtitle_lines(self, entry_id: str, selected_segment_index: int | None = None) -> None:
        entry = next(
            (item for item in self._app_controller.subtitle_library_entries() if item.entry_id == entry_id),
            None,
        )
        self._subtitle_list_refreshing = True
        try:
            self._subtitle_rows = []
            self._subtitle_list.clear()
            if entry is None or not entry.segments:
                return

            for segment_index, (segment_start, segment_end, segment_text) in enumerate(entry.segments):
                clean_text = (segment_text or "").replace("\n", " ").strip() or "-"
                item = QListWidgetItem(clean_text, self._subtitle_list)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                item.setToolTip(
                    self.tr("{line}. {start} - {end}").format(
                        line=segment_index + 1,
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

    def _on_subtitle_item_changed(self, item: QListWidgetItem) -> None:
        if self._subtitle_list_refreshing:
            return

        row = self._subtitle_list.row(item)
        if row < 0 or row >= len(self._subtitle_rows):
            return
        entry_id, segment_index = self._subtitle_rows[row]
        new_text = (item.text() or "").strip()
        if not new_text:
            self._restore_subtitle_item_text(item, entry_id, segment_index)
            return

        updated = self._app_controller.update_subtitle_segment_text(entry_id, segment_index, new_text)
        if updated:
            return
        self._restore_subtitle_item_text(item, entry_id, segment_index)

    def _restore_subtitle_item_text(self, item: QListWidgetItem, entry_id: str, segment_index: int) -> None:
        original_text = self._subtitle_text(entry_id, segment_index)
        if original_text is None:
            original_text = "-"
        self._subtitle_list_refreshing = True
        try:
            item.setText(original_text)
        finally:
            self._subtitle_list_refreshing = False

    def _subtitle_text(self, entry_id: str, segment_index: int) -> str | None:
        entry = next(
            (item for item in self._app_controller.subtitle_library_entries() if item.entry_id == entry_id),
            None,
        )
        if entry is None:
            return None
        if segment_index < 0 or segment_index >= len(entry.segments):
            return None
        return (entry.segments[segment_index][2] or "").strip() or "-"

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
