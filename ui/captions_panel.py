from __future__ import annotations

from pathlib import Path

from app.controllers.app_controller import AppController
from app.ui.shared.icons import build_pixmap
from PySide6.QtCore import QRect, QSize, Qt, QUrl
from PySide6.QtGui import QAction, QBrush, QColor, QDesktopServices, QFont, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
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
        self.setObjectName("captionsPanel")
        self._app_controller = app_controller
        self._refreshing = False
        self._entry_row_keys: list[str] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        left_column = QWidget(self)
        left_column.setObjectName("captions_left_column")
        left_column.setFixedWidth(92)
        left_layout = QVBoxLayout(left_column)
        left_layout.setContentsMargins(8, 10, 8, 10)
        left_layout.setSpacing(8)

        self._import_nav_label = QLabel(self.tr("Nhập"), left_column)
        self._import_nav_label.setObjectName("captions_nav_label")
        left_layout.addWidget(self._import_nav_label)
        left_layout.addStretch(1)

        separator = QFrame(self)
        separator.setObjectName("captions_column_separator")
        separator.setFrameShape(QFrame.Shape.VLine)

        right_column = QWidget(self)
        right_column.setObjectName("captions_right_column")
        right_layout = QVBoxLayout(right_column)
        right_layout.setContentsMargins(10, 10, 8, 8)
        right_layout.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)

        header = QLabel(self.tr("Tất cả"), right_column)
        header.setObjectName("captions_content_title")
        top_row.addWidget(header)

        self._import_button = QPushButton(self.tr("Nhập phụ đề..."), right_column)
        self._import_button.setObjectName("captions_import_action_button")
        self._import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._import_button.clicked.connect(self._on_import_clicked)
        top_row.addStretch(1)
        top_row.addWidget(self._import_button)
        right_layout.addLayout(top_row)

        self._entry_list = QListWidget(right_column)
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
        self._entry_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._entry_list.customContextMenuRequested.connect(self._on_context_menu_requested)
        right_layout.addWidget(self._entry_list, 1)

        layout.addWidget(left_column)
        layout.addWidget(separator)
        layout.addWidget(right_column, 1)

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

    def _on_context_menu_requested(self, position) -> None:
        item = self._entry_list.itemAt(position)
        if item is None:
            return

        entry_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(entry_id, str):
            return
        entry = self._find_entry(entry_id)
        if entry is None:
            return

        if self._entry_list.currentItem() is not item:
            self._entry_list.setCurrentItem(item)

        menu = QMenu(self._entry_list)
        reveal_action = QAction(self.tr("Hiện trong thư mục"), menu)
        copy_path_action = QAction(self.tr("Sao chép đường dẫn tệp"), menu)
        remove_action = QAction(self.tr("Xóa khỏi danh sách"), menu)
        menu.addAction(reveal_action)
        menu.addAction(copy_path_action)
        menu.addSeparator()
        menu.addAction(remove_action)

        triggered = menu.exec(self._entry_list.viewport().mapToGlobal(position))
        if triggered == reveal_action:
            self._reveal_in_folder(entry.source_path)
        elif triggered == copy_path_action:
            self._copy_file_path(entry.source_path)
        elif triggered == remove_action:
            self._remove_entry(entry_id)

    def _remove_entry(self, entry_id: str) -> None:
        entry = self._find_entry(entry_id)
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

    def _find_entry(self, entry_id: str):
        return next((item for item in self._app_controller.subtitle_library_entries() if item.entry_id == entry_id), None)

    def _resolve_source_path(self, source_path: str) -> Path:
        path = Path(source_path).expanduser()
        if path.is_absolute():
            return path.resolve()
        project_path = self._app_controller.project_controller.active_project_path()
        if project_path is not None:
            return (Path(project_path).resolve().parent / path).resolve()
        return path.resolve()

    def _reveal_in_folder(self, source_path: str) -> None:
        resolved = self._resolve_source_path(source_path)
        if resolved.exists():
            target = resolved if resolved.is_dir() else resolved.parent
        else:
            target = resolved.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    @staticmethod
    def _copy_file_path(source_path: str) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(source_path)

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
