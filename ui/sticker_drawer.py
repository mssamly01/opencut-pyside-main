from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, QSize, Qt
from PySide6.QtGui import QDrag, QIcon, QMouseEvent, QPixmap
from PySide6.QtWidgets import QGridLayout, QLabel, QScrollArea, QToolButton, QVBoxLayout, QWidget

STICKER_MIME_TYPE = "application/x-opencut-sticker"


class _StickerButton(QToolButton):
    def __init__(self, sticker_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sticker_path = sticker_path
        self._press_pos: QPoint | None = None

        pixmap = QPixmap(str(sticker_path))
        if not pixmap.isNull():
            self.setIcon(QIcon(pixmap))
            self.setIconSize(QSize(56, 56))
        self.setFixedSize(70, 70)
        self.setToolTip(sticker_path.stem)
        self.setAutoRaise(False)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._press_pos is None:
            return
        if (event.pos() - self._press_pos).manhattanLength() < 8:
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(STICKER_MIME_TYPE, str(self._sticker_path).encode("utf-8"))
        drag.setMimeData(mime)

        drag_pixmap = QPixmap(str(self._sticker_path))
        if not drag_pixmap.isNull():
            drag.setPixmap(
                drag_pixmap.scaled(
                    56,
                    56,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        drag.exec(Qt.DropAction.CopyAction)
        self._press_pos = None


class StickerDrawer(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        title = QLabel("Stickers", self)
        title.setStyleSheet("font-weight: 600;")
        root.addWidget(title)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        body = QWidget(scroll)
        grid = QGridLayout(body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)

        sticker_paths = sorted(self._sticker_dir().glob("*.png"))
        if not sticker_paths:
            empty = QLabel("No stickers found", body)
            empty.setStyleSheet("color: #8a97a8;")
            grid.addWidget(empty, 0, 0)
        else:
            for index, sticker_path in enumerate(sticker_paths):
                row, col = divmod(index, 4)
                grid.addWidget(_StickerButton(sticker_path, body), row, col)

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    @staticmethod
    def _sticker_dir() -> Path:
        return Path(__file__).resolve().parent / "resources" / "stickers"
