from __future__ import annotations

from app.domain.transition import Transition
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsPathItem, QStyleOptionGraphicsItem, QWidget


class TransitionItem(QGraphicsPathItem):
    def __init__(self, transition: Transition, rect: QRectF, color_hex: str = "#f6c453") -> None:
        super().__init__()
        self.transition = transition
        self._color_hex = color_hex
        self._is_selected_state = False
        self.setRect(rect)

    def setRect(self, rect: QRectF) -> None:  # noqa: N802
        path = QPainterPath()
        path.moveTo(rect.topLeft())
        path.cubicTo(
            QPointF(rect.left() + rect.width() * 0.5, rect.top()),
            QPointF(rect.left() + rect.width() * 0.5, rect.bottom()),
            rect.bottomRight(),
        )
        path.lineTo(rect.bottomLeft())
        path.cubicTo(
            QPointF(rect.left() + rect.width() * 0.5, rect.bottom()),
            QPointF(rect.left() + rect.width() * 0.5, rect.top()),
            rect.topLeft(),
        )
        path.closeSubpath()
        self.setPath(path)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        rect = self.path().boundingRect()
        gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        gradient.setColorAt(0.0, QColor("#1f2933"))
        gradient.setColorAt(0.5, QColor(self._color_hex))
        gradient.setColorAt(1.0, QColor("#1f2933"))
        painter.setBrush(QBrush(gradient))
        pen_color = "#ff5a36" if self._is_selected_state else "#f6c453"
        painter.setPen(QPen(QColor(pen_color), 1.4))
        painter.drawPath(self.path())

    def set_selected_state(self, selected: bool) -> None:
        self._is_selected_state = bool(selected)
        self.update()
