from __future__ import annotations

from app.controllers.app_controller import AppController
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class CaptionsPanel(QWidget):
    """Subtitle rail panel: list subtitle files only."""

    def __init__(self, app_controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app_controller = app_controller
        self._refreshing = False
        self._entry_row_keys: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QLabel(self.tr("Subtitles"), self)
        header.setStyleSheet("font-weight: 600; color: #e6edf3; padding: 2px 0;")
        layout.addWidget(header)

        self._import_button = QPushButton(self.tr("Import subtitles..."), self)
        self._import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._import_button.clicked.connect(self._on_import_clicked)
        layout.addWidget(self._import_button)

        self._entry_list = QListWidget(self)
        self._entry_list.setAlternatingRowColors(True)
        self._entry_list.setWordWrap(True)
        self._entry_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._entry_list.currentRowChanged.connect(self._on_entry_row_changed)
        layout.addWidget(self._entry_list, 1)

        button_row = QHBoxLayout()
        button_row.setSpacing(4)

        self._load_button = QPushButton(self.tr("Load to timeline"), self)
        self._load_button.setToolTip(self.tr("Load selected subtitle file at current playhead"))
        self._load_button.clicked.connect(self._on_load_clicked)
        button_row.addWidget(self._load_button)

        self._remove_button = QPushButton(self.tr("Remove"), self)
        self._remove_button.clicked.connect(self._on_remove_clicked)
        button_row.addWidget(self._remove_button)

        button_row.addStretch()
        layout.addLayout(button_row)

        self._app_controller.subtitle_library_changed.connect(self._refresh)
        self._app_controller.subtitle_selection_changed.connect(self._sync_selection_from_controller)
        self._app_controller.project_controller.project_changed.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        self._refreshing = True
        try:
            self._entry_list.clear()
            self._entry_row_keys = []

            for entry in self._app_controller.subtitle_library_entries():
                if not entry.segments:
                    continue
                start = float(entry.segments[0][0])
                end = float(entry.segments[-1][1])
                label = self.tr("[{name}] {count} lines  {start} - {end}").format(
                    name=entry.source_name,
                    count=len(entry.segments),
                    start=self._format_timestamp(start),
                    end=self._format_timestamp(end),
                )
                item = QListWidgetItem(label, self._entry_list)
                item.setData(Qt.ItemDataRole.UserRole, entry.entry_id)
                item.setToolTip(self.tr("Source: {path}").format(path=entry.source_path))
                item.setSizeHint(QSize(0, 30))
                self._entry_row_keys.append(entry.entry_id)

            if not self._entry_row_keys:
                placeholder = QListWidgetItem(self.tr("No subtitle files imported"), self._entry_list)
                placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
                placeholder.setForeground(Qt.GlobalColor.gray)

            self._sync_selection_from_controller()
        finally:
            self._refreshing = False

    def _on_import_clicked(self) -> None:
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Import subtitles"),
            "",
            self.tr("Subtitle files (*.srt *.vtt);;All files (*.*)"),
        )
        if not selected_path:
            return

        try:
            imported_count = self._app_controller.import_subtitles_from_file(selected_path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, self.tr("Subtitle import failed"), str(exc))
            return

        if imported_count <= 0:
            QMessageBox.information(
                self,
                self.tr("Import subtitles"),
                self.tr("No subtitle lines were imported."),
            )

    def _sync_selection_from_controller(self) -> None:
        selected = self._app_controller.selected_subtitle_segment()
        selected_entry_id = selected.entry_id if selected is not None else None

        previous_refreshing = self._refreshing
        self._refreshing = True
        try:
            if selected_entry_id is None or selected_entry_id not in self._entry_row_keys:
                self._entry_list.setCurrentRow(-1)
                return
            entry_row = self._entry_row_keys.index(selected_entry_id)
            if self._entry_list.currentRow() != entry_row:
                self._entry_list.setCurrentRow(entry_row)
        finally:
            self._refreshing = previous_refreshing

    def _on_entry_row_changed(self, row: int) -> None:
        if self._refreshing:
            return
        if row < 0 or row >= len(self._entry_row_keys):
            self._app_controller.select_subtitle_segment(None, None)
            return

        entry_id = self._entry_row_keys[row]
        self._app_controller.select_subtitle_segment(entry_id, 0)

    def _on_load_clicked(self) -> None:
        row = self._entry_list.currentRow()
        if row < 0 or row >= len(self._entry_row_keys):
            return

        entry_id = self._entry_row_keys[row]
        imported = self._app_controller.load_subtitle_entry_to_timeline(
            entry_id=entry_id,
            timeline_offset_seconds=self._app_controller.playback_controller.current_time(),
        )
        if imported <= 0:
            QMessageBox.information(
                self,
                self.tr("Load subtitles"),
                self.tr("Could not load subtitles into timeline."),
            )

    def _on_remove_clicked(self) -> None:
        row = self._entry_list.currentRow()
        if row < 0 or row >= len(self._entry_row_keys):
            return

        entry_id = self._entry_row_keys[row]
        entry = next((item for item in self._app_controller.subtitle_library_entries() if item.entry_id == entry_id), None)
        if entry is None:
            return

        reply = QMessageBox.question(
            self,
            self.tr("Remove subtitle file"),
            self.tr('Remove "{name}" from subtitle list?').format(name=entry.source_name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._app_controller.remove_subtitle_entry(entry_id)

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        total_ms = max(0, int(round(seconds * 1000.0)))
        hours, remainder = divmod(total_ms, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        whole_seconds, milliseconds = divmod(remainder, 1_000)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"
        return f"{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"
