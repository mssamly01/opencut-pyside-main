from __future__ import annotations

from app.controllers.app_controller import AppController
from app.domain.clips.text_clip import TextClip
from app.ui.captions_row_widget import CaptionRowWidget
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class CaptionsPanel(QWidget):
    """CapCut-like subtitle list panel."""

    def __init__(self, app_controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app_controller = app_controller
        self._refreshing = False
        self._clip_ids: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self._list_widget = QListWidget(self)
        self._list_widget.setAlternatingRowColors(True)
        self._list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._list_widget.currentRowChanged.connect(self._on_row_changed)
        self._list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list_widget)

        button_row = QHBoxLayout()
        button_row.setSpacing(4)

        self._split_button = QPushButton(self.tr("Tách"), self)
        self._split_button.setToolTip(self.tr("Tách phụ đề đang chọn tại đầu phát"))
        self._split_button.clicked.connect(self._on_split_clicked)
        button_row.addWidget(self._split_button)

        self._merge_button = QPushButton(self.tr("Gộp"), self)
        self._merge_button.setToolTip(self.tr("Gộp phụ đề đang chọn với phụ đề tiếp theo"))
        self._merge_button.clicked.connect(self._on_merge_clicked)
        button_row.addWidget(self._merge_button)

        self._duplicate_button = QPushButton(self.tr("Nhân bản"), self)
        self._duplicate_button.setToolTip(self.tr("Nhân bản phụ đề đang chọn vào ngay sau"))
        self._duplicate_button.clicked.connect(self._on_duplicate_clicked)
        button_row.addWidget(self._duplicate_button)

        self._delete_button = QPushButton(self.tr("Xóa"), self)
        self._delete_button.setToolTip(self.tr("Xóa phụ đề đang chọn"))
        self._delete_button.clicked.connect(self._on_delete_clicked)
        button_row.addWidget(self._delete_button)

        button_row.addStretch()
        layout.addLayout(button_row)

        self._app_controller.timeline_controller.timeline_changed.connect(self._refresh)
        self._app_controller.timeline_controller.timeline_edited.connect(self._refresh)
        self._app_controller.project_controller.project_changed.connect(self._refresh)
        self._app_controller.selection_controller.selection_changed.connect(self._sync_selection_from_controller)

        self._refresh()

    def _refresh(self) -> None:
        self._refreshing = True
        try:
            self._list_widget.clear()
            self._clip_ids = []
            for clip in self._app_controller.timeline_controller.caption_clips():
                item = QListWidgetItem(self._list_widget)
                item.setData(Qt.ItemDataRole.UserRole, clip.clip_id)
                item.setSizeHint(QSize(0, 32))
                row_widget = CaptionRowWidget(
                    clip=clip,
                    timestamp_label=self._format_timestamp_range(clip),
                    commit_callback=self._commit_caption_text,
                    parent=self._list_widget,
                )
                self._list_widget.setItemWidget(item, row_widget)
                self._clip_ids.append(clip.clip_id)
            self._sync_selection_from_controller()
        finally:
            self._refreshing = False

    def _sync_selection_from_controller(self) -> None:
        selected_clip_id = self._app_controller.selection_controller.selected_clip_id()
        if selected_clip_id is None or selected_clip_id not in self._clip_ids:
            self._list_widget.setCurrentRow(-1)
            return

        row = self._clip_ids.index(selected_clip_id)
        if self._list_widget.currentRow() != row:
            previous = self._refreshing
            self._refreshing = True
            try:
                self._list_widget.setCurrentRow(row)
            finally:
                self._refreshing = previous

    def _on_row_changed(self, row: int) -> None:
        if self._refreshing or row < 0 or row >= len(self._clip_ids):
            return
        clip_id = self._clip_ids[row]
        self._app_controller.selection_controller.select_clip(clip_id)
        clip = self._find_clip(clip_id)
        if isinstance(clip, TextClip):
            self._app_controller.playback_controller.seek(clip.timeline_start)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        row_widget = self._list_widget.itemWidget(item)
        if isinstance(row_widget, CaptionRowWidget):
            row_widget.begin_edit()

    def _commit_caption_text(self, clip_id: str, new_text: str) -> None:
        self._app_controller.timeline_controller.update_caption_text(clip_id, new_text)

    def _on_split_clicked(self) -> None:
        clip_id = self._current_clip_id()
        if clip_id is None:
            return
        clip = self._find_clip(clip_id)
        if not isinstance(clip, TextClip):
            return

        playhead = self._app_controller.playback_controller.current_time()
        if playhead <= clip.timeline_start or playhead >= clip.timeline_start + clip.duration:
            QMessageBox.information(
                self,
                self.tr("Tách phụ đề"),
                self.tr("Di chuyển đầu phát vào bên trong phụ đề đang chọn trước khi tách."),
            )
            return
        try:
            self._app_controller.timeline_controller.split_clip(clip_id, playhead)
        except ValueError as exc:
            QMessageBox.warning(self, self.tr("Tách phụ đề thất bại"), str(exc))

    def _on_merge_clicked(self) -> None:
        clip_id = self._current_clip_id()
        if clip_id is None:
            return
        did_merge = self._app_controller.timeline_controller.merge_caption_with_next(clip_id)
        if not did_merge:
            QMessageBox.information(
                self,
                self.tr("Gộp phụ đề"),
                self.tr("Không có phụ đề tiếp theo trên cùng track văn bản để gộp."),
            )

    def _on_duplicate_clicked(self) -> None:
        clip_id = self._current_clip_id()
        if clip_id is None:
            return
        self._app_controller.timeline_controller.duplicate_caption_clip(clip_id)

    def _on_delete_clicked(self) -> None:
        clip_id = self._current_clip_id()
        if clip_id is None:
            return
        self._app_controller.selection_controller.select_clip(clip_id)
        self._app_controller.timeline_controller.delete_selected_clip()

    def _current_clip_id(self) -> str | None:
        row = self._list_widget.currentRow()
        if row < 0 or row >= len(self._clip_ids):
            return None
        return self._clip_ids[row]

    def _find_clip(self, clip_id: str) -> TextClip | None:
        for clip in self._app_controller.timeline_controller.caption_clips():
            if clip.clip_id == clip_id:
                return clip
        return None

    @staticmethod
    def _format_timestamp_range(clip: TextClip) -> str:
        start = clip.timeline_start
        end = clip.timeline_start + clip.duration
        return f"[{CaptionsPanel._format_timestamp(start)} - {CaptionsPanel._format_timestamp(end)}]"

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        total_ms = max(0, int(round(seconds * 1000.0)))
        hours, remainder = divmod(total_ms, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        whole_seconds, milliseconds = divmod(remainder, 1_000)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"
        return f"{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"
