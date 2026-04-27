from __future__ import annotations

from app.controllers.app_controller import AppController
from app.domain.clips.audio_clip import AudioClip
from app.domain.clips.base_clip import BaseClip
from app.domain.clips.image_clip import ImageClip
from app.domain.clips.text_clip import TextClip
from app.domain.clips.video_clip import VideoClip
from app.domain.project import Project
from app.ui.shared.icons import build_icon
from PySide6.QtCore import QCoreApplication, QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QFocusEvent, QKeyEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class _SubtitleLineEdit(QLineEdit):
    """Line editor that commits on focus-out/Enter and reverts on Escape."""

    commit_requested = Signal(str)
    revert_requested = Signal()
    focus_received = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._committed = False
        self.editingFinished.connect(self._on_editing_finished)

    def focusInEvent(self, event: QFocusEvent) -> None:  # noqa: N802
        self._committed = False
        super().focusInEvent(event)
        self.focus_received.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.revert_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:  # noqa: N802
        super().focusOutEvent(event)
        self._on_editing_finished()

    def reset_committed_flag(self) -> None:
        self._committed = False

    def suppress_commit(self) -> None:
        self._committed = True

    def _on_editing_finished(self) -> None:
        if self._committed:
            return
        self._committed = True
        self.commit_requested.emit(self.text())


class _SubtitleListRowWidget(QWidget):
    """Subtitle row widget: index + inline editable text + quick actions."""

    text_commit_requested = Signal(str)
    focus_requested = Signal()
    add_requested = Signal()
    delete_requested = Signal()
    hover_requested = Signal(object)

    def __init__(self, line_number: int, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("details_subtitle_row")
        self._original_text = (text or "").strip() or "-"
        self._hovered = False
        self.setProperty("hovered", False)
        self.setMinimumHeight(44)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 10, 8)
        layout.setSpacing(8)

        self._index_label = QLabel(str(line_number), self)
        self._index_label.setObjectName("details_subtitle_row_index")
        self._index_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._index_label)

        self._text_edit = _SubtitleLineEdit(self)
        self._text_edit.setObjectName("details_subtitle_row_text")
        self._text_edit.setText(self._original_text)
        self._text_edit.commit_requested.connect(self._on_commit)
        self._text_edit.revert_requested.connect(self._on_revert)
        self._text_edit.focus_received.connect(self.focus_requested.emit)
        layout.addWidget(self._text_edit, 1)

        self._add_button = QToolButton(self)
        self._add_button.setObjectName("details_subtitle_row_add")
        self._add_button.setText("+")
        self._add_button.setAutoRaise(True)
        self._add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_button.setToolTip("")
        self._add_button.clicked.connect(self.add_requested.emit)
        layout.addWidget(self._add_button)

        self._delete_button = QToolButton(self)
        self._delete_button.setObjectName("details_subtitle_row_delete")
        self._delete_button.setIcon(build_icon("delete", color="#e5ebf2"))
        self._delete_button.setIconSize(QSize(12, 12))
        self._delete_button.setText("")
        self._delete_button.setAutoRaise(True)
        self._delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete_button.setToolTip("")
        self._delete_button.clicked.connect(self.delete_requested.emit)
        layout.addWidget(self._delete_button)

        self._hover_watch_widgets = (
            self._index_label,
            self._text_edit,
            self._add_button,
            self._delete_button,
        )
        for watched in self._hover_watch_widgets:
            watched.setMouseTracking(True)
            watched.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            watched.installEventFilter(self)

        self._update_action_buttons_visibility()

    def enterEvent(self, event) -> None:  # type: ignore[override]
        super().enterEvent(event)
        self.hover_requested.emit(self)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        super().leaveEvent(event)
        QTimer.singleShot(0, self._sync_hover_from_cursor)

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched in self._hover_watch_widgets:
            event_type = event.type()
            if event_type in {
                QEvent.Type.Enter,
                QEvent.Type.HoverEnter,
                QEvent.Type.MouseMove,
                QEvent.Type.HoverMove,
            }:
                self.hover_requested.emit(self)
            elif event_type in {QEvent.Type.Leave, QEvent.Type.HoverLeave}:
                QTimer.singleShot(0, self._sync_hover_from_cursor)
        return super().eventFilter(watched, event)

    def set_selected(self, selected: bool) -> None:
        if bool(self.property("selected")) == bool(selected):
            return
        self.setProperty("selected", bool(selected))
        self._repolish()
        self._update_action_buttons_visibility()

    def set_text(self, value: str) -> None:
        normalized = (value or "").strip() or "-"
        self._original_text = normalized
        self._text_edit.suppress_commit()
        self._text_edit.blockSignals(True)
        self._text_edit.setText(normalized)
        self._text_edit.blockSignals(False)
        self._text_edit.reset_committed_flag()

    def _on_commit(self, value: str) -> None:
        normalized = (value or "").strip()
        if not normalized:
            self._text_edit.suppress_commit()
            self._text_edit.setText(self._original_text)
            return
        if normalized == self._original_text:
            return
        self._original_text = normalized
        self.text_commit_requested.emit(normalized)

    def _on_revert(self) -> None:
        self._text_edit.suppress_commit()
        self._text_edit.setText(self._original_text)
        self._text_edit.clearFocus()

    def _update_action_buttons_visibility(self) -> None:
        show_actions = self._hovered
        self._add_button.setVisible(show_actions)
        self._delete_button.setVisible(show_actions)

    def _set_hover_state(self, hovered: bool) -> None:
        if self._hovered == hovered:
            return
        self._hovered = hovered
        self.setProperty("hovered", hovered)
        self._repolish()
        self._update_action_buttons_visibility()

    def _sync_hover_from_cursor(self) -> None:
        should_hover = self.rect().contains(self.mapFromGlobal(QCursor.pos()))
        self.hover_requested.emit(self if should_hover else None)

    def _repolish(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)
        for child in self.findChildren(QWidget):
            child.style().unpolish(child)
            child.style().polish(child)
        self.update()


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
        subtitle_layout.setSpacing(4)

        search_row = QWidget(self._subtitle_page)
        search_row.setObjectName("details_subtitle_search_row")
        search_row_layout = QHBoxLayout(search_row)
        search_row_layout.setContentsMargins(0, 0, 0, 0)
        search_row_layout.setSpacing(4)

        self._subtitle_search_input = QLineEdit(search_row)
        self._subtitle_search_input.setObjectName("details_subtitle_search")
        self._subtitle_search_input.setPlaceholderText(self.tr("Tìm kiếm"))
        self._subtitle_search_input.addAction(
            build_icon("zoom-out", color="#6e7d8e"),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self._subtitle_search_input.textChanged.connect(self._on_subtitle_search_text_changed)
        search_row_layout.addWidget(self._subtitle_search_input, 1)

        self._toolbar_sort_button = self._build_subtitle_toolbar_button("A-")
        self._toolbar_filter_button = self._build_subtitle_toolbar_button("-≡")
        self._toolbar_zoom_button = self._build_subtitle_toolbar_button("⊖")
        self._toolbar_help_button = self._build_subtitle_toolbar_button("?")
        search_row_layout.addWidget(self._toolbar_sort_button)
        search_row_layout.addWidget(self._toolbar_filter_button)
        search_row_layout.addWidget(self._toolbar_zoom_button)
        search_row_layout.addWidget(self._toolbar_help_button)
        subtitle_layout.addWidget(search_row)

        self._subtitle_list = QListWidget(self._subtitle_page)
        self._subtitle_list.setObjectName("details_subtitle_list")
        self._subtitle_list.setAlternatingRowColors(False)
        self._subtitle_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._subtitle_list.setMouseTracking(True)
        self._subtitle_list.viewport().setMouseTracking(True)
        self._subtitle_list.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._subtitle_list.currentRowChanged.connect(self._on_subtitle_row_changed)
        self._subtitle_list.viewport().installEventFilter(self)
        subtitle_layout.addWidget(self._subtitle_list, 1)
        self._stack.addWidget(self._subtitle_page)

        self._app_controller.project_controller.project_changed.connect(self._refresh)
        self._app_controller.timeline_controller.timeline_edited.connect(self._refresh)
        self._app_controller.selection_controller.selection_changed.connect(self._refresh)
        self._app_controller.subtitle_selection_changed.connect(self._on_external_subtitle_selection_changed)
        self._app_controller.subtitle_library_changed.connect(self._refresh)
        self._refresh()

    def _build_subtitle_toolbar_button(self, text: str) -> QToolButton:
        button = QToolButton(self._subtitle_page)
        button.setObjectName("details_subtitle_toolbar_button")
        button.setText(text)
        button.setAutoRaise(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        return button

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
        if watched is self._subtitle_list.viewport():
            event_type = event.type()
            if event_type == QEvent.Type.Leave:
                self._clear_subtitle_row_hover_states()
            elif event_type in {QEvent.Type.MouseMove, QEvent.Type.HoverMove}:
                self._sync_subtitle_row_hover_from_cursor()
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
            self._apply_subtitle_filter()
            return
        self._populate_subtitle_lines(selected.entry_id, selected.segment_index)

    def _on_external_subtitle_selection_changed(self) -> None:
        if self._mode != self.MODE_SUBTITLES:
            return
        selected = self._app_controller.selected_subtitle_segment()
        if selected is None:
            return

        if not self._subtitle_rows:
            self._populate_subtitle_lines(selected.entry_id, selected.segment_index)
            return

        active_entry_id = self._subtitle_rows[0][0]
        if selected.entry_id != active_entry_id:
            self._populate_subtitle_lines(selected.entry_id, selected.segment_index)
            return

        row = self._row_index_for_subtitle(selected.entry_id, selected.segment_index)
        if row is None:
            self._populate_subtitle_lines(selected.entry_id, selected.segment_index)
            return

        previous_flag = self._subtitle_list_refreshing
        self._subtitle_list_refreshing = True
        try:
            self._subtitle_list.setCurrentRow(row)
        finally:
            self._subtitle_list_refreshing = previous_flag
        self._update_subtitle_row_selection_styles()

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

                list_item = QListWidgetItem()
                list_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                list_item.setToolTip("")
                self._subtitle_list.addItem(list_item)

                row_widget = _SubtitleListRowWidget(segment_index + 1, clean_text, self._subtitle_list)
                row_widget.text_commit_requested.connect(
                    lambda value, eid=entry.entry_id, idx=segment_index: self._on_subtitle_text_committed(
                        eid,
                        idx,
                        value,
                    )
                )
                row_widget.focus_requested.connect(
                    lambda eid=entry.entry_id, idx=segment_index: self._focus_subtitle_row(eid, idx)
                )
                row_widget.add_requested.connect(
                    lambda eid=entry.entry_id, idx=segment_index: self._on_add_subtitle_requested(eid, idx)
                )
                row_widget.delete_requested.connect(
                    lambda eid=entry.entry_id, idx=segment_index: self._on_delete_subtitle_requested(eid, idx)
                )
                row_widget.hover_requested.connect(self._on_subtitle_row_hover_requested)
                self._subtitle_list.setItemWidget(list_item, row_widget)
                list_item.setSizeHint(row_widget.sizeHint())

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
            self._apply_subtitle_filter()
            self._clear_subtitle_row_hover_states()
            self._update_subtitle_row_selection_styles()

    def _on_subtitle_search_text_changed(self, _value: str) -> None:
        if self._mode != self.MODE_SUBTITLES:
            return
        self._apply_subtitle_filter()

    def _apply_subtitle_filter(self) -> None:
        query = (self._subtitle_search_input.text() or "").strip().lower()
        previous_flag = self._subtitle_list_refreshing
        self._subtitle_list_refreshing = True
        current_row_after_filter = -1
        try:
            first_visible_row: int | None = None
            for row, (entry_id, segment_index) in enumerate(self._subtitle_rows):
                item = self._subtitle_list.item(row)
                if item is None:
                    continue
                row_text = (self._subtitle_text(entry_id, segment_index) or "").lower()
                visible = not query or query in row_text
                item.setHidden(not visible)
                if visible and first_visible_row is None:
                    first_visible_row = row

            current_row = self._subtitle_list.currentRow()
            if current_row < 0:
                if first_visible_row is not None:
                    self._subtitle_list.setCurrentRow(first_visible_row)
                    current_row_after_filter = first_visible_row
                return
            current_item = self._subtitle_list.item(current_row)
            if current_item is None or current_item.isHidden():
                if first_visible_row is not None:
                    self._subtitle_list.setCurrentRow(first_visible_row)
                    current_row_after_filter = first_visible_row
                else:
                    self._subtitle_list.setCurrentRow(-1)
                    current_row_after_filter = -1
            else:
                current_row_after_filter = current_row
        finally:
            self._subtitle_list_refreshing = previous_flag
            self._update_subtitle_row_selection_styles()

        if previous_flag:
            return
        if current_row_after_filter < 0 or current_row_after_filter >= len(self._subtitle_rows):
            return
        item = self._subtitle_list.item(current_row_after_filter)
        if item is None or item.isHidden():
            return
        entry_id, segment_index = self._subtitle_rows[current_row_after_filter]
        self._app_controller.select_subtitle_segment(entry_id, segment_index)
        self._clear_subtitle_row_hover_states()

    def _focus_subtitle_row(self, entry_id: str, segment_index: int) -> None:
        row = self._row_index_for_subtitle(entry_id, segment_index)
        if row is None:
            return
        item = self._subtitle_list.item(row)
        if item is not None and item.isHidden():
            self._subtitle_search_input.clear()
            item.setHidden(False)
        if self._subtitle_list.currentRow() == row:
            return
        self._subtitle_list.setCurrentRow(row)

    def _on_subtitle_row_changed(self, row: int) -> None:
        if self._subtitle_list_refreshing:
            return
        self._update_subtitle_row_selection_styles()
        if row < 0 or row >= len(self._subtitle_rows):
            return

        item = self._subtitle_list.item(row)
        if item is not None and item.isHidden():
            return

        entry_id, segment_index = self._subtitle_rows[row]
        self._app_controller.select_subtitle_segment(entry_id, segment_index)
        selected = self._app_controller.selected_subtitle_segment()
        if selected is None:
            return
        if not self._app_controller.is_subtitle_segment_loaded_on_timeline(
            selected.entry_id,
            selected.segment_index,
        ):
            return
        self._app_controller.playback_controller.seek(selected.start_seconds)

    def _on_subtitle_text_committed(self, entry_id: str, segment_index: int, new_text: str) -> None:
        if self._subtitle_list_refreshing:
            return
        normalized = (new_text or "").strip()
        if not normalized:
            self._restore_subtitle_row_text(entry_id, segment_index)
            return

        updated = self._app_controller.update_subtitle_segment_text(entry_id, segment_index, normalized)
        if updated:
            return
        self._restore_subtitle_row_text(entry_id, segment_index)

    def _on_add_subtitle_requested(self, entry_id: str, segment_index: int) -> None:
        if self._subtitle_list_refreshing:
            return
        self._app_controller.insert_subtitle_segment_after(entry_id, segment_index)

    def _on_delete_subtitle_requested(self, entry_id: str, segment_index: int) -> None:
        if self._subtitle_list_refreshing:
            return
        self._app_controller.delete_subtitle_segment(entry_id, segment_index)

    def _restore_subtitle_row_text(self, entry_id: str, segment_index: int) -> None:
        row = self._row_index_for_subtitle(entry_id, segment_index)
        if row is None:
            return
        item = self._subtitle_list.item(row)
        if item is None:
            return
        widget = self._subtitle_list.itemWidget(item)
        if not isinstance(widget, _SubtitleListRowWidget):
            return
        original_text = self._subtitle_text(entry_id, segment_index)
        if original_text is None:
            original_text = "-"
        self._subtitle_list_refreshing = True
        try:
            widget.set_text(original_text)
        finally:
            self._subtitle_list_refreshing = False

    def _row_index_for_subtitle(self, entry_id: str, segment_index: int) -> int | None:
        key = (entry_id, segment_index)
        if key not in self._subtitle_rows:
            return None
        return self._subtitle_rows.index(key)

    def _update_subtitle_row_selection_styles(self) -> None:
        current_row = self._subtitle_list.currentRow()
        for row in range(self._subtitle_list.count()):
            item = self._subtitle_list.item(row)
            if item is None:
                continue
            widget = self._subtitle_list.itemWidget(item)
            if isinstance(widget, _SubtitleListRowWidget):
                widget.set_selected(row == current_row and not item.isHidden())

    def _on_subtitle_row_hover_requested(self, hovered_widget: object | None) -> None:
        for row in range(self._subtitle_list.count()):
            item = self._subtitle_list.item(row)
            if item is None:
                continue
            widget = self._subtitle_list.itemWidget(item)
            if isinstance(widget, _SubtitleListRowWidget):
                widget._set_hover_state(widget is hovered_widget and not item.isHidden())

    def _sync_subtitle_row_hover_from_cursor(self) -> None:
        viewport = self._subtitle_list.viewport()
        if not viewport.isVisible():
            self._on_subtitle_row_hover_requested(None)
            return

        cursor_pos = viewport.mapFromGlobal(QCursor.pos())
        if not viewport.rect().contains(cursor_pos):
            self._on_subtitle_row_hover_requested(None)
            return

        item = self._subtitle_list.itemAt(cursor_pos)
        if item is None or item.isHidden():
            self._on_subtitle_row_hover_requested(None)
            return

        widget = self._subtitle_list.itemWidget(item)
        if isinstance(widget, _SubtitleListRowWidget):
            self._on_subtitle_row_hover_requested(widget)
            return
        self._on_subtitle_row_hover_requested(None)

    def _clear_subtitle_row_hover_states(self) -> None:
        for row in range(self._subtitle_list.count()):
            item = self._subtitle_list.item(row)
            if item is None:
                continue
            widget = self._subtitle_list.itemWidget(item)
            if isinstance(widget, _SubtitleListRowWidget):
                widget._set_hover_state(False)

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
