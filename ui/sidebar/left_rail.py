from __future__ import annotations

from collections.abc import Iterable

from app.ui.shared.icons import build_icon
from PySide6.QtCore import QCoreApplication, QSize, Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QToolButton, QWidget

# Keep ordering stable: index maps to LeftSidebarStack page index.
# Labels are translated lazily via QCoreApplication.translate so they pick up
# the active QTranslator at widget-build time.
RAIL_CATEGORIES: list[tuple[str, str, str]] = [
    ("media", "Phương tiện", "rail-media"),
    ("audio", "Âm thanh", "rail-audio"),
    ("effects", "Hiệu ứng", "rail-effects"),
    ("transitions", "Chuyển tiếp", "rail-transitions"),
    ("captions", "Phụ đề", "rail-captions"),
]

_BUTTON_WIDTH = 80
_BUTTON_HEIGHT = 44
_ICON_DEFAULT_COLOR = "#cdd4dc"
_ICON_ACTIVE_COLOR = "#14dbe8"


class LeftRail(QWidget):
    category_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("leftRail")
        self.setFixedHeight(56)
        self.setStyleSheet(
            "#leftRail QToolButton {"
             " border: none;"
             " background: transparent;"
             " color: #d4dde8;"
             " border-radius: 6px;"
             " padding: 0px;"
             " spacing: 0px;"
             " margin: 0px;"
            " }"
            "#leftRail QToolButton:hover {"
             " border: none;"
             " background: transparent;"
            " }"
            "#leftRail QToolButton:checked {"
             " border: none;"
             " background: transparent;"
             " color: #14dbe8;"
            " }"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(0)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QToolButton] = {}
        self._icon_names: dict[str, str] = {}

        for key, label, icon_name in RAIL_CATEGORIES:
            translated_label = QCoreApplication.translate("LeftRail", label)
            button = self._build_button(key, translated_label, icon_name)
            layout.addWidget(button)
            self._group.addButton(button)
            self._buttons[key] = button
            self._icon_names[key] = icon_name

        rail_content_width = 4 + 4 + (len(RAIL_CATEGORIES) * _BUTTON_WIDTH)
        self.setMinimumWidth(rail_content_width)

        first_key = RAIL_CATEGORIES[0][0]
        self._buttons[first_key].setChecked(True)

    def select(self, key: str) -> None:
        button = self._buttons.get(key)
        if button is None or button.isChecked():
            return
        button.setChecked(True)

    def keys(self) -> Iterable[str]:
        return tuple(key for key, _label, _icon in RAIL_CATEGORIES)

    def _build_button(self, key: str, label: str, icon_name: str) -> QToolButton:
        button = QToolButton(self)
        button_font = button.font()
        button_font.setPixelSize(8)
        button.setFont(button_font)
        button.setText(label)
        button.setIcon(build_icon(icon_name, color=_ICON_DEFAULT_COLOR))
        button.setIconSize(QSize(20, 20))
        button.setCheckable(True)
        button.setAutoRaise(True)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setToolTip(label)
        button.setFixedSize(_BUTTON_WIDTH, _BUTTON_HEIGHT)
        button.toggled.connect(lambda checked, k=key: self._on_button_toggled(k, checked))
        return button

    def _on_button_toggled(self, key: str, checked: bool) -> None:
        button = self._buttons.get(key)
        icon_name = self._icon_names.get(key)
        if button is not None and icon_name is not None:
            icon_color = _ICON_ACTIVE_COLOR if checked else _ICON_DEFAULT_COLOR
            button.setIcon(build_icon(icon_name, color=icon_color))
        if checked:
            self.category_selected.emit(key)
