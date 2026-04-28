from __future__ import annotations

from PySide6.QtWidgets import QApplication

# Dark theme inspired by CapCut / Premiere chrome.
# Palette layers:
# - App background: #141414
# - Main panels (suil / preview / details): #303030
# - Inner suil details: #262626
# - Elevated controls: #2f333a
# - Borders: #30353d
# - Text: #d6d9df, muted #8d939d, accent #16d3e2
_DARK_QSS = """
QWidget {
    background-color: #141414;
    color: #d6d9df;
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 10pt;
}
QMainWindow { background-color: #141414; }
QMenuBar {
    background-color: #24262b;
    color: #d6d9df;
    border-bottom: 1px solid #30353d;
    padding: 2px 6px;
}
QMenuBar::item {
    padding: 4px 10px;
    border-radius: 3px;
}
QMenuBar::item:selected { background-color: #30353d; }
QMenu {
    background-color: #24262b;
    border: 1px solid #30353d;
    padding: 4px 0;
}
QMenu::item { padding: 5px 20px 5px 18px; }
QMenu::item:selected { background-color: #30353d; color: #ffffff; }
QMenu::separator { height: 1px; background: #30353d; margin: 4px 8px; }

QToolBar {
    background-color: #24262b;
    border-bottom: 1px solid #30353d;
    padding: 4px;
    spacing: 2px;
}
QToolBar::separator {
    background-color: #30353d;
    width: 1px;
    margin: 4px 6px;
}
QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 4px 8px;
    color: #d6d9df;
}
QToolButton:hover { background-color: #2f333a; border-color: #30353d; }
QToolButton:pressed { background-color: #30353d; }
QToolButton:checked { background-color: #30353d; border-color: #16d3e2; color: #16d3e2; }
QToolButton:disabled { color: #666c75; }

QStatusBar {
    background-color: #24262b;
    color: #bfc5ce;
    border-top: 1px solid #30353d;
}
QStatusBar::item { border: none; }

QPushButton {
    background-color: #2f333a;
    color: #d6d9df;
    border: 1px solid #30353d;
    border-radius: 4px;
    padding: 5px 12px;
}
QPushButton:hover { background-color: #30353d; }
QPushButton:pressed { background-color: #272b31; }
QPushButton:disabled { color: #666c75; background-color: #24262b; }

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {
    background-color: #17191d;
    color: #e8ebef;
    border: 1px solid #30353d;
    border-radius: 3px;
    padding: 3px 6px;
    selection-background-color: #16d3e2;
    selection-color: #0f1114;
}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    background-color: #24262b;
    border: 1px solid #30353d;
}
QComboBox::drop-down { border: none; }

QListWidget, QListView, QTreeWidget, QTreeView, QTableView {
    background-color: #17191d;
    color: #d6d9df;
    border: 1px solid #30353d;
    border-radius: 3px;
}
QListWidget::item, QListView::item { padding: 3px 6px; }
QListWidget::item:hover, QListView::item:hover { background-color: #2f333a; }
QListWidget::item:selected, QListView::item:selected {
    background-color: #16d3e2;
    color: #0f1114;
}

QDockWidget {
    color: #d6d9df;
    font-weight: 600;
    titlebar-close-icon: url(none);
}
QDockWidget::title {
    background-color: #20262f;
    color: #f2f4f7;
    padding: 6px 10px;
    border-bottom: 1px solid #2f3742;
}
QDockWidget::close-button, QDockWidget::float-button {
    border: none;
    background: transparent;
}

QTabWidget::pane {
    border: none;
    border-top: 1px solid #2f3742;
    background-color: #1b1c1f;
}
QTabBar::tab {
    background: transparent;
    color: #8d939d;
    padding: 8px 16px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 0;
}
QTabBar::tab:hover { color: #c6ccd5; }
QTabBar::tab:selected { color: #f2f4f7; border-bottom: 2px solid #16d3e2; }

QSlider::groove:horizontal {
    background: #17191d;
    height: 4px;
    border-radius: 2px;
}
QSlider::sub-page:horizontal { background: #16d3e2; border-radius: 2px; }
QSlider::handle:horizontal {
    background: #e8ebef;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}

QCheckBox { spacing: 6px; }
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #30353d;
    background: #17191d;
    border-radius: 2px;
}
QCheckBox::indicator:checked { background: #16d3e2; border-color: #16d3e2; }

QScrollBar:vertical {
    background: #17191d;
    width: 10px;
    border: none;
}
QScrollBar:horizontal {
    background: #17191d;
    height: 10px;
    border: none;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #30353d;
    border-radius: 4px;
    min-width: 20px;
    min-height: 20px;
}
QScrollBar::handle:hover { background: #666c75; }
QScrollBar::add-line, QScrollBar::sub-line {
    background: transparent;
    border: none;
    height: 0;
    width: 0;
}

QSplitter::handle { background-color: #141414; }
QSplitter::handle:horizontal { width: 4px; }
QSplitter::handle:vertical { height: 4px; }
#workspace_top_splitter::handle:horizontal {
    width: 6px;
    background-color: #141414;
}
#workspace_root_splitter::handle:vertical {
    height: 6px;
    background-color: #141414;
}
QWidget#workspace_left_region_container,
QWidget#workspace_center_region_container,
QWidget#workspace_right_region_container {
    background-color: #262626;
}
QWidget#workspace_preview_region {
    background-color: #262626;
}
QWidget#workspace_inspector_region,
QWidget#workspace_inspector_region QScrollArea,
QWidget#workspace_inspector_region QScrollArea > QWidget,
DetailsInspector,
DetailsInspector QWidget {
    background-color: #262626;
    border: none;
}
QWidget#workspace_timeline_region {
    background-color: #22242a;
    border: none;
}
QWidget#workspace_region_header {
    background-color: #303030;
    border: none;
    min-height: 56px;
    max-height: 56px;
}
QLabel#workspace_region_header_title {
    background-color: transparent;
    color: #d6d9df;
    font-size: 13px;
    font-weight: 600;
}
QLabel#workspace_region_header_title[accent="true"] {
    background-color: transparent;
    color: #16d3e2;
}

#preview_canvas {
    background-color: #262626;
    border: none;
    border-radius: 2px;
    color: #e8ebef;
    font-weight: 600;
}
#timecode_label {
    color: #16d3e2;
    font-family: "Consolas", "Menlo", monospace;
    font-size: 12pt;
    font-weight: 600;
    padding: 0 10px;
}
#dirty_indicator {
    color: #ff6d4a;
    font-weight: 700;
    padding-right: 6px;
}
#top_bar {
    background-color: #111317;
    border-bottom: 1px solid #2a2d33;
}
QToolButton#top_menu_button {
    background: transparent;
    border: none;
    color: #d6d9df;
    font-size: 14pt;
    padding: 0;
}
QToolButton#top_menu_button:hover {
    background-color: #2f333a;
    border-radius: 4px;
}
QLineEdit#top_project_name {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    color: #d6d9df;
    font-size: 10pt;
    font-weight: 500;
    padding: 2px 8px;
}
QLineEdit#top_project_name:hover {
    background-color: #1f2228;
    border-color: #343840;
}
QLineEdit#top_project_name:focus {
    background-color: #171b20;
    border-color: #16d3e2;
    color: #e8ebef;
}
QPushButton#top_export_button {
    background-color: #16d3e2;
    color: #0f1114;
    border: none;
    border-radius: 4px;
    padding: 4px 16px;
    font-weight: 600;
}
QPushButton#top_export_button:hover { background-color: #25d9e6; }
QPushButton#top_export_button:pressed { background-color: #0ca6b3; }
#left_sidebar {
    background-color: #303030;
}
QWidget#left_sidebar_rail_region {
    background-color: #303030;
    min-height: 56px;
    max-height: 56px;
}
QWidget#left_sidebar_rail_detail_gap {
    background-color: #141414;
    min-height: 3px;
    max-height: 3px;
}
QScrollArea#leftRailScroll {
    background-color: #303030;
    border: none;
}
QWidget#leftRailViewport {
    background-color: #303030;
    border: none;
}
QWidget#leftRail {
    background-color: #303030;
}
QFrame#left_sidebar_region_separator {
    color: transparent;
    background-color: transparent;
    max-height: 0px;
}
QWidget#left_sidebar_body_region {
    background-color: #262626;
}
#captionsPanel {
    background-color: #262626;
}
QWidget#captions_left_column {
    background-color: #303030;
}
QFrame#captions_column_separator {
    color: transparent;
    background-color: transparent;
    max-width: 0px;
}
QWidget#captions_right_column {
    background-color: #262626;
}
QWidget#captions_import_page {
    background-color: #262626;
}
QListWidget#captions_entry_list {
    background-color: #262626;
    border: none;
    border-radius: 0px;
}
QWidget#captions_functions_page {
    background-color: #262626;
    border: none;
    border-radius: 0px;
}
QLabel#captions_content_title {
    color: #e8ebef;
    background-color: transparent;
    border: none;
    font-weight: 600;
    padding: 2px 0;
}
QLabel#captions_nav_label {
    color: #8f96a1;
    border: 1px solid transparent;
    border-radius: 5px;
    font-size: 11px;
    font-weight: 700;
    padding: 6px 8px;
}
QLabel#captions_nav_label[active="true"] {
    color: #16d3e2;
    background-color: #1e2730;
}
QLabel#captions_nav_label[active="false"] {
    color: #e0dedb;
    background-color: #3b3b3b;
}
QPushButton#captions_import_action_button {
    background-color: #16d3e2;
    color: #0e1116;
    border: none;
    border-radius: 5px;
    font-weight: 600;
    padding: 5px 10px;
}
QPushButton#captions_import_action_button:hover {
    background-color: #25d9e6;
}
QPushButton#captions_import_action_button:pressed {
    background-color: #0ca6b3;
}
QFrame#captions_functions_table {
    background-color: transparent;
    border: none;
    border-radius: 6px;
}
QPushButton#captions_function_action_button {
    background-color: #273641;
    color: #d8e6f3;
    border: 1px solid #3a5668;
    border-radius: 5px;
    font-size: 11px;
    font-weight: 600;
    padding: 4px 8px;
}
QPushButton#captions_function_action_button:hover {
    background-color: #2c4156;
    border-color: #486f86;
}
QPushButton#captions_function_action_button:pressed {
    background-color: #25333e;
    border-color: #486f86;
}
#timeline_toolbar {
    background-color: #252830;
    border: none;
}
QFrame#timeline_toolbar_sep {
    color: #30353d;
    margin: 4px 6px;
}
QLabel#details_title {
    color: #e8ebef;
    font-size: 12pt;
    font-weight: 600;
    padding: 2px 2px 6px 2px;
}
QLineEdit#details_project_name_inline {
    background-color: transparent;
    border: none;
    border-radius: 5px;
    color: #e8ebef;
    font-size: 13pt;
    font-weight: 700;
    padding: 4px 6px;
    selection-background-color: #16d3e2;
    selection-color: #0e1116;
}
QLineEdit#details_project_name_inline:read-only:hover {
    background-color: #1f2228;
}
QLineEdit#details_project_name_inline:focus {
    background-color: #171b20;
    border: 1px solid #16d3e2;
}
QLabel#details_subtitle_title {
    color: #a0a8b2;
    font-size: 9pt;
    font-weight: 600;
    padding: 2px 2px 4px 2px;
}
QListWidget#details_subtitle_list {
    background-color: #1a1d22;
    border: 1px solid #343840;
    border-radius: 4px;
    font-size: 11pt;
    outline: 0;
}
QListWidget#details_subtitle_list::item {
    background: transparent;
    border: none;
    margin: 0;
    padding: 0;
}
QListWidget#details_subtitle_list::item:hover {
    background: transparent;
}
QListWidget#details_subtitle_list::item:selected {
    background: transparent;
    border: none;
}
QLineEdit#details_subtitle_search {
    background-color: #1a1d22;
    border: 1px solid #343840;
    border-radius: 5px;
    color: #d9dde5;
    padding: 5px 8px;
    font-size: 11px;
}
QLineEdit#details_subtitle_search:focus {
    border-color: #25d9e6;
}
QToolButton#details_subtitle_toolbar_button {
    background-color: transparent;
    border: none;
    color: #97a0ab;
    min-width: 20px;
    max-width: 20px;
    min-height: 20px;
    max-height: 20px;
    font-size: 11px;
    font-weight: 600;
    padding: 0;
}
QToolButton#details_subtitle_toolbar_button:hover {
    color: #dde2ea;
}
QWidget#details_subtitle_row {
    background-color: transparent;
    border: none;
    border-bottom: 1px solid #343840;
    border-radius: 0;
}
QWidget#details_subtitle_row[hovered="true"] {
    background-color: #202730;
}
QWidget#details_subtitle_row[selected="true"] {
    background-color: #242b34;
    border-bottom: 1px solid #455161;
}
QLabel#details_subtitle_row_index {
    color: #919aa5;
    font-size: 11px;
    font-weight: 600;
    min-width: 26px;
    max-width: 26px;
    border: none;
    background: transparent;
    padding-right: 2px;
}
QWidget#details_subtitle_row[selected="true"] QLabel#details_subtitle_row_index {
    color: #25d9e6;
}
QPlainTextEdit#details_subtitle_row_text {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    color: #dde2e9;
    padding: 0px 3px;
}
QPlainTextEdit#details_subtitle_row_text:focus {
    background-color: #151a21;
    border-color: #25d9e6;
}
QWidget#details_subtitle_row[selected="true"] QPlainTextEdit#details_subtitle_row_text {
    color: #25d9e6;
}
QToolButton#details_subtitle_row_add,
QToolButton#details_subtitle_row_delete {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    color: #99a2ad;
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
    background-color: #2b3641;
    border-color: #455160;
    color: #dee3ea;
}
QToolButton#details_subtitle_row_add:hover {
    background-color: #27d8e5;
    color: #0e141d;
    border-color: #27d8e5;
}
QToolButton#details_subtitle_row_delete:hover {
    background-color: #e56a66;
    border-color: #e56a66;
    color: #f2f4f7;
}
QFrame#details_separator { color: #30353d; }
QLabel#details_key {
    color: #8d939d;
    font-size: 9pt;
}
QLabel#details_value {
    color: #d6d9df;
    font-size: 9pt;
}
QPushButton#inspector_toggle_button {
    background-color: transparent;
    color: #d6d9df;
    border: 1px solid #30353d;
    border-radius: 4px;
    padding: 4px 12px;
    font-size: 11px;
}
QPushButton#inspector_toggle_button:checked {
    background-color: #16d3e2;
    color: #0e1116;
    border-color: #16d3e2;
}
QPushButton#inspector_toggle_button:checked:disabled {
    background-color: #16d3e2;
    color: #0e1116;
    border-color: #16d3e2;
}
QPushButton#inspector_toggle_button:hover:!checked {
    background-color: #2f343c;
}
QLabel#audio_row_name {
    color: #d4dde8;
    font-size: 12px;
    padding-left: 4px;
}
QWidget#audio_row_waveform { background: transparent; }
QLabel#caption_row_timestamp {
    color: #8d939d;
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
    background-color: #1f2329;
    border-color: #16d3e2;
}
"""


def apply_basic_theme(app: QApplication) -> None:
    app.setStyleSheet(_DARK_QSS)
