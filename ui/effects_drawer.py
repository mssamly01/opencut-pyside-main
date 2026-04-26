from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QMimeData, QPoint, Qt
from PySide6.QtGui import QDrag, QMouseEvent, QPixmap
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


def _transition_buttons() -> list[tuple[str, str]]:
    translate = QCoreApplication.translate
    return [
        ("cross_dissolve", translate("EffectsDrawer", "Hiệu ứng tan")),
        ("fade_to_black", translate("EffectsDrawer", "Mờ về đen")),
        ("slide_left", translate("EffectsDrawer", "Trượt <-")),
        ("slide_right", translate("EffectsDrawer", "Trượt ->")),
        ("wipe_left", translate("EffectsDrawer", "Xóa <-")),
        ("wipe_right", translate("EffectsDrawer", "Xóa ->")),
    ]

TRANSITION_MIME_TYPE = "application/x-opencut-transition"


class _TransitionDragButton(QPushButton):
    def __init__(self, transition_type: str, label: str, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self._transition_type = transition_type
        self._press_pos: QPoint | None = None
        self.setToolTip(self.tr("Kéo vào ranh giới giữa hai clip trên dòng thời gian"))

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
        mime.setData(TRANSITION_MIME_TYPE, self._transition_type.encode("utf-8"))
        drag.setMimeData(mime)
        preview = QPixmap(120, 32)
        preview.fill(Qt.GlobalColor.transparent)
        drag.setPixmap(preview)
        drag.exec(Qt.DropAction.CopyAction)
        self._press_pos = None

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._press_pos = None
        super().mouseReleaseEvent(event)


class EffectsDrawer(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel(self.tr("Chuyển cảnh"), self)
        title.setStyleSheet("font-weight: 600;")
        layout.addWidget(title)

        hint = QLabel(self.tr("Kéo vào ranh giới giữa hai clip."), self)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #7a8794;")
        layout.addWidget(hint)

        for transition_type, label in _transition_buttons():
            layout.addWidget(_TransitionDragButton(transition_type, label, self))

        layout.addStretch(1)
