from __future__ import annotations

from dataclasses import dataclass

from app.controllers.project_controller import ProjectController
from app.services.audio_playback_service import AudioPlaybackService
from app.services.playback_service import PlaybackService
from PySide6.QtCore import QElapsedTimer, QObject, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtGui import QImage


@dataclass(slots=True)
class _PreviewFrameRequest:
    request_id: int
    project: object | None
    time_seconds: float
    project_path: str | None


class _PreviewFrameSignals(QObject):
    completed = Signal(int, object, str)
    failed = Signal(int, str)


class _PreviewFrameWorker(QRunnable):
    def __init__(self, request: _PreviewFrameRequest, playback_service: PlaybackService) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._request = request
        self._playback_service = playback_service
        self.signals = _PreviewFrameSignals()

    def run(self) -> None:
        try:
            frame_result = self._playback_service.get_preview_frame(
                self._request.project,
                self._request.time_seconds,
                self._request.project_path,
            )
        except Exception as exc:  # pragma: no cover - defensive guard for worker-thread failures
            self.signals.failed.emit(self._request.request_id, str(exc))
            return

        self.signals.completed.emit(self._request.request_id, frame_result.frame_bytes, frame_result.message)


class PlaybackController(QObject):
    _DEFAULT_PREVIEW_FPS = 30.0
    _MIN_PREVIEW_REFRESH_MS = 16
    _MAX_PREVIEW_REFRESH_MS = 120

    current_time_changed = Signal(float)
    playback_state_changed = Signal(str)
    preview_frame_changed = Signal(object)
    preview_message_changed = Signal(str)

    def __init__(
        self,
        project_controller: ProjectController,
        playback_service: PlaybackService | None = None,
        audio_playback_service: AudioPlaybackService | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._project_controller = project_controller
        self._playback_service = playback_service or PlaybackService()
        self._audio_playback_service = audio_playback_service or AudioPlaybackService(parent=self)

        self._current_time_seconds = 0.0
        self._state = "stopped"
        self._last_preview_message = "No project loaded"
        self._last_preview_image: QImage | None = None
        self._preview_thread_pool = QThreadPool()
        self._preview_request_counter = 0
        self._preview_active_request_id: int | None = None
        self._preview_pending_request: _PreviewFrameRequest | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._on_timer_timeout)

        self._preview_refresh_timer = QTimer(self)
        self._preview_refresh_timer.setInterval(
            self._preview_refresh_interval_ms_for_fps(self._DEFAULT_PREVIEW_FPS)
        )
        self._preview_refresh_timer.timeout.connect(self._on_preview_refresh_timeout)

        self._audio_sync_timer = QTimer(self)
        self._audio_sync_timer.setInterval(80)
        self._audio_sync_timer.timeout.connect(self._on_audio_sync_timeout)

        self._elapsed = QElapsedTimer()
        self._project_controller.project_changed.connect(self._on_project_changed)
        self._on_project_changed()

    def current_time(self) -> float:
        return self._current_time_seconds

    def state(self) -> str:
        return self._state

    def is_playing(self) -> bool:
        return self._state == "playing"

    def play(self) -> None:
        if self._state == "playing":
            return

        self._state = "playing"
        self._elapsed.restart()
        self._timer.start()
        self._preview_refresh_timer.start()
        self._audio_sync_timer.start()
        self.refresh_preview_frame()
        self.refresh_audio_playback()
        self.playback_state_changed.emit(self._state)

    def pause(self) -> None:
        if self._state != "playing":
            return

        self._advance_from_elapsed()
        self._timer.stop()
        self._preview_refresh_timer.stop()
        self._audio_sync_timer.stop()
        self._state = "paused"
        self.playback_state_changed.emit(self._state)
        self.refresh_preview_frame()
        self.refresh_audio_playback()

    def stop(self) -> None:
        if self._state == "playing":
            self._advance_from_elapsed()

        self._timer.stop()
        self._preview_refresh_timer.stop()
        self._audio_sync_timer.stop()
        self._set_current_time(0.0)

        if self._state != "stopped":
            self._state = "stopped"
            self.playback_state_changed.emit(self._state)
        self.refresh_preview_frame()
        self.refresh_audio_playback()

    def toggle_play_pause(self) -> None:
        if self._state == "playing":
            self.pause()
            return
        self.play()

    def seek_to_start(self) -> None:
        self.seek(0.0)

    def nudge_frames(self, frame_delta: int) -> None:
        if frame_delta == 0:
            return
        fps = self.current_fps()
        self.seek(self._current_time_seconds + (frame_delta / fps))

    def current_fps(self) -> float:
        project = self._project_controller.active_project()
        if project is None or project.fps <= 0:
            return self._DEFAULT_PREVIEW_FPS
        return project.fps

    def seek(self, time_seconds: float) -> None:
        self._set_current_time(max(0.0, time_seconds))
        if self._state == "playing":
            self._elapsed.restart()
        self.refresh_preview_frame()
        self.refresh_audio_playback()

    def set_playhead_seconds(self, time_seconds: float) -> None:
        self.seek(time_seconds)

    def refresh_preview_frame(self) -> None:
        self._preview_request_counter += 1
        self._preview_pending_request = _PreviewFrameRequest(
            request_id=self._preview_request_counter,
            project=self._project_controller.active_project(),
            time_seconds=self._current_time_seconds,
            project_path=self._project_controller.active_project_path(),
        )

        if self._preview_active_request_id is not None:
            return

        self._dispatch_preview_request()

    def latest_preview_image(self) -> QImage | None:
        return self._last_preview_image

    def latest_preview_message(self) -> str:
        return self._last_preview_message

    def _on_timer_timeout(self) -> None:
        if self._state != "playing":
            return
        self._advance_from_elapsed()

    def _on_preview_refresh_timeout(self) -> None:
        if self._state != "playing":
            return
        self.refresh_preview_frame()

    def _on_audio_sync_timeout(self) -> None:
        if self._state != "playing":
            return
        self.refresh_audio_playback()

    def _advance_from_elapsed(self) -> None:
        elapsed_seconds = self._elapsed.restart() / 1000.0
        if elapsed_seconds <= 0:
            return
        # Keep playhead motion smooth while avoiding synchronous frame decode on every tick.
        self._set_current_time(self._current_time_seconds + elapsed_seconds)

    def _set_current_time(self, time_seconds: float) -> None:
        if abs(time_seconds - self._current_time_seconds) < 1e-6:
            return
        self._current_time_seconds = time_seconds
        self.current_time_changed.emit(self._current_time_seconds)

    def _dispatch_preview_request(self) -> None:
        request = self._preview_pending_request
        if request is None:
            return

        self._preview_pending_request = None
        self._preview_active_request_id = request.request_id
        worker = _PreviewFrameWorker(request, self._playback_service)
        worker.signals.completed.connect(self._on_preview_request_completed)
        worker.signals.failed.connect(self._on_preview_request_failed)
        self._preview_thread_pool.start(worker)

    def _on_preview_request_completed(self, request_id: int, frame_bytes: object, message: str) -> None:
        if request_id != self._preview_active_request_id:
            return

        self._preview_active_request_id = None
        self._apply_preview_result(frame_bytes, message)
        self._dispatch_preview_request()

    def _on_preview_request_failed(self, request_id: int, message: str) -> None:
        if request_id != self._preview_active_request_id:
            return

        self._preview_active_request_id = None
        self._apply_preview_result(None, message)
        self._dispatch_preview_request()

    def _apply_preview_result(self, frame_bytes: object, message: str) -> None:
        self._last_preview_image = self._bytes_to_image(frame_bytes)
        self.preview_frame_changed.emit(self._last_preview_image)
        if message != self._last_preview_message:
            self._last_preview_message = message
            self.preview_message_changed.emit(message)

    def refresh_audio_playback(self) -> None:
        project = self._project_controller.active_project()
        self._audio_playback_service.sync_to_playhead(
            project,
            self._current_time_seconds,
            self._project_controller.active_project_path(),
            self._state,
        )

    def _on_project_changed(self) -> None:
        self._apply_project_refresh_rate()
        self._audio_playback_service.clear()
        self.refresh_preview_frame()
        self.refresh_audio_playback()

    def _apply_project_refresh_rate(self) -> None:
        project = self._project_controller.active_project()
        fps = project.fps if project is not None else self._DEFAULT_PREVIEW_FPS
        interval_ms = self._preview_refresh_interval_ms_for_fps(fps)
        self._preview_refresh_timer.setInterval(interval_ms)

    @classmethod
    def _preview_refresh_interval_ms_for_fps(cls, fps: float) -> int:
        safe_fps = fps if fps > 0 else cls._DEFAULT_PREVIEW_FPS
        target_interval = int(round(1000.0 / safe_fps))
        return max(cls._MIN_PREVIEW_REFRESH_MS, min(cls._MAX_PREVIEW_REFRESH_MS, target_interval))

    @staticmethod
    def _bytes_to_image(frame_bytes: object) -> QImage | None:
        if not frame_bytes:
            return None

        image = QImage.fromData(bytes(frame_bytes))
        if image.isNull():
            return None
        return image
