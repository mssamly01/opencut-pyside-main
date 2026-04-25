from __future__ import annotations

from app.controllers.playback_controller import PlaybackController
from app.ui.shared.icons import build_icon
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QLabel, QPushButton, QWidget


class PlaybackTimeLabel(QLabel):
    """Time label showing current and total timeline duration."""

    def __init__(self, playback_controller: PlaybackController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._playback_controller = playback_controller
        self._total_seconds = 0.0
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(220)
        self.setStyleSheet("color: #cdd4dc; font-family: monospace;")

        self._playback_controller.current_time_changed.connect(self._refresh)
        self._refresh(self._playback_controller.current_time())

    def set_total_seconds(self, total: float) -> None:
        self._total_seconds = max(0.0, float(total))
        self._refresh(self._playback_controller.current_time())

    def _refresh(self, current_time: float) -> None:
        fps = self._playback_controller.current_fps()
        current = self._format(current_time, fps)
        total = self._format(self._total_seconds, fps)
        self.setText(f"{current} / {total}")

    @staticmethod
    def _format(time_seconds: float, fps: float) -> str:
        safe = max(0.0, float(time_seconds))
        total_seconds = int(safe)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        fractional = safe - total_seconds
        max_frame = max(0, int(fps) - 1)
        frame = min(max(0, int(fractional * fps)), max_frame)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frame:02d}"


class PlaybackPlayButton(QPushButton):
    """Centered, prominent play/pause button for preview bottom toolbar."""

    def __init__(self, playback_controller: PlaybackController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._playback_controller = playback_controller
        self.setFixedSize(QSize(44, 36))
        self.setIconSize(QSize(18, 18))
        self.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.08); border-radius: 6px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.16); }"
        )
        self.clicked.connect(self._playback_controller.toggle_play_pause)
        self._playback_controller.playback_state_changed.connect(self._on_state_changed)
        self._on_state_changed(self._playback_controller.state())

    def _on_state_changed(self, state: str) -> None:
        if state == "playing":
            self.setIcon(build_icon("pause", color="#ffffff"))
            self.setToolTip("Pause")
        else:
            self.setIcon(build_icon("play", color="#ffffff"))
            self.setToolTip("Play")
