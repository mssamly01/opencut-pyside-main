from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QListWidget

MEDIA_ASSET_MIME_TYPE = "application/x-opencut-media-asset-id"


class MediaListWidget(QListWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)

    def startDrag(self, supported_actions: Qt.DropAction) -> None:  # type: ignore[override]
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
