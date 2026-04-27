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
