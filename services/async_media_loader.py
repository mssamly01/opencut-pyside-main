"""Background workers for media import and thumbnail extraction.

Both ffprobe (during import) and ``ffmpeg -ss ... -frames:v 1`` (for the
media-library thumbnails) are subprocess invocations that take 50–2000 ms
per long video. The original code ran them on the UI thread inside
``ProjectController.import_media_files`` and ``MediaPanel._build_media_icon``,
which froze the app for several seconds when the user imported one or more
long clips.

This module wraps both operations as ``QRunnable`` workers feeding a
shared ``QThreadPool`` and exposes ``QObject`` signals so the UI can stay
responsive and update progressively.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.clips.video_clip import VideoClip
from app.domain.media_asset import MediaAsset
from app.domain.project import Project
from app.services.media_service import MediaService
from app.services.thumbnail_service import ThumbnailService
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


@dataclass(slots=True)
class _ImportRequest:
    request_id: int
    file_paths: list[str]


class _ImportSignals(QObject):
    completed = Signal(int, list)  # request_id, list[MediaAsset]


class _ImportWorker(QRunnable):
    def __init__(self, request: _ImportRequest, media_service: MediaService, signals: _ImportSignals) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._request = request
        self._media_service = media_service
        self._signals = signals

    def run(self) -> None:
        try:
            assets = self._media_service.import_files(list(self._request.file_paths))
        except Exception:  # pragma: no cover - defensive guard for worker thread
            assets = []
        self._signals.completed.emit(self._request.request_id, assets)


class AsyncMediaImporter(QObject):
    """Run ``MediaService.import_files`` off the UI thread."""

    import_completed = Signal(int, list)  # request_id, list[MediaAsset]

    def __init__(
        self,
        media_service: MediaService | None = None,
        thread_pool: QThreadPool | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._media_service = media_service or MediaService()
        self._pool = thread_pool or QThreadPool(self)
        self._signals = _ImportSignals()
        self._signals.completed.connect(self.import_completed)
        self._next_request_id = 0

    def request_import(self, file_paths: list[str]) -> int:
        """Schedule an import. Returns a request id; caller listens to ``import_completed``."""

        self._next_request_id += 1
        request = _ImportRequest(request_id=self._next_request_id, file_paths=list(file_paths))
        worker = _ImportWorker(request, self._media_service, self._signals)
        self._pool.start(worker)
        return self._next_request_id


@dataclass(slots=True)
class _ThumbnailRequest:
    media_id: str
    media_asset: MediaAsset
    project_path: str | None


class _ThumbnailSignals(QObject):
    completed = Signal(str, object)  # media_id, bytes | None


class _ThumbnailWorker(QRunnable):
    def __init__(
        self,
        request: _ThumbnailRequest,
        thumbnail_service: ThumbnailService,
        signals: _ThumbnailSignals,
    ) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._request = request
        self._service = thumbnail_service
        self._signals = signals

    def run(self) -> None:
        try:
            payload = self._service.get_media_asset_thumbnail_bytes(
                self._request.media_asset,
                project_path=self._request.project_path,
                source_time=0.0,
            )
        except Exception:  # pragma: no cover - defensive guard for worker thread
            payload = None
        self._signals.completed.emit(self._request.media_id, payload)


class AsyncMediaThumbnailLoader(QObject):
    """Load media-library thumbnails off the UI thread, deduping in-flight work."""

    thumbnail_ready = Signal(str, object)  # media_id, bytes | None

    def __init__(
        self,
        thumbnail_service: ThumbnailService | None = None,
        thread_pool: QThreadPool | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = thumbnail_service or ThumbnailService()
        self._pool = thread_pool or QThreadPool(self)
        self._signals = _ThumbnailSignals()
        self._signals.completed.connect(self._on_completed)
        self._pending: set[str] = set()

    def request(self, media_asset: MediaAsset, project_path: str | None) -> None:
        """Schedule a thumbnail load. Duplicate requests for the same media_id are ignored."""

        media_id = media_asset.media_id
        if media_id in self._pending:
            return
        self._pending.add(media_id)
        worker = _ThumbnailWorker(
            _ThumbnailRequest(
                media_id=media_id,
                media_asset=media_asset,
                project_path=project_path,
            ),
            self._service,
            self._signals,
        )
        self._pool.start(worker)

    def _on_completed(self, media_id: str, payload: object) -> None:
        self._pending.discard(media_id)
        self.thumbnail_ready.emit(media_id, payload)


@dataclass(slots=True)
class _FilmstripRequest:
    cache_key: str
    clip_id: str
    project: Project
    clip: VideoClip
    project_path: str | None
    frame_count: int


class _FilmstripSignals(QObject):
    completed = Signal(str, str, list)  # cache_key, clip_id, list[bytes]


class _FilmstripWorker(QRunnable):
    def __init__(
        self,
        request: _FilmstripRequest,
        thumbnail_service: ThumbnailService,
        signals: _FilmstripSignals,
    ) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._request = request
        self._service = thumbnail_service
        self._signals = signals

    def run(self) -> None:
        try:
            frames = self._service.get_filmstrip_bytes(
                project=self._request.project,
                clip=self._request.clip,
                project_path=self._request.project_path,
                frame_count=self._request.frame_count,
            )
        except Exception:  # pragma: no cover - defensive guard for worker thread
            frames = []
        self._signals.completed.emit(self._request.cache_key, self._request.clip_id, frames)


class AsyncFilmstripLoader(QObject):
    """Run ``ThumbnailService.get_filmstrip_bytes`` off the UI thread.

    Drag-to-timeline used to stall for several seconds because the scene
    rendered each new ``VideoClip`` by calling ``get_filmstrip_bytes`` on the
    UI thread, which forks 1–256 ``ffmpeg`` subprocesses sequentially. This
    loader pushes that work to a worker pool and emits the bytes back via a
    signal, keyed by both ``cache_key`` (so the scene can cache pixmaps) and
    ``clip_id`` (so the scene can find the live ``ClipItem``).
    """

    filmstrip_ready = Signal(str, str, list)  # cache_key, clip_id, list[bytes]

    def __init__(
        self,
        thumbnail_service: ThumbnailService | None = None,
        thread_pool: QThreadPool | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = thumbnail_service or ThumbnailService()
        self._pool = thread_pool or QThreadPool(self)
        self._signals = _FilmstripSignals()
        self._signals.completed.connect(self._on_completed)
        self._pending: set[str] = set()

    def request(
        self,
        cache_key: str,
        clip_id: str,
        project: Project,
        clip: VideoClip,
        project_path: str | None,
        frame_count: int,
    ) -> None:
        """Schedule a filmstrip load. Duplicate ``cache_key`` requests are ignored."""

        if cache_key in self._pending:
            return
        self._pending.add(cache_key)
        worker = _FilmstripWorker(
            _FilmstripRequest(
                cache_key=cache_key,
                clip_id=clip_id,
                project=project,
                clip=clip,
                project_path=project_path,
                frame_count=frame_count,
            ),
            self._service,
            self._signals,
        )
        self._pool.start(worker)

    def _on_completed(self, cache_key: str, clip_id: str, frames: list) -> None:
        self._pending.discard(cache_key)
        self.filmstrip_ready.emit(cache_key, clip_id, frames)
