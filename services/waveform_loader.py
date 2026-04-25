"""Sprint 14: Background loader for WaveformService.get_peaks_for_asset."""

from __future__ import annotations

from app.domain.media_asset import MediaAsset
from app.services.waveform_service import WaveformService
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _WaveformSignalEmitter(QObject):
    """Bridge for QRunnable to emit Qt signals (QRunnable itself is not a QObject)."""

    peaks_loaded = Signal(str, list)


class _WaveformTask(QRunnable):
    def __init__(
        self,
        waveform_service: WaveformService,
        media_asset: MediaAsset,
        project_path: str | None,
        emitter: _WaveformSignalEmitter,
    ) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._waveform_service = waveform_service
        self._media_asset = media_asset
        self._project_path = project_path
        self._emitter = emitter

    def run(self) -> None:
        try:
            peaks = self._waveform_service.get_peaks_for_asset(self._media_asset, self._project_path)
        except Exception:  # pragma: no cover - defensive guard for worker-thread failures
            peaks = []
        self._emitter.peaks_loaded.emit(self._media_asset.media_id, peaks)


class WaveformLoader(QObject):
    """Async wrapper around WaveformService.get_peaks_for_asset using QThreadPool."""

    peaks_loaded = Signal(str, list)

    def __init__(
        self,
        waveform_service: WaveformService,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._waveform_service = waveform_service
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self._emitter = _WaveformSignalEmitter()
        self._emitter.peaks_loaded.connect(self.peaks_loaded.emit)

    def request_peaks(self, media_asset: MediaAsset, project_path: str | None = None) -> None:
        task = _WaveformTask(self._waveform_service, media_asset, project_path, self._emitter)
        self._pool.start(task)
