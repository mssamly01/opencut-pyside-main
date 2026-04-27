from __future__ import annotations

from PySide6.QtWidgets import QApplication

# Dark theme inspired by CapCut / Premiere chrome.
# Palette: #1a1d23 background, #22262d surfaces, #2c323c elevated,
# #3a4452 borders, #cdd4dc text, #7a8794 muted, #00bcd4 accent (teal).
_DARK_QSS = """
QWidget {
    background-color: #1a1d23;
    color: #cdd4dc;
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 10pt;
}
QMainWindow { background-color: #1a1d23; }
QMenuBar {
    background-color: #22262d;
    color: #cdd4dc;
    border-bottom: 1px solid #3a4452;
    padding: 2px 6px;
}
QMenuBar::item {
    padding: 4px 10px;
    border-radius: 3px;
}
QMenuBar::item:selected { background-color: #3a4452; }
QMenu {
    background-color: #22262d;
    border: 1px solid #3a4452;
    padding: 4px 0;
}
QMenu::item { padding: 5px 20px 5px 18px; }
QMenu::item:selected { background-color: #3a4452; color: #ffffff; }
QMenu::separator { height: 1px; background: #3a4452; margin: 4px 8px; }

QToolBar {
    background-color: #22262d;
    border-bottom: 1px solid #3a4452;
    padding: 4px;
    spacing: 2px;
}
QToolBar::separator {
    background-color: #3a4452;
    width: 1px;
    margin: 4px 6px;
}
QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 4px 8px;
    color: #cdd4dc;
}
QToolButton:hover { background-color: #2c323c; border-color: #3a4452; }
QToolButton:pressed { background-color: #3a4452; }
QToolButton:checked { background-color: #3a4452; border-color: #00bcd4; color: #00bcd4; }
QToolButton:disabled { color: #5c6674; }

QStatusBar {
    background-color: #22262d;
    color: #b9c2cc;
    border-top: 1px solid #3a4452;
}
QStatusBar::item { border: none; }

QPushButton {
    background-color: #2c323c;
    color: #cdd4dc;
    border: 1px solid #3a4452;
    border-radius: 4px;
    padding: 5px 12px;
}
QPushButton:hover { background-color: #3a4452; }
QPushButton:pressed { background-color: #242933; }
QPushButton:disabled { color: #5c6674; background-color: #22262d; }

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {
    background-color: #14171c;
    color: #e6edf3;
    border: 1px solid #3a4452;
    border-radius: 3px;
    padding: 3px 6px;
    selection-background-color: #00bcd4;
    selection-color: #0c0e12;
}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    background-color: #22262d;
    border: 1px solid #3a4452;
}
QComboBox::drop-down { border: none; }

QListWidget, QListView, QTreeWidget, QTreeView, QTableView {
    background-color: #14171c;
    color: #cdd4dc;
    border: 1px solid #3a4452;
    border-radius: 3px;
}
QListWidget::item, QListView::item { padding: 3px 6px; }
QListWidget::item:hover, QListView::item:hover { background-color: #2c323c; }
QListWidget::item:selected, QListView::item:selected {
    background-color: #00bcd4;
    color: #0c0e12;
}

QDockWidget {
    color: #cdd4dc;
    font-weight: 600;
    titlebar-close-icon: url(none);
}
QDockWidget::title {
    background-color: #1f2733;
    color: #f7fbff;
    padding: 6px 10px;
    border-bottom: 1px solid #283344;
}
QDockWidget::close-button, QDockWidget::float-button {
    border: none;
    background: transparent;
}

QTabWidget::pane {
    border: none;
    border-top: 1px solid #283344;
    background-color: #1a1d23;
}
QTabBar::tab {
    background: transparent;
    color: #7a8794;
    padding: 8px 16px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 0;
}
QTabBar::tab:hover { color: #c4ccd6; }
QTabBar::tab:selected { color: #f7fbff; border-bottom: 2px solid #00bcd4; }

QSlider::groove:horizontal {
    background: #14171c;
    height: 4px;
    border-radius: 2px;
}
QSlider::sub-page:horizontal { background: #00bcd4; border-radius: 2px; }
QSlider::handle:horizontal {
    background: #e6edf3;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}

QCheckBox { spacing: 6px; }
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #3a4452;
    background: #14171c;
    border-radius: 2px;
}
QCheckBox::indicator:checked { background: #00bcd4; border-color: #00bcd4; }

QScrollBar:vertical {
    background: #14171c;
    width: 10px;
    border: none;
}
QScrollBar:horizontal {
    background: #14171c;
    height: 10px;
    border: none;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #3a4452;
    border-radius: 4px;
    min-width: 20px;
    min-height: 20px;
}
QScrollBar::handle:hover { background: #5c6674; }
QScrollBar::add-line, QScrollBar::sub-line {
    background: transparent;
    border: none;
    height: 0;
    width: 0;
}

QSplitter::handle { background-color: #3a4452; }
QSplitter::handle:horizontal { width: 4px; }
QSplitter::handle:vertical { height: 4px; }

#preview_canvas {
    background-color: #0c0e12;
    border: 1px solid #3a4452;
    border-radius: 4px;
    color: #e6edf3;
    font-weight: 600;
}
#timecode_label {
    color: #00bcd4;
    font-family: "Consolas", "Menlo", monospace;
    font-size: 12pt;
    font-weight: 600;
    padding: 0 10px;
}
#dirty_indicator {
    color: #ff5a36;
    font-weight: 700;
    padding-right: 6px;
}
#top_bar {
    background-color: #14171c;
    border-bottom: 1px solid #3a4452;
}
QToolButton#top_menu_button {
    background: transparent;
    border: none;
    color: #cdd4dc;
    font-size: 14pt;
    padding: 0;
}
QToolButton#top_menu_button:hover {
    background-color: #2c323c;
    border-radius: 4px;
}
QLineEdit#top_project_name {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    color: #cdd4dc;
    font-size: 10pt;
    font-weight: 500;
    padding: 2px 8px;
}
QLineEdit#top_project_name:hover {
    background-color: #1d222a;
    border-color: #2f3946;
}
QLineEdit#top_project_name:focus {
    background-color: #12171e;
    border-color: #00bcd4;
    color: #e6edf3;
}
QPushButton#top_export_button {
    background-color: #00bcd4;
    color: #0c0e12;
    border: none;
    border-radius: 4px;
    padding: 4px 16px;
    font-weight: 600;
}
QPushButton#top_export_button:hover { background-color: #26c6da; }
QPushButton#top_export_button:pressed { background-color: #0097a7; }
#captionsPanel {
    background-color: #1a1d23;
}
QWidget#captions_left_column {
    background-color: #20242b;
}
QFrame#captions_column_separator {
    color: #343b46;
    background-color: #343b46;
    max-width: 1px;
}
QWidget#captions_right_column {
    background-color: #1a1d23;
}
QLabel#captions_content_title {
    color: #e6edf3;
    font-weight: 600;
    padding: 2px 0;
}
QLabel#captions_nav_label {
    color: #00d6e6;
    font-size: 11px;
    font-weight: 700;
    padding: 6px 8px;
}
QPushButton#captions_import_action_button {
    background-color: #00bcd4;
    color: #0e1116;
    border: none;
    border-radius: 5px;
    font-weight: 600;
    padding: 5px 10px;
}
QPushButton#captions_import_action_button:hover {
    background-color: #26c6da;
}
QPushButton#captions_import_action_button:pressed {
    background-color: #0097a7;
}
#timeline_toolbar {
    background-color: #1f242b;
    border-top: 1px solid #3a4452;
    border-bottom: 1px solid #3a4452;
}
QFrame#timeline_toolbar_sep {
    color: #3a4452;
    margin: 4px 6px;
}
QLabel#details_title {
    color: #e6edf3;
    font-size: 12pt;
    font-weight: 600;
    padding: 2px 2px 6px 2px;
}
QLineEdit#details_project_name_inline {
    background-color: transparent;
    border: none;
    border-radius: 5px;
    color: #e6edf3;
    font-size: 13pt;
    font-weight: 700;
    padding: 4px 6px;
    selection-background-color: #00bcd4;
    selection-color: #0e1116;
}
QLineEdit#details_project_name_inline:read-only:hover {
    background-color: #1d222a;
}
QLineEdit#details_project_name_inline:focus {
    background-color: #12171e;
    border: 1px solid #00bcd4;
}
QLabel#details_subtitle_title {
    color: #9eb0c0;
    font-size: 9pt;
    font-weight: 600;
    padding: 2px 2px 4px 2px;
}
QListWidget#details_subtitle_list {
    background-color: #181b20;
    border: none;
    outline: 0;
}
QListWidget#details_subtitle_list::item {
    background: transparent;
    border: none;
    margin: 0;
    padding: 1px 0;
}
QListWidget#details_subtitle_list::item:hover {
    background: transparent;
}
QListWidget#details_subtitle_list::item:selected {
    background: transparent;
    border: none;
}
QLineEdit#details_subtitle_search {
    background-color: #171a1f;
    border: 1px solid #272d36;
    border-radius: 4px;
    color: #d3dbe5;
    padding: 5px 8px;
    font-size: 11px;
}
QLineEdit#details_subtitle_search:focus {
    border-color: #00bcd4;
}
QToolButton#details_subtitle_toolbar_button {
    background-color: transparent;
    border: none;
    color: #9aa7b4;
    min-width: 20px;
    max-width: 20px;
    min-height: 20px;
    max-height: 20px;
    font-size: 11px;
    font-weight: 600;
    padding: 0;
}
QToolButton#details_subtitle_toolbar_button:hover {
    color: #d7e4f1;
}
QWidget#details_subtitle_row {
    background-color: transparent;
    border: none;
    border-bottom: 1px solid #343b46;
    border-radius: 0;
}
QWidget#details_subtitle_row[hovered="true"] {
    background-color: #2c333d;
}
QWidget#details_subtitle_row[selected="true"] {
    background-color: #2a2e33;
    border-bottom: 1px solid #3b4048;
}
QLabel#details_subtitle_row_index {
    color: #6a7380;
    font-size: 11px;
    font-weight: 600;
    min-width: 26px;
    max-width: 26px;
    border: none;
    background: transparent;
}
QWidget#details_subtitle_row[selected="true"] QLabel#details_subtitle_row_index {
    color: #00e5ff;
}
QLineEdit#details_subtitle_row_text {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    color: #d7dce4;
    padding: 2px 4px;
}
QLineEdit#details_subtitle_row_text:focus {
    background-color: #131922;
    border-color: #00bcd4;
}
QWidget#details_subtitle_row[selected="true"] QLineEdit#details_subtitle_row_text {
    color: #00e5ff;
}
QToolButton#details_subtitle_row_add,
QToolButton#details_subtitle_row_delete {
    background-color: #49505a;
    border: 1px solid #606874;
    border-radius: 3px;
    color: #e9eef5;
    min-width: 18px;
    max-width: 18px;
    min-height: 18px;
    max-height: 18px;
    padding: 0;
    font-size: 10px;
    font-weight: 700;
}
QWidget#details_subtitle_row:hover QToolButton#details_subtitle_row_add,
QWidget#details_subtitle_row:hover QToolButton#details_subtitle_row_delete,
QWidget#details_subtitle_row[selected="true"] QToolButton#details_subtitle_row_add,
QWidget#details_subtitle_row[selected="true"] QToolButton#details_subtitle_row_delete {
    background-color: #49505a;
    border-color: #606874;
    color: #e9eef5;
}
QToolButton#details_subtitle_row_add:hover {
    background-color: #00bcd4;
    color: #0d1117;
    border-color: #00bcd4;
}
QToolButton#details_subtitle_row_delete:hover {
    background-color: #f05d5d;
    border-color: #f05d5d;
}
QFrame#details_separator { color: #3a4452; }
QLabel#details_key {
    color: #7a8794;
    font-size: 9pt;
}
QLabel#details_value {
    color: #cdd4dc;
    font-size: 9pt;
}
QPushButton#inspector_toggle_button {
    background-color: transparent;
    color: #cdd4dc;
    border: 1px solid #3a4452;
    border-radius: 4px;
    padding: 4px 12px;
    font-size: 11px;
}
QPushButton#inspector_toggle_button:checked {
    background-color: #00bcd4;
    color: #0e1116;
    border-color: #00bcd4;
}
QPushButton#inspector_toggle_button:checked:disabled {
    background-color: #00bcd4;
    color: #0e1116;
    border-color: #00bcd4;
}
QPushButton#inspector_toggle_button:hover:!checked {
    background-color: #2a323d;
}
QLabel#audio_row_name {
    color: #d4dde8;
    font-size: 12px;
    padding-left: 4px;
}
QWidget#audio_row_waveform { background: transparent; }
QLabel#caption_row_timestamp {
    color: #7a8794;
    font-size: 11px;
    font-family: "Consolas", "Courier New", monospace;
    min-width: 140px;
    max-width: 140px;
}
QLineEdit#caption_row_text {
    background-color: transparent;
    color: #d4dde8;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 2px 4px;
}
QLineEdit#caption_row_text:focus {
    background-color: #1c2129;
    border-color: #00bcd4;
}
"""


def apply_basic_theme(app: QApplication) -> None:
    app.setStyleSheet(_DARK_QSS)
