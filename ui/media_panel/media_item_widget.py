from __future__ import annotations

from PySide6.QtCore import QMimeData, QPoint, Qt
from PySide6.QtGui import QDrag, QMouseEvent
from PySide6.QtWidgets import QAbstractItemView, QApplication, QListWidget

MEDIA_ASSET_MIME_TYPE = "application/x-opencut-media-asset-id"


class MediaListWidget(QListWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        # External drag only; timeline consumes the drop.
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._press_pos: QPoint | None = None

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if (
            (event.buttons() & Qt.MouseButton.LeftButton)
            and self._press_pos is not None
            and (event.position().toPoint() - self._press_pos).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            self._press_pos = None
            self._start_media_drag()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        self._press_pos = None
        super().mouseReleaseEvent(event)

    def _start_media_drag(self) -> None:
        current_item = self.currentItem()
        if current_item is None:
            return

        media_id = current_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(media_id, str) or not media_id:
            return

        mime_data = QMimeData()
        mime_data.setData(MEDIA_ASSET_MIME_TYPE, media_id.encode("utf-8"))

        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.exec(Qt.DropAction.CopyAction)


def media_id_from_mime_data(mime_data: QMimeData) -> str | None:
    if not mime_data.hasFormat(MEDIA_ASSET_MIME_TYPE):
        return None

    payload = bytes(mime_data.data(MEDIA_ASSET_MIME_TYPE))
    if not payload:
        return None

    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return decoded or None
