from __future__ import annotations

from pathlib import Path

from app.controllers.app_controller import AppController
from app.ui.shared.icons import build_pixmap
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPixmap
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

SUBTITLE_TILE_SIZE = QSize(88, 70)


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
        self._entry_list.setViewMode(QListWidget.ViewMode.IconMode)
        self._entry_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._entry_list.setMovement(QListWidget.Movement.Static)
        self._entry_list.setSpacing(8)
        self._entry_list.setUniformItemSizes(True)
        self._entry_list.setWordWrap(True)
        self._entry_list.setIconSize(SUBTITLE_TILE_SIZE)
        self._entry_list.setGridSize(QSize(SUBTITLE_TILE_SIZE.width() + 16, SUBTITLE_TILE_SIZE.height() + 40))
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
        self._refresh()

    def _refresh(self) -> None:
        self._refreshing = True
        try:
            self._entry_list.clear()
            self._entry_row_keys = []

            for entry in self._app_controller.subtitle_library_entries():
                if not entry.segments:
                    continue
                item = QListWidgetItem(self._format_entry_label(entry.source_name), self._entry_list)
                item.setData(Qt.ItemDataRole.UserRole, entry.entry_id)
                item.setIcon(self._build_subtitle_icon(entry.source_name))
                item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
                item.setToolTip(
                    self.tr("{name}\n{count} lines\nSource: {path}").format(
                        name=entry.source_name,
                        count=len(entry.segments),
                        path=entry.source_path,
                    )
                )
                item.setSizeHint(QSize(SUBTITLE_TILE_SIZE.width() + 14, SUBTITLE_TILE_SIZE.height() + 36))
                self._entry_row_keys.append(entry.entry_id)

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
        entry_id = self._resolve_current_entry_id()
        if entry_id is None:
            return
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
        entry_id = self._resolve_current_entry_id()
        if entry_id is None:
            return
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

        if not self._app_controller.remove_subtitle_entry(entry_id):
            QMessageBox.information(
                self,
                self.tr("Remove subtitle file"),
                self.tr("Could not remove subtitle file from list."),
            )

    def _resolve_current_entry_id(self) -> str | None:
        row = self._entry_list.currentRow()
        if 0 <= row < len(self._entry_row_keys):
            return self._entry_row_keys[row]

        selected = self._app_controller.selected_subtitle_segment()
        if selected is not None and selected.entry_id in self._entry_row_keys:
            return selected.entry_id

        if len(self._entry_row_keys) == 1:
            return self._entry_row_keys[0]
        return None

    @staticmethod
    def _format_entry_label(source_name: str) -> str:
        base = Path(source_name or "").name or "subtitle.srt"
        if len(base) <= 16:
            return base
        return base[:13] + "..."

    @staticmethod
    def _build_subtitle_icon(source_name: str) -> QIcon:
        ext = Path(source_name or "").suffix.lower().lstrip(".")
        badge_text = (ext.upper() if ext else "SUB")[:4]

        canvas = QPixmap(SUBTITLE_TILE_SIZE)
        canvas.fill(Qt.GlobalColor.transparent)

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        card_rect = canvas.rect().adjusted(1, 1, -1, -1)
        painter.setPen(QColor("#3a4452"))
        painter.setBrush(QBrush(QColor("#2a313b")))
        painter.drawRoundedRect(card_rect, 8, 8)

        inner_rect = card_rect.adjusted(18, 8, -18, -16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#22c7d8")))
        painter.drawRoundedRect(inner_rect, 6, 6)

        glyph = build_pixmap("subtitle", 30, "#0f252a")
        glyph_x = inner_rect.left() + (inner_rect.width() - glyph.width()) // 2
        glyph_y = inner_rect.top() + 2
        painter.drawPixmap(glyph_x, glyph_y, glyph)

        badge_rect = QRect(inner_rect.left() + 6, inner_rect.bottom() - 14, inner_rect.width() - 12, 13)
        painter.setBrush(QBrush(QColor("#0f252a")))
        painter.drawRoundedRect(badge_rect, 4, 4)
        painter.setPen(QColor("#7ef5ff"))
        badge_font = QFont()
        badge_font.setPointSize(7)
        badge_font.setBold(True)
        painter.setFont(badge_font)
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

        painter.end()
        return QIcon(canvas)
