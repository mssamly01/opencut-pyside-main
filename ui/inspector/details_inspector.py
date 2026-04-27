from __future__ import annotations

from app.controllers.app_controller import AppController
from app.domain.clips.audio_clip import AudioClip
from app.domain.clips.base_clip import BaseClip
from app.domain.clips.image_clip import ImageClip
from app.domain.clips.text_clip import TextClip
from app.domain.clips.video_clip import VideoClip
from app.domain.project import Project
from app.services.subtitle_filters import (
    find_adjacent_duplicate_indices,
    find_interjection_indices,
    find_ocr_error_indices,
    find_reading_speed_outlier_indices,
)
from app.ui.shared.icons import build_icon
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCursor, QFocusEvent, QKeyEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
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


class _FindReplaceDialog(QDialog):
    """Tìm và thay thế hàng loạt trong toàn bộ phụ đề của entry hiện tại.

    Mirrors ``FindReplaceDialog`` in the reference editor app. The dialog
    only collects user input — the actual bulk replace is delegated to
    :meth:`AppController.replace_all_in_subtitle_entry`.
    """

    def __init__(self, parent: QWidget, initial_find_text: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Tìm & thay thế phụ đề"))
        self.resize(420, 200)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(QLabel(self.tr("Tìm:")))
        self._find_input = QLineEdit(self)
        self._find_input.setPlaceholderText(self.tr("Nhập văn bản cần tìm..."))
        self._find_input.setText(initial_find_text)
        layout.addWidget(self._find_input)

        layout.addWidget(QLabel(self.tr("Thay bằng:")))
        self._replace_input = QLineEdit(self)
        self._replace_input.setPlaceholderText(
            self.tr("Để trống để xoá đoạn khớp...")
        )
        layout.addWidget(self._replace_input)

        self._case_sensitive = QCheckBox(self.tr("Phân biệt chữ hoa/thường"))
        layout.addWidget(self._case_sensitive)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            self.tr("Thay tất cả")
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.tr("Huỷ"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._find_input.setFocus()
        if initial_find_text:
            self._find_input.selectAll()

    def find_text(self) -> str:
        return self._find_input.text()

    def replace_text(self) -> str:
        return self._replace_input.text()

    def case_sensitive(self) -> bool:
        return self._case_sensitive.isChecked()


class _InterjectionFilterDialog(QDialog):
    """Checklist dialog for bulk-deleting Chinese-interjection-only subtitles.

    Mirrors ``DeleteInterjectionsDialog`` from the reference editor app: each
    row represents a candidate segment, all are pre-checked, and the OK action
    returns the segment indices the user kept checked.
    """

    def __init__(self, parent: QWidget, rows: list[tuple[int, str]]) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Bộ lọc câu cảm thán"))
        self.resize(500, 450)
        self._rows = rows

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        header = QLabel(
            self.tr(
                "Phát hiện <b>{count}</b> dòng có khả năng là phụ đề cảm thán."
                "<br>Bỏ chọn các dòng bạn muốn giữ lại trước khi nhấn Xoá."
            ).format(count=len(rows))
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        self._select_all = QCheckBox(self.tr("Chọn tất cả để xoá"))
        self._select_all.setChecked(True)
        self._select_all.stateChanged.connect(self._on_select_all_changed)
        layout.addWidget(self._select_all)

        self._list = QListWidget(self)
        for segment_index, text in rows:
            item = QListWidgetItem(
                self.tr("Dòng {n}: {text}").format(n=segment_index + 1, text=text)
            )
            item.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
            )
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, segment_index)
            self._list.addItem(item)
        layout.addWidget(self._list, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            self.tr("Xoá các dòng đã chọn")
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.tr("Huỷ"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_select_all_changed(self, state: int) -> None:
        check_state = (
            Qt.CheckState.Checked if state != int(Qt.CheckState.Unchecked) else Qt.CheckState.Unchecked
        )
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(check_state)

    def selected_indices(self) -> list[int]:
        result: list[int] = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.append(int(item.data(Qt.ItemDataRole.UserRole)))
        return result


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
        self._subtitle_text_cache: list[str] = []
        self._subtitle_text_lower_cache: list[str] = []
        self._active_subtitle_entry_id: str | None = None
        self._attached_widget_rows: set[int] = set()
        # Estimated row height (incl. margins) used for sizeHint and visible-row math.
        # Matches _SubtitleListRowWidget minimum height + list item padding.
        self._subtitle_row_height: int = 44 + 8
        # Buffer of rows above/below viewport that keep their widgets attached, so
        # small scrolls don't churn widgets.
        self._subtitle_row_buffer: int = 12
        self._pending_visible_row: int | None = None
        # Active "quality" filter: None | "ocr" | "speed" | "duplicate". When set
        # the search input shows a chip and the visible rows are restricted to
        # the indices in `_quality_filter_rows`.
        self._quality_filter: str | None = None
        self._quality_filter_rows: set[int] = set()
        self._quality_filter_chip_visible = False

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
        self._toolbar_filter_button.setToolTip(self.tr("Bộ lọc chất lượng phụ đề"))
        self._toolbar_filter_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._toolbar_filter_button.setMenu(self._build_subtitle_filter_menu())

        # Ctrl+H mở Find/Replace, chỉ hoạt động khi inspector đang ở chế độ
        # phụ đề và phím tắt được hướng tới panel này.
        self._find_replace_shortcut = QShortcut(QKeySequence("Ctrl+H"), self)
        self._find_replace_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._find_replace_shortcut.activated.connect(self._on_find_replace_shortcut)
        search_row_layout.addWidget(self._toolbar_sort_button)
        search_row_layout.addWidget(self._toolbar_filter_button)
        search_row_layout.addWidget(self._toolbar_zoom_button)
        search_row_layout.addWidget(self._toolbar_help_button)
        subtitle_layout.addWidget(search_row)

        self._subtitle_list = QListWidget(self._subtitle_page)
        self._subtitle_list.setObjectName("details_subtitle_list")
        self._subtitle_list.setAlternatingRowColors(False)
        self._subtitle_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._subtitle_list.setUniformItemSizes(True)
        self._subtitle_list.setMouseTracking(True)
        self._subtitle_list.viewport().setMouseTracking(True)
        self._subtitle_list.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._subtitle_list.currentRowChanged.connect(self._on_subtitle_row_changed)
        self._subtitle_list.viewport().installEventFilter(self)
        self._subtitle_list.verticalScrollBar().valueChanged.connect(
            self._on_subtitle_scroll_changed
        )
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

    def _build_subtitle_filter_menu(self) -> QMenu:
        menu = QMenu(self._subtitle_page)
        menu.setObjectName("details_subtitle_filter_menu")

        clear_action = QAction(self.tr("Bỏ lọc"), menu)
        clear_action.triggered.connect(lambda: self._set_quality_filter(None))
        menu.addAction(clear_action)
        menu.addSeparator()

        ocr_action = QAction(self.tr("Lọc lỗi OCR"), menu)
        ocr_action.triggered.connect(lambda: self._set_quality_filter("ocr"))
        menu.addAction(ocr_action)

        speed_action = QAction(self.tr("Lọc tốc độ đọc < 3 ký tự/s"), menu)
        speed_action.triggered.connect(lambda: self._set_quality_filter("speed"))
        menu.addAction(speed_action)

        duplicate_action = QAction(self.tr("Lọc phụ đề trùng liền kề"), menu)
        duplicate_action.triggered.connect(lambda: self._set_quality_filter("duplicate"))
        menu.addAction(duplicate_action)

        menu.addSeparator()
        interjection_action = QAction(self.tr("Bộ lọc câu cảm thán..."), menu)
        interjection_action.triggered.connect(self._open_interjection_dialog)
        menu.addAction(interjection_action)

        find_replace_action = QAction(self.tr("Tìm && thay thế...\tCtrl+H"), menu)
        find_replace_action.triggered.connect(self._open_find_replace_dialog)
        menu.addAction(find_replace_action)
        return menu

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
            self._subtitle_text_cache = []
            self._subtitle_text_lower_cache = []
            self._attached_widget_rows.clear()
            self._active_subtitle_entry_id = None
            self._reset_quality_filter()
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

        # Fast incremental path: same entry & same number of segments => just refresh
        # text on attached widgets and the text caches in place. This avoids the
        # heavy rebuild of N item-widgets every time a segment text edit emits
        # subtitle_library_changed.
        if (
            entry is not None
            and entry.entry_id == self._active_subtitle_entry_id
            and len(entry.segments) == len(self._subtitle_rows)
            and len(entry.segments) > 0
        ):
            self._update_subtitle_caches_in_place(entry)
            self._refresh_attached_subtitle_widgets()
            if selected_segment_index is not None:
                key = (entry.entry_id, int(selected_segment_index))
                if key in self._subtitle_rows:
                    target_row = self._subtitle_rows.index(key)
                    if self._subtitle_list.currentRow() != target_row:
                        previous_flag = self._subtitle_list_refreshing
                        self._subtitle_list_refreshing = True
                        try:
                            self._subtitle_list.setCurrentRow(target_row)
                        finally:
                            self._subtitle_list_refreshing = previous_flag
            self._apply_subtitle_filter()
            self._clear_subtitle_row_hover_states()
            self._update_subtitle_row_selection_styles()
            return

        self._subtitle_list_refreshing = True
        try:
            self._subtitle_rows = []
            self._subtitle_text_cache = []
            self._subtitle_text_lower_cache = []
            self._attached_widget_rows.clear()
            self._active_subtitle_entry_id = None
            # Quality-filter row indices are invalidated by an entry switch or
            # any change in the segment count; the search-input chip should
            # also be cleared so the user sees the new entry's full list.
            self._reset_quality_filter()
            self._subtitle_list.clear()
            if entry is None or not entry.segments:
                return

            self._active_subtitle_entry_id = entry.entry_id
            placeholder_size = QSize(0, self._subtitle_row_height)

            for segment_index, (_segment_start, _segment_end, segment_text) in enumerate(entry.segments):
                clean_text = (segment_text or "").replace("\n", " ").strip() or "-"

                list_item = QListWidgetItem()
                list_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                list_item.setToolTip("")
                list_item.setSizeHint(placeholder_size)
                self._subtitle_list.addItem(list_item)

                self._subtitle_rows.append((entry.entry_id, segment_index))
                self._subtitle_text_cache.append(clean_text)
                self._subtitle_text_lower_cache.append(clean_text.lower())

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
            self._sync_attached_subtitle_widgets()
            self._clear_subtitle_row_hover_states()
            self._update_subtitle_row_selection_styles()

    def _on_subtitle_search_text_changed(self, _value: str) -> None:
        if self._mode != self.MODE_SUBTITLES:
            return
        # User typed (or cleared) text while a quality filter chip was showing —
        # exit the quality-filter mode so the search query takes over.
        if self._quality_filter_chip_visible:
            self._quality_filter = None
            self._quality_filter_rows = set()
            self._quality_filter_chip_visible = False
        self._apply_subtitle_filter()

    def _reset_quality_filter(self) -> None:
        """Drop any active quality filter and clear the search-input chip."""

        had_chip = self._quality_filter_chip_visible
        self._quality_filter = None
        self._quality_filter_rows = set()
        self._quality_filter_chip_visible = False
        if had_chip:
            self._subtitle_search_input.blockSignals(True)
            try:
                self._subtitle_search_input.clear()
            finally:
                self._subtitle_search_input.blockSignals(False)

    def _set_quality_filter(self, kind: str | None) -> None:
        """Activate (or clear) one of the four built-in quality filters."""

        if kind not in (None, "ocr", "speed", "duplicate"):
            return
        if kind is None:
            self._quality_filter = None
            self._quality_filter_rows = set()
            self._quality_filter_chip_visible = False
            self._subtitle_search_input.blockSignals(True)
            try:
                self._subtitle_search_input.clear()
            finally:
                self._subtitle_search_input.blockSignals(False)
            self._apply_subtitle_filter()
            return

        entry = self._current_subtitle_entry()
        if entry is None or not entry.segments:
            self._quality_filter = None
            self._quality_filter_rows = set()
            self._quality_filter_chip_visible = False
            QMessageBox.information(
                self,
                self.tr("Bộ lọc phụ đề"),
                self.tr("Chưa có phụ đề để lọc."),
            )
            return

        if kind == "ocr":
            indices = find_ocr_error_indices(entry.segments)
            label = self.tr("[Chế độ lọc: Lỗi OCR]")
            empty_message = self.tr("Không phát hiện lỗi OCR trong danh sách phụ đề.")
        elif kind == "speed":
            indices = find_reading_speed_outlier_indices(entry.segments)
            label = self.tr("[Chế độ lọc: Tốc độ đọc < 3 ký tự/s]")
            empty_message = self.tr("Không có phụ đề nào đọc dưới 3 ký tự/giây.")
        else:  # "duplicate"
            indices = find_adjacent_duplicate_indices(entry.segments)
            label = self.tr("[Chế độ lọc: Trùng lặp liền kề]")
            empty_message = self.tr("Không có phụ đề nào trùng lặp liền kề.")

        if not indices:
            self._quality_filter = None
            self._quality_filter_rows = set()
            self._quality_filter_chip_visible = False
            QMessageBox.information(self, self.tr("Bộ lọc phụ đề"), empty_message)
            return

        self._quality_filter = kind
        self._quality_filter_rows = set(indices)
        self._quality_filter_chip_visible = True
        self._subtitle_search_input.blockSignals(True)
        try:
            self._subtitle_search_input.setText(label)
        finally:
            self._subtitle_search_input.blockSignals(False)
        self._apply_subtitle_filter()

    def _current_subtitle_entry(self):
        if self._active_subtitle_entry_id is None:
            return None
        for entry in self._app_controller.subtitle_library_entries():
            if entry.entry_id == self._active_subtitle_entry_id:
                return entry
        return None

    def _open_interjection_dialog(self) -> None:
        entry = self._current_subtitle_entry()
        if entry is None or not entry.segments:
            QMessageBox.information(
                self,
                self.tr("Bộ lọc câu cảm thán"),
                self.tr("Chưa có phụ đề để lọc."),
            )
            return

        indices = find_interjection_indices(entry.segments)
        if not indices:
            QMessageBox.information(
                self,
                self.tr("Bộ lọc câu cảm thán"),
                self.tr("Tuyệt vời, không tìm thấy dòng cảm thán nào trong phụ đề!"),
            )
            return

        rows = [(idx, entry.segments[idx][2]) for idx in indices]
        dialog = _InterjectionFilterDialog(self, rows)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected = dialog.selected_indices()
        if not selected:
            return

        # Delete in descending order so earlier indices remain stable as the
        # entry's segment list shrinks. Each call re-emits subtitle_library_changed
        # but the inspector's incremental refresh keeps the cost manageable.
        for idx in sorted(selected, reverse=True):
            self._app_controller.delete_subtitle_segment(entry.entry_id, idx)

        QMessageBox.information(
            self,
            self.tr("Bộ lọc câu cảm thán"),
            self.tr("Đã xoá {count} dòng phụ đề cảm thán.").format(count=len(selected)),
        )

    def _on_find_replace_shortcut(self) -> None:
        if self._mode != self.MODE_SUBTITLES:
            return
        self._open_find_replace_dialog()

    def _open_find_replace_dialog(self) -> None:
        entry = self._current_subtitle_entry()
        if entry is None or not entry.segments:
            QMessageBox.information(
                self,
                self.tr("Tìm & thay thế"),
                self.tr("Chưa có phụ đề để tìm kiếm."),
            )
            return

        # Pre-fill the find field with the search-bar query when it isn't a
        # quality-filter chip — saves typing the same word twice.
        prefill = ""
        if not self._quality_filter_chip_visible:
            prefill = (self._subtitle_search_input.text() or "").strip()

        dialog = _FindReplaceDialog(self, initial_find_text=prefill)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        find_text = dialog.find_text()
        if not find_text:
            return
        replace_text = dialog.replace_text()
        case_sensitive = dialog.case_sensitive()

        count = self._app_controller.replace_all_in_subtitle_entry(
            entry.entry_id,
            find_text,
            replace_text,
            case_sensitive=case_sensitive,
        )
        if count == 0:
            QMessageBox.information(
                self,
                self.tr("Tìm & thay thế"),
                self.tr('Không tìm thấy văn bản:\n"{text}"').format(text=find_text),
            )
            return
        QMessageBox.information(
            self,
            self.tr("Tìm & thay thế"),
            self.tr("Đã thay thế {count} chỗ.").format(count=count),
        )

    def _apply_subtitle_filter(self) -> None:
        if self._quality_filter_chip_visible:
            query = ""
        else:
            query = (self._subtitle_search_input.text() or "").strip().lower()
        quality_rows = self._quality_filter_rows if self._quality_filter else None
        previous_flag = self._subtitle_list_refreshing
        self._subtitle_list_refreshing = True
        current_row_after_filter = -1
        try:
            first_visible_row: int | None = None
            row_count = len(self._subtitle_rows)
            for row in range(row_count):
                item = self._subtitle_list.item(row)
                if item is None:
                    continue
                if quality_rows is not None and row not in quality_rows:
                    visible = False
                elif not query:
                    visible = True
                elif row < len(self._subtitle_text_lower_cache):
                    visible = query in self._subtitle_text_lower_cache[row]
                else:
                    visible = False
                if item.isHidden() == visible:
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
            self._sync_attached_subtitle_widgets()
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
        self._ensure_subtitle_widget_attached(row)
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
        original_text = self._subtitle_text(entry_id, segment_index)
        if original_text is None:
            original_text = "-"
        if 0 <= row < len(self._subtitle_text_cache):
            self._subtitle_text_cache[row] = original_text
            self._subtitle_text_lower_cache[row] = original_text.lower()
        item = self._subtitle_list.item(row)
        if item is None:
            return
        widget = self._subtitle_list.itemWidget(item)
        if not isinstance(widget, _SubtitleListRowWidget):
            return
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
        # Only iterate rows that currently have an attached row widget; off-screen
        # rows have no widget so they need no style update.
        for row in tuple(self._attached_widget_rows):
            item = self._subtitle_list.item(row)
            if item is None:
                continue
            widget = self._subtitle_list.itemWidget(item)
            if isinstance(widget, _SubtitleListRowWidget):
                widget.set_selected(row == current_row and not item.isHidden())

    def _on_subtitle_row_hover_requested(self, hovered_widget: object | None) -> None:
        for row in tuple(self._attached_widget_rows):
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
        for row in tuple(self._attached_widget_rows):
            item = self._subtitle_list.item(row)
            if item is None:
                continue
            widget = self._subtitle_list.itemWidget(item)
            if isinstance(widget, _SubtitleListRowWidget):
                widget._set_hover_state(False)

    def _on_subtitle_scroll_changed(self, _value: int) -> None:
        self._sync_attached_subtitle_widgets()

    def _visible_subtitle_row_range(self) -> tuple[int, int]:
        """Return [first, last] inclusive row indexes intended to have a widget attached.

        Uses the QListWidget's indexAt API so we honor wraps/hidden rows correctly.
        Returns (0, -1) when the viewport has no items.
        """
        row_count = len(self._subtitle_rows)
        if row_count == 0:
            return (0, -1)
        viewport = self._subtitle_list.viewport()
        viewport_rect = viewport.rect()
        if viewport_rect.height() <= 0 or viewport_rect.width() <= 0:
            return (0, -1)

        top_index = self._subtitle_list.indexAt(viewport_rect.topLeft())
        bottom_index = self._subtitle_list.indexAt(viewport_rect.bottomLeft() - QPoint(0, 1))

        if top_index.isValid():
            top_row = top_index.row()
        else:
            # Fallback to scroll math when indexAt misses (e.g. empty space above items).
            scroll_y = self._subtitle_list.verticalScrollBar().value()
            top_row = max(0, scroll_y // max(1, self._subtitle_row_height))

        if bottom_index.isValid():
            bottom_row = bottom_index.row()
        else:
            estimated_visible = max(1, viewport_rect.height() // max(1, self._subtitle_row_height))
            bottom_row = top_row + estimated_visible

        first = max(0, top_row - self._subtitle_row_buffer)
        last = min(row_count - 1, bottom_row + self._subtitle_row_buffer)
        return (first, last)

    def _sync_attached_subtitle_widgets(self) -> None:
        """Ensure widgets are attached only for rows currently inside the visible window.

        Detaches widgets for rows that scrolled far out of view; attaches new widgets
        for rows that scrolled into view. Keeps memory bounded for large lists.
        """
        if not self._subtitle_rows:
            if self._attached_widget_rows:
                for row in tuple(self._attached_widget_rows):
                    self._detach_subtitle_widget(row)
            return

        first, last = self._visible_subtitle_row_range()
        if last < first:
            return

        target_rows = set(range(first, last + 1))
        # Detach widgets that are no longer needed.
        for row in tuple(self._attached_widget_rows):
            if row not in target_rows:
                self._detach_subtitle_widget(row)
        # Attach widgets that are now needed.
        for row in range(first, last + 1):
            self._ensure_subtitle_widget_attached(row)

        self._update_subtitle_row_selection_styles()

    def _ensure_subtitle_widget_attached(self, row: int) -> None:
        if row < 0 or row >= len(self._subtitle_rows):
            return
        if row in self._attached_widget_rows:
            return
        item = self._subtitle_list.item(row)
        if item is None:
            return
        entry_id, segment_index = self._subtitle_rows[row]
        text = (
            self._subtitle_text_cache[row]
            if 0 <= row < len(self._subtitle_text_cache)
            else (self._subtitle_text(entry_id, segment_index) or "-")
        )

        widget = _SubtitleListRowWidget(segment_index + 1, text, self._subtitle_list)
        widget.text_commit_requested.connect(
            lambda value, eid=entry_id, idx=segment_index: self._on_subtitle_text_committed(
                eid,
                idx,
                value,
            )
        )
        widget.focus_requested.connect(
            lambda eid=entry_id, idx=segment_index: self._focus_subtitle_row(eid, idx)
        )
        widget.add_requested.connect(
            lambda eid=entry_id, idx=segment_index: self._on_add_subtitle_requested(eid, idx)
        )
        widget.delete_requested.connect(
            lambda eid=entry_id, idx=segment_index: self._on_delete_subtitle_requested(eid, idx)
        )
        widget.hover_requested.connect(self._on_subtitle_row_hover_requested)
        self._subtitle_list.setItemWidget(item, widget)
        # Keep size hint stable so geometry math remains predictable.
        item.setSizeHint(QSize(0, self._subtitle_row_height))
        self._attached_widget_rows.add(row)

    def _detach_subtitle_widget(self, row: int) -> None:
        if row not in self._attached_widget_rows:
            return
        item = self._subtitle_list.item(row)
        if item is not None:
            self._subtitle_list.removeItemWidget(item)
            item.setSizeHint(QSize(0, self._subtitle_row_height))
        self._attached_widget_rows.discard(row)

    def _update_subtitle_caches_in_place(self, entry: object) -> None:
        segments = getattr(entry, "segments", []) or []
        if len(segments) != len(self._subtitle_rows):
            return
        for row, (_segment_start, _segment_end, segment_text) in enumerate(segments):
            clean_text = (segment_text or "").replace("\n", " ").strip() or "-"
            if row < len(self._subtitle_text_cache):
                self._subtitle_text_cache[row] = clean_text
                self._subtitle_text_lower_cache[row] = clean_text.lower()
            else:
                self._subtitle_text_cache.append(clean_text)
                self._subtitle_text_lower_cache.append(clean_text.lower())

    def _refresh_attached_subtitle_widgets(self) -> None:
        """Push cached text into already-attached widgets without rebuilding the list."""
        for row in tuple(self._attached_widget_rows):
            item = self._subtitle_list.item(row)
            if item is None:
                continue
            widget = self._subtitle_list.itemWidget(item)
            if not isinstance(widget, _SubtitleListRowWidget):
                continue
            if 0 <= row < len(self._subtitle_text_cache):
                widget.set_text(self._subtitle_text_cache[row])

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
