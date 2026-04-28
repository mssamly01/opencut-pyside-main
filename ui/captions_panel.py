from __future__ import annotations

from pathlib import Path

from app.controllers.app_controller import AppController
from app.ui.shared.icons import build_pixmap
from PySide6.QtCore import QEvent, QRect, QSize, Qt, QUrl
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
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

SUBTITLE_TILE_SIZE = QSize(88, 70)
CAPTIONS_NAV_COLUMN_WIDTH = 112


class CaptionsPanel(QWidget):
    """Subtitle rail panel: list subtitle files only."""

    def __init__(self, app_controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("captionsPanel")
        self._app_controller = app_controller
        self._refreshing = False
        self._nav_mode = "import"
        self._entry_row_keys: list[str] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        left_column = QWidget(self)
        left_column.setObjectName("captions_left_column")
        left_column.setFixedWidth(CAPTIONS_NAV_COLUMN_WIDTH)
        left_layout = QVBoxLayout(left_column)
        left_layout.setContentsMargins(8, 10, 8, 10)
        left_layout.setSpacing(8)

        self._import_nav_label = QLabel(self.tr("Nhập"), left_column)
        self._import_nav_label.setObjectName("captions_nav_label")
        self._import_nav_label.setProperty("active", True)
        self._import_nav_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._import_nav_label.installEventFilter(self)
        left_layout.addWidget(self._import_nav_label)

        self._functions_nav_label = QLabel(self.tr("Chức năng"), left_column)
        self._functions_nav_label.setObjectName("captions_nav_label")
        self._functions_nav_label.setProperty("active", False)
        self._functions_nav_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._functions_nav_label.installEventFilter(self)
        left_layout.addWidget(self._functions_nav_label)
        left_layout.addStretch(1)

        separator = QFrame(self)
        separator.setObjectName("captions_column_separator")
        separator.setFrameShape(QFrame.Shape.VLine)

        right_column = QWidget(self)
        right_column.setObjectName("captions_right_column")
        right_layout = QVBoxLayout(right_column)
        right_layout.setContentsMargins(10, 10, 8, 8)
        right_layout.setSpacing(6)

        self._action_stack = QStackedWidget(right_column)
        right_layout.addWidget(self._action_stack, 1)

        import_page = QWidget(self._action_stack)
        import_page.setObjectName("captions_import_page")
        import_layout = QVBoxLayout(import_page)
        import_layout.setContentsMargins(0, 0, 0, 0)
        import_layout.setSpacing(0)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)

        header = QLabel(self.tr("Tất cả"), import_page)
        header.setObjectName("captions_content_title")
        top_row.addWidget(header)

        self._import_button = QPushButton(self.tr("Nhập phụ đề"), import_page)
        self._import_button.setObjectName("captions_import_action_button")
        self._import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._import_button.clicked.connect(self._on_import_clicked)
        top_row.addStretch(1)
        top_row.addWidget(self._import_button)
        import_layout.addLayout(top_row)
        import_layout.addSpacing(12)

        self._entry_list = QListWidget(import_page)
        self._entry_list.setObjectName("captions_entry_list")
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
        import_layout.addWidget(self._entry_list, 1)
        
        # Placeholder label inside the list's viewport
        self.placeholder_label = QLabel(self.tr("Chưa nhập phụ đề"), self._entry_list.viewport())
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_label.setStyleSheet("color: gray; background-color: transparent;")
        self.placeholder_label.setVisible(False)
        
        # Center the label when the list is resized
        self._entry_list.viewport().installEventFilter(self)

        self._action_stack.addWidget(import_page)

        functions_page = QWidget(self._action_stack)
        functions_page.setObjectName("captions_functions_page")
        functions_page_layout = QVBoxLayout(functions_page)
        functions_page_layout.setContentsMargins(0, 0, 0, 0)
        functions_page_layout.setSpacing(8)

        self._functions_table = QFrame(functions_page)
        self._functions_table.setObjectName("captions_functions_table")
        functions_layout = QVBoxLayout(self._functions_table)
        functions_layout.setContentsMargins(8, 8, 8, 8)
        functions_layout.setSpacing(6)

        self._filter_ocr_button = QPushButton(self.tr("Lọc lỗi OCR"), self._functions_table)
        self._filter_ocr_button.setObjectName("captions_function_action_button")
        self._filter_ocr_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._filter_ocr_button.clicked.connect(self._on_filter_ocr_clicked)
        functions_layout.addWidget(self._filter_ocr_button)

        self._filter_duplicate_button = QPushButton(
            self.tr("Lọc phụ đề trùng lặp"), self._functions_table
        )
        self._filter_duplicate_button.setObjectName("captions_function_action_button")
        self._filter_duplicate_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._filter_duplicate_button.clicked.connect(self._on_filter_duplicate_clicked)
        functions_layout.addWidget(self._filter_duplicate_button)

        self._remove_interjection_button = QPushButton(
            self.tr("Xóa từ cảm thán"), self._functions_table
        )
        self._remove_interjection_button.setObjectName("captions_function_action_button")
        self._remove_interjection_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._remove_interjection_button.clicked.connect(self._on_remove_interjection_clicked)
        functions_layout.addWidget(self._remove_interjection_button)
        functions_layout.addStretch(1)
        functions_page_layout.addWidget(self._functions_table, 1)
        self._action_stack.addWidget(functions_page)

        layout.addWidget(left_column)
        layout.addWidget(separator)
        layout.addWidget(right_column, 1)

        self._app_controller.subtitle_library_changed.connect(self._refresh)
        self._app_controller.subtitle_selection_changed.connect(self._sync_selection_from_controller)
        self._set_nav_mode("import")
        self._refresh()

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            if watched is self._import_nav_label:
                self._set_nav_mode("import")
                return True
            if watched is self._functions_nav_label:
                self._set_nav_mode("functions")
                return True
        elif watched is self._entry_list.viewport() and event.type() == QEvent.Type.Resize:
            self.placeholder_label.resize(event.size())
            
        return super().eventFilter(watched, event)

    def _set_nav_mode(self, mode: str) -> None:
        normalized = "functions" if mode == "functions" else "import"
        if self._nav_mode == normalized and self._action_stack.currentIndex() >= 0:
            return
        self._nav_mode = normalized
        self._action_stack.setCurrentIndex(0 if normalized == "import" else 1)
        self._set_nav_label_active(self._import_nav_label, normalized == "import")
        self._set_nav_label_active(self._functions_nav_label, normalized == "functions")

    @staticmethod
    def _set_nav_label_active(label: QLabel, active: bool) -> None:
        if bool(label.property("active")) == bool(active):
            return
        label.setProperty("active", bool(active))
        style = label.style()
        style.unpolish(label)
        style.polish(label)
        label.update()

    def _refresh(self) -> None:
        self._refreshing = True
        try:
            self._entry_list.clear()
            self._entry_row_keys = []
            
            entries = list(self._app_controller.subtitle_library_entries())
            if not entries:
                self.placeholder_label.setVisible(True)
                self.placeholder_label.resize(self._entry_list.viewport().size())
                return

            self.placeholder_label.setVisible(False)
            for entry in entries:
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

    def _ensure_subtitle_selected(self) -> bool:
        selected = self._app_controller.selected_subtitle_segment()
        if selected is not None:
            return True
        if not self._entry_row_keys:
            QMessageBox.information(
                self,
                self.tr("Chức năng phụ đề"),
                self.tr("Chưa có phụ đề để xử lý."),
            )
            return False

        current_row = self._entry_list.currentRow()
        if current_row < 0 or current_row >= len(self._entry_row_keys):
            current_row = 0
            self._entry_list.setCurrentRow(current_row)
        self._app_controller.select_subtitle_segment(self._entry_row_keys[current_row], 0)
        return True

    def _on_filter_ocr_clicked(self) -> None:
        if not self._ensure_subtitle_selected():
            return
        self._app_controller.request_subtitle_quality_filter("ocr")

    def _on_filter_duplicate_clicked(self) -> None:
        if not self._ensure_subtitle_selected():
            return
        self._app_controller.request_subtitle_quality_filter("duplicate")

    def _on_remove_interjection_clicked(self) -> None:
        if not self._ensure_subtitle_selected():
            return
        self._app_controller.request_subtitle_interjection_cleanup()

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
