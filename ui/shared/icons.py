"""Inline SVG icon factory for the CapCut-style toolbar and media placeholders."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_DEFAULT_COLOR = "#cdd4dc"

_SVG_TEMPLATES: dict[str, str] = {
    # Primary file ops
    "file-open": """<path d="M2 4a1 1 0 0 1 1-1h3.5l1.5 1.5H13a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1z" fill="none" stroke="{color}" stroke-width="1.4"/>""",
    "save": """<path d="M3 3h8l2 2v8H3zM6 3v3.5h4V3M5.5 9.5h5v3h-5z" fill="none" stroke="{color}" stroke-width="1.4" stroke-linejoin="round"/>""",
    "save-as": """<path d="M3 3h8l2 2v8H3zM6 3v3h3V3" fill="none" stroke="{color}" stroke-width="1.4"/><path d="M11 11l3-3" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/>""",
    "new-file": """<path d="M3 2h6l4 4v8H3z" fill="none" stroke="{color}" stroke-width="1.4"/><path d="M8 8v4M6 10h4" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/>""",
    # Media and subtitle
    "import-media": """<rect x="2.5" y="3" width="11" height="8" rx="1" fill="none" stroke="{color}" stroke-width="1.4"/><path d="M2.5 5.5H13.5M5 3v8M11 3v8" stroke="{color}" stroke-width="1.2"/><circle cx="8" cy="13" r="1.6" fill="{color}"/>""",
    "import-subtitle": """<rect x="2" y="5" width="12" height="7" rx="1.5" fill="none" stroke="{color}" stroke-width="1.4"/><path d="M4 8h3M9 8h3M4 10h5" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/><circle cx="13" cy="3" r="1.6" fill="{color}"/>""",
    "export-subtitle": """<rect x="2" y="5" width="12" height="7" rx="1.5" fill="none" stroke="{color}" stroke-width="1.4"/><path d="M4 8h3M9 8h3M4 10h5" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/><path d="M13 3l2 2-2 2M10 5h4" stroke="{color}" stroke-width="1.4" stroke-linecap="round" fill="none"/>""",
    "export": """<path d="M8 1.5v8M5.5 4l2.5-2.5L10.5 4" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M3 10v3h10v-3" fill="none" stroke="{color}" stroke-width="1.4"/>""",
    "subtitle": """<rect x="2.5" y="4" width="11" height="8" rx="1.5" fill="none" stroke="{color}" stroke-width="1.4"/><path d="M4.5 7h3M8.5 7h3M4.5 9.5h6" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>""",
    "sticker": """<path d="M3 5.5A2.5 2.5 0 0 1 5.5 3H10a3 3 0 0 1 3 3v3.5A2.5 2.5 0 0 1 10.5 12H6a3 3 0 0 1-3-3z" fill="none" stroke="{color}" stroke-width="1.4"/><path d="M10 3v3h3" fill="none" stroke="{color}" stroke-width="1.2"/><circle cx="7" cy="8.5" r="0.8" fill="{color}"/><circle cx="10" cy="8.5" r="0.8" fill="{color}"/>""",
    "magic": """<path d="M3 11l8-8 2 2-8 8H3z" fill="none" stroke="{color}" stroke-width="1.4" stroke-linejoin="round"/><path d="M11 2l1-1M13 4l1-1M13 2h2M12 5h2" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>""",
    # Edit ops
    "undo": """<path d="M3 6h7a3.5 3.5 0 0 1 0 7H6" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/><path d="M5 3L2 6l3 3" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/>""",
    "redo": """<path d="M13 6H6a3.5 3.5 0 0 0 0 7h4" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/><path d="M11 3l3 3-3 3" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/>""",
    "cut": """<circle cx="4" cy="11" r="2" fill="none" stroke="{color}" stroke-width="1.4"/><circle cx="12" cy="11" r="2" fill="none" stroke="{color}" stroke-width="1.4"/><path d="M5 10l8-7M11 10l-8-7" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/>""",
    "copy": """<rect x="5" y="5" width="8" height="8" rx="1" fill="none" stroke="{color}" stroke-width="1.4"/><path d="M3 11V4a1 1 0 0 1 1-1h7" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/>""",
    "paste": """<path d="M4 4h8v9H4z" fill="none" stroke="{color}" stroke-width="1.4"/><path d="M6 4V3a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v1" fill="none" stroke="{color}" stroke-width="1.4"/>""",
    "split": """<path d="M8 2v4M8 10v4" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/><circle cx="8" cy="8" r="2" fill="none" stroke="{color}" stroke-width="1.4"/>""",
    "delete": """<path d="M3 5h10M6 5V3h4v2M5 5l.5 9h5L11 5M7 8v3M9 8v3" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>""",
    "duplicate": """<rect x="3" y="3" width="7" height="7" fill="none" stroke="{color}" stroke-width="1.4"/><rect x="6" y="6" width="7" height="7" fill="#1a1d23" stroke="{color}" stroke-width="1.4"/>""",
    # Transport
    "play": """<path d="M4 3l9 5-9 5z" fill="{color}"/>""",
    "pause": """<rect x="4" y="3" width="3" height="10" fill="{color}"/><rect x="9" y="3" width="3" height="10" fill="{color}"/>""",
    "stop": """<rect x="4" y="4" width="8" height="8" fill="{color}"/>""",
    "skip-back": """<path d="M11 3L4 8l7 5zM3 3v10" fill="{color}" stroke="{color}" stroke-width="1.2" stroke-linejoin="round"/>""",
    "skip-forward": """<path d="M5 3l7 5-7 5zM13 3v10" fill="{color}" stroke="{color}" stroke-width="1.2" stroke-linejoin="round"/>""",
    "step-back": """<path d="M10 3L5 8l5 5z" fill="{color}"/><rect x="4" y="3" width="1" height="10" fill="{color}"/>""",
    "step-forward": """<path d="M6 3l5 5-5 5z" fill="{color}"/><rect x="11" y="3" width="1" height="10" fill="{color}"/>""",
    # View
    "zoom-in": """<circle cx="7" cy="7" r="4.5" fill="none" stroke="{color}" stroke-width="1.4"/><path d="M7 4.5v5M4.5 7h5M10.5 10.5L14 14" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/>""",
    "zoom-out": """<circle cx="7" cy="7" r="4.5" fill="none" stroke="{color}" stroke-width="1.4"/><path d="M4.5 7h5M10.5 10.5L14 14" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/>""",
    "fit": """<path d="M2 5V2h3M11 2h3v3M14 11v3h-3M5 14H2v-3" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/>""",
    # Track and misc
    "volume": """<path d="M3 6h2l3-2v8L5 10H3z" fill="{color}"/><path d="M11 5c1 1 1 5 0 6M13 3c2 2 2 8 0 10" fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>""",
    "text": """<path d="M3 4h10M6 4v9M10 4v9" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/>""",
    "magnet": """<path d="M3 3v6a5 5 0 0 0 10 0V3h-3v6a2 2 0 0 1-4 0V3z" fill="none" stroke="{color}" stroke-width="1.4"/><rect x="3" y="2" width="3" height="2" fill="{color}"/><rect x="10" y="2" width="3" height="2" fill="{color}"/>""",
    "logs": """<rect x="3" y="2" width="10" height="12" fill="none" stroke="{color}" stroke-width="1.4"/><path d="M5 5h6M5 8h6M5 11h4" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>""",
    # Sprint 16-B: window chrome (frameless title-bar) controls
    "window-min": """<path d="M3 11h10" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/>""",
    "window-max": """<rect x="3" y="3" width="10" height="10" fill="none" stroke="{color}" stroke-width="1.4"/>""",
    "window-restore": """<rect x="5" y="3" width="8" height="8" fill="none" stroke="{color}" stroke-width="1.4"/><path d="M3 5h2v8h8v-2" fill="none" stroke="{color}" stroke-width="1.4" stroke-linejoin="round"/>""",
    "window-close": """<path d="M4 4l8 8M12 4l-8 8" stroke="{color}" stroke-width="1.4" stroke-linecap="round"/>""",
    # Sprint 9: left-rail category icons
    "rail-media": """<rect x="2" y="3" width="12" height="9" rx="1.2" fill="none" stroke="{color}" stroke-width="1.4"/><path d="M6 5.5l4 2.5-4 2.5z" fill="{color}"/>""",
    "rail-audio": """<path d="M3 6v4h2l3 2.5v-9L5 6zM10.5 5a3.5 3.5 0 0 1 0 6M12 3a6 6 0 0 1 0 10" fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>""",
    "rail-effects": """<path d="M8 2l1.4 3.5L13 6l-2.7 2 0.7 3.5L8 9.7 4.7 11.5 5.4 8 2.7 6l3.5-0.5z" fill="none" stroke="{color}" stroke-width="1.3" stroke-linejoin="round"/>""",
    "rail-transitions": """<rect x="2" y="4" width="5" height="8" fill="none" stroke="{color}" stroke-width="1.3"/><rect x="9" y="4" width="5" height="8" fill="none" stroke="{color}" stroke-width="1.3"/><path d="M7.2 8h1.6M6.8 6.5l1.7 1.5-1.7 1.5M9.2 6.5l-1.7 1.5 1.7 1.5" fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>""",
    "rail-captions": """<rect x="2" y="4" width="12" height="8" rx="1.2" fill="none" stroke="{color}" stroke-width="1.4"/><path d="M5 8.2c-0.5-0.6-1-0.6-1.5 0M11 8.2c-0.5-0.6-1-0.6-1.5 0M5 10.2c-0.5-0.6-1-0.6-1.5 0M11 10.2c-0.5-0.6-1-0.6-1.5 0" fill="none" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>""",
}


def _render_svg(name: str, color: str, size: int) -> QPixmap:
    template = _SVG_TEMPLATES.get(name)
    if template is None:
        empty = QPixmap(size, size)
        empty.fill(Qt.GlobalColor.transparent)
        return empty

    inner = template.format(color=color)
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">{inner}</svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    return QPixmap.fromImage(image)


def build_icon(name: str, color: str = _DEFAULT_COLOR) -> QIcon:
    """Return a QIcon populated with 16/20/24/32 px renderings of `name`."""
    icon = QIcon()
    for size in (16, 20, 24, 32):
        icon.addPixmap(_render_svg(name, color, size), QIcon.Mode.Normal)
    for size in (16, 20, 24, 32):
        icon.addPixmap(_render_svg(name, "#5c6674", size), QIcon.Mode.Disabled)
    return icon


def build_pixmap(name: str, size: int = 16, color: str = _DEFAULT_COLOR) -> QPixmap:
    """Return a pixmap at requested size for custom painting."""
    return _render_svg(name, color, size)


def icon_size(pixels: int) -> QSize:
    return QSize(pixels, pixels)
