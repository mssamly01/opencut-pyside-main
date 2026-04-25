"""Sprint 14: list row widget for AudioPanel with async waveform preview."""

from __future__ import annotations

from pathlib import Path

from app.domain.media_asset import MediaAsset
from app.services.waveform_loader import WaveformLoader
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class _WaveformView(QWidget):
    """Lightweight waveform painter. Receives a list[float] (0..1) of peaks."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._peaks: list[float] = []
        self.setFixedSize(80, 24)
        self.setObjectName("audio_row_waveform")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_peaks(self, peaks: list[float]) -> None:
        self._peaks = peaks
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(80, 24)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        rect = self.rect().adjusted(2, 2, -2, -2)
        painter.fillRect(self.rect(), QColor("#1c2129"))
        if not self._peaks:
            painter.setPen(QPen(QColor("#3a4452"), 1))
            mid_y = rect.center().y()
            painter.drawLine(rect.left(), mid_y, rect.right(), mid_y)
            painter.end()
            return

        pen = QPen(QColor("#00bcd4"))
        pen.setWidth(1)
        painter.setPen(pen)

        peak_count = len(self._peaks)
        width = rect.width()
        if peak_count == 0 or width <= 0:
            painter.end()
            return

        center_y = rect.center().y()
        max_amplitude = (rect.height() / 2.0) - 1.0
        for x_index in range(width):
            peak_index = min(int(x_index * peak_count / width), peak_count - 1)
            magnitude = max(0.0, min(1.0, float(self._peaks[peak_index])))
            half_height = max(1.0, magnitude * max_amplitude)
            x_coord = rect.left() + x_index
            painter.drawLine(
                int(x_coord),
                int(center_y - half_height),
                int(x_coord),
                int(center_y + half_height),
            )
        painter.end()


class AudioRowWidget(QWidget):
    """Row widget composing async-loaded waveform + name label."""

    def __init__(
        self,
        media_asset: MediaAsset,
        waveform_loader: WaveformLoader | None,
        project_path: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._media_id = media_asset.media_id
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(8)

        self._waveform_view = _WaveformView(self)
        layout.addWidget(self._waveform_view)

        label = media_asset.name or Path(media_asset.file_path).name
        self._label = QLabel(label, self)
        self._label.setObjectName("audio_row_name")
        self._label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._label.setWordWrap(False)
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._label, 1)

        if waveform_loader is not None:
            waveform_loader.peaks_loaded.connect(self._on_peaks_loaded)
            waveform_loader.request_peaks(media_asset, project_path=project_path)

    def _on_peaks_loaded(self, media_id: str, peaks: list) -> None:
        if media_id != self._media_id:
            return
        self._waveform_view.set_peaks(peaks)
