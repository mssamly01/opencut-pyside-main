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
    """Subtitle library panel: import files, then load selected file to timeline."""

    def __init__(self, app_controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app_controller = app_controller
        self._refreshing = False
        self._row_keys: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QLabel(self.tr("Phụ đề"), self)
        header.setStyleSheet("font-weight: 600; color: #e6edf3; padding: 2px 0;")
        layout.addWidget(header)

        self._import_button = QPushButton(self.tr("Nhập phụ đề..."), self)
        self._import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._import_button.clicked.connect(self._on_import_clicked)
        layout.addWidget(self._import_button)

        self._list_widget = QListWidget(self)
        self._list_widget.setAlternatingRowColors(True)
        self._list_widget.setWordWrap(True)
        self._list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._list_widget.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self._list_widget)

        button_row = QHBoxLayout()
        button_row.setSpacing(4)

        self._load_button = QPushButton(self.tr("Nạp vào timeline"), self)
        self._load_button.setToolTip(self.tr("Nạp file phụ đề đã chọn vào timeline tại đầu phát"))
        self._load_button.clicked.connect(self._on_load_clicked)
        button_row.addWidget(self._load_button)

        self._remove_button = QPushButton(self.tr("Xóa khỏi danh sách"), self)
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
            self._list_widget.clear()
            self._row_keys = []
            for entry in self._app_controller.subtitle_library_entries():
                if not entry.segments:
                    continue
                start = float(entry.segments[0][0])
                end = float(entry.segments[-1][1])
                label = self.tr("[{name}] {count} đoạn - {start} đến {end}").format(
                    name=entry.source_name,
                    count=len(entry.segments),
                    start=self._format_timestamp(start),
                    end=self._format_timestamp(end),
                )
                item = QListWidgetItem(label, self._list_widget)
                item.setData(Qt.ItemDataRole.UserRole, entry.entry_id)
                item.setToolTip(self.tr("Nguồn: {path}").format(path=entry.source_path))
                item.setSizeHint(QSize(0, 30))
                self._row_keys.append(entry.entry_id)

            if not self._row_keys:
                placeholder = QListWidgetItem(self.tr("Chưa có file phụ đề đã nhập"), self._list_widget)
                placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
                placeholder.setForeground(Qt.GlobalColor.gray)

            self._sync_selection_from_controller()
        finally:
            self._refreshing = False

    def _on_import_clicked(self) -> None:
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Nhập phụ đề"),
            "",
            self.tr("Tệp phụ đề (*.srt *.vtt);;Tất cả tệp (*.*)"),
        )
        if not selected_path:
            return

        try:
            imported_count = self._app_controller.import_subtitles_from_file(selected_path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, self.tr("Nhập phụ đề thất bại"), str(exc))
            return

        if imported_count <= 0:
            QMessageBox.information(
                self,
                self.tr("Nhập phụ đề"),
                self.tr("Không có đoạn phụ đề nào được nhập."),
            )

    def _sync_selection_from_controller(self) -> None:
        selected = self._app_controller.selected_subtitle_segment()
        if selected is None:
            self._list_widget.setCurrentRow(-1)
            return

        key = selected.entry_id
        if key not in self._row_keys:
            self._list_widget.setCurrentRow(-1)
            return

        row = self._row_keys.index(key)
        if self._list_widget.currentRow() != row:
            previous = self._refreshing
            self._refreshing = True
            try:
                self._list_widget.setCurrentRow(row)
            finally:
                self._refreshing = previous

    def _on_row_changed(self, row: int) -> None:
        if self._refreshing:
            return
        if row < 0 or row >= len(self._row_keys):
            self._app_controller.select_subtitle_segment(None, None)
            return

        entry_id = self._row_keys[row]
        self._app_controller.select_subtitle_segment(entry_id, 0)
        selected = self._app_controller.selected_subtitle_segment()
        if selected is not None:
            self._app_controller.playback_controller.seek(selected.start_seconds)

    def _on_load_clicked(self) -> None:
        row = self._list_widget.currentRow()
        if row < 0 or row >= len(self._row_keys):
            return

        entry_id = self._row_keys[row]
        imported = self._app_controller.load_subtitle_entry_to_timeline(
            entry_id=entry_id,
            timeline_offset_seconds=self._app_controller.playback_controller.current_time(),
        )
        if imported <= 0:
            QMessageBox.information(
                self,
                self.tr("Nạp phụ đề"),
                self.tr("Không thể nạp phụ đề vào timeline."),
            )

    def _on_remove_clicked(self) -> None:
        row = self._list_widget.currentRow()
        if row < 0 or row >= len(self._row_keys):
            return

        entry_id = self._row_keys[row]
        entry = next((item for item in self._app_controller.subtitle_library_entries() if item.entry_id == entry_id), None)
        if entry is None:
            return

        reply = QMessageBox.question(
            self,
            self.tr("Xóa phụ đề"),
            self.tr('Xóa "{name}" khỏi danh sách phụ đề?').format(name=entry.source_name),
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
