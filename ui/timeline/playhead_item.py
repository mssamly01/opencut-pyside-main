from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsPolygonItem


class PlayheadItem(QGraphicsLineItem):
    MARKER_HALF_WIDTH = 7.0
    MARKER_HEIGHT = 11.0
    ICON_RADIUS = 6.0
    HIT_PADDING = 4.0

    def __init__(self, x_position: float, bounds: QRectF) -> None:
        super().__init__(x_position, bounds.top(), x_position, bounds.bottom())
        self.setPen(QPen(QColor("#ff5a36"), 2))
        self.setZValue(20)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._x_position = x_position
        self._top_y = bounds.top()
        self._bottom_y = bounds.bottom()

        top_y = bounds.top()
        marker = QGraphicsPolygonItem(
            QPolygonF(
                [
                    QPointF(x_position, top_y),
                    QPointF(x_position - self.MARKER_HALF_WIDTH, top_y + self.MARKER_HEIGHT),
                    QPointF(x_position + self.MARKER_HALF_WIDTH, top_y + self.MARKER_HEIGHT),
                ]
            ),
            self,
        )
        marker.setBrush(QBrush(QColor("#ff5a36")))
        marker.setPen(QPen(QColor("#ff5a36"), 1))
        marker.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

        icon = QGraphicsEllipseItem(
            x_position - self.ICON_RADIUS,
            top_y + self.MARKER_HEIGHT + 2.0,
            self.ICON_RADIUS * 2.0,
            self.ICON_RADIUS * 2.0,
            self,
        )
        icon.setBrush(QBrush(QColor("#ff7b5c")))
        icon.setPen(QPen(QColor("#ff5a36"), 1.2))
        icon.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def hit_test(self, scene_x: float, scene_y: float) -> bool:
        line_hit = (
            abs(scene_x - self._x_position) <= self.HIT_PADDING
            and self._top_y <= scene_y <= self._bottom_y
        )
        marker_top = self._top_y
        marker_bottom = self._top_y + self.MARKER_HEIGHT + 2.0 + self.ICON_RADIUS * 2.0
        marker_hit = (
            abs(scene_x - self._x_position) <= self.MARKER_HALF_WIDTH + self.HIT_PADDING
            and marker_top <= scene_y <= marker_bottom
        )
        return line_hit or marker_hit

    def set_scene_x(self, x_position: float) -> None:
        delta = x_position - self._x_position
        if abs(delta) < 1e-6:
            return
        self._x_position = x_position
        self.moveBy(delta, 0.0)

    @property
    def scene_x(self) -> float:
        return self._x_position
