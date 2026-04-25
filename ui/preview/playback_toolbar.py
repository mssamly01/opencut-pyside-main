from __future__ import annotations

from app.controllers.playback_controller import PlaybackController
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class PlaybackToolbar(QWidget):
    def __init__(self, playback_controller: PlaybackController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._playback_controller = playback_controller

        layout = QHBoxLayout(self)

        self._to_start_button = QPushButton("<<", self)
        self._prev_frame_button = QPushButton("<F", self)
        self._play_button = QPushButton("Play", self)
        self._pause_button = QPushButton("Pause", self)
        self._stop_button = QPushButton("Stop", self)
        self._next_frame_button = QPushButton("F>", self)
        self._time_label = QLabel("00:00:00:00", self)
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._time_label.setMinimumWidth(112)

        self._to_start_button.clicked.connect(self._playback_controller.seek_to_start)
        self._prev_frame_button.clicked.connect(lambda: self._playback_controller.nudge_frames(-1))
        self._play_button.clicked.connect(self._playback_controller.play)
        self._pause_button.clicked.connect(self._playback_controller.pause)
        self._stop_button.clicked.connect(self._playback_controller.stop)
        self._next_frame_button.clicked.connect(lambda: self._playback_controller.nudge_frames(1))

        self._playback_controller.current_time_changed.connect(self._on_current_time_changed)
        self._playback_controller.playback_state_changed.connect(self._on_playback_state_changed)

        layout.addWidget(self._to_start_button)
        layout.addWidget(self._prev_frame_button)
        layout.addWidget(self._play_button)
        layout.addWidget(self._pause_button)
        layout.addWidget(self._stop_button)
        layout.addWidget(self._next_frame_button)
        layout.addStretch()
        layout.addWidget(self._time_label)
        self._on_current_time_changed(self._playback_controller.current_time())
        self._on_playback_state_changed(self._playback_controller.state())

    def _on_current_time_changed(self, current_time: float) -> None:
        fps = self._playback_controller.current_fps()
        safe_time = max(0.0, current_time)

        total_seconds = int(safe_time)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        fractional = safe_time - total_seconds
        frame = int(fractional * fps)
        max_frame = max(0, int(fps) - 1)
        frame = min(max(0, frame), max_frame)
        self._time_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frame:02d}")

    def _on_playback_state_changed(self, state: str) -> None:
        is_playing = state == "playing"
        self._play_button.setEnabled(not is_playing)
        self._pause_button.setEnabled(is_playing)
