from __future__ import annotations

from app.controllers.app_controller import AppController
from app.domain.clips.text_clip import TextClip
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
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

        self._split_button = QPushButton("Split", self)
        self._split_button.setToolTip("Split selected caption at playhead")
        self._split_button.clicked.connect(self._on_split_clicked)
        button_row.addWidget(self._split_button)

        self._merge_button = QPushButton("Merge", self)
        self._merge_button.setToolTip("Merge selected caption with the next one")
        self._merge_button.clicked.connect(self._on_merge_clicked)
        button_row.addWidget(self._merge_button)

        self._duplicate_button = QPushButton("Duplicate", self)
        self._duplicate_button.setToolTip("Duplicate selected caption after itself")
        self._duplicate_button.clicked.connect(self._on_duplicate_clicked)
        button_row.addWidget(self._duplicate_button)

        self._delete_button = QPushButton("Delete", self)
        self._delete_button.setToolTip("Delete selected caption")
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
                label = self._format_label(clip)
                item = QListWidgetItem(label, self._list_widget)
                item.setData(Qt.ItemDataRole.UserRole, clip.clip_id)
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
        clip_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(clip_id, str):
            return
        clip = self._find_clip(clip_id)
        if not isinstance(clip, TextClip):
            return

        new_text, accepted = QInputDialog.getMultiLineText(
            self,
            "Edit Caption",
            "Caption text:",
            clip.content,
        )
        if not accepted:
            return
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
                "Split Caption",
                "Move playhead inside the selected caption before splitting.",
            )
            return
        try:
            self._app_controller.timeline_controller.split_clip(clip_id, playhead)
        except ValueError as exc:
            QMessageBox.warning(self, "Split Caption Failed", str(exc))

    def _on_merge_clicked(self) -> None:
        clip_id = self._current_clip_id()
        if clip_id is None:
            return
        did_merge = self._app_controller.timeline_controller.merge_caption_with_next(clip_id)
        if not did_merge:
            QMessageBox.information(
                self,
                "Merge Caption",
                "No following caption on the same text track to merge with.",
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
    def _format_label(clip: TextClip) -> str:
        start = clip.timeline_start
        end = clip.timeline_start + clip.duration
        snippet = (clip.content or "").replace("\n", " / ").strip()
        if len(snippet) > 60:
            snippet = f"{snippet[:57]}..."
        return f"[{CaptionsPanel._format_timestamp(start)} - {CaptionsPanel._format_timestamp(end)}]  {snippet}"

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        total_ms = max(0, int(round(seconds * 1000.0)))
        hours, remainder = divmod(total_ms, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        whole_seconds, milliseconds = divmod(remainder, 1_000)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"
        return f"{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"
