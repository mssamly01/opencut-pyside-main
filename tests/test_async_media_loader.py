"""Async import + thumbnail off the UI thread.

The old code blocked Qt's UI thread inside ``_on_import_clicked`` for one
``ffprobe`` subprocess per file plus one ``ffmpeg -ss ... -frames:v 1`` PNG
encode per video. Importing a few long videos froze the app for several
seconds. These tests pin the new contract: ``ProjectController`` schedules
import work on a worker thread and emits ``media_import_finished`` with the
new asset ids, while ``AsyncMediaThumbnailLoader`` loads thumbnails off-thread
and dedupes concurrent requests for the same media id.
"""

from __future__ import annotations

from app.bootstrap import create_application
from app.controllers.project_controller import ProjectController
from app.domain.media_asset import MediaAsset
from app.domain.project import build_empty_project
from app.services.async_media_loader import AsyncMediaImporter, AsyncMediaThumbnailLoader
from app.services.media_service import MediaService
from app.services.thumbnail_service import ThumbnailService
from PySide6.QtCore import QEventLoop, QTimer


class _StubMediaService(MediaService):
    def __init__(self, assets: list[MediaAsset]) -> None:
        self._assets = assets
        self.calls = 0

    def import_files(self, file_paths: list[str]) -> list[MediaAsset]:  # type: ignore[override]
        self.calls += 1
        return list(self._assets)


class _StubThumbnailService(ThumbnailService):
    def __init__(self, payload: bytes | None) -> None:
        self._payload = payload
        self.calls: list[str] = []

    def get_media_asset_thumbnail_bytes(  # type: ignore[override]
        self,
        media_asset: MediaAsset,
        project_path: str | None = None,
        source_time: float = 0.0,
    ) -> bytes | None:
        self.calls.append(media_asset.media_id)
        return self._payload


def _process_until(predicate, timeout_ms: int = 2000) -> None:
    """Spin Qt's event loop until ``predicate()`` returns True or timeout."""

    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(10)

    def tick() -> None:
        if predicate():
            loop.quit()

    timer.timeout.connect(tick)
    timer.start()
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    timer.stop()


def test_async_importer_runs_off_thread_and_returns_assets() -> None:
    create_application(["pytest"])
    asset = MediaAsset(
        media_id="media_a",
        name="a",
        file_path="/tmp/a.mp4",
        media_type="video",
    )
    importer = AsyncMediaImporter(_StubMediaService([asset]))

    received: list[list[MediaAsset]] = []
    importer.import_completed.connect(lambda _rid, assets: received.append(list(assets)))

    importer.request_import(["/tmp/a.mp4"])
    _process_until(lambda: bool(received))

    assert received == [[asset]]


def test_project_controller_emits_media_import_finished_with_new_ids() -> None:
    create_application(["pytest"])
    asset = MediaAsset(
        media_id="media_x",
        name="x",
        file_path="/tmp/x.mp4",
        media_type="video",
    )
    stub = _StubMediaService([asset])
    controller = ProjectController(media_service=stub)
    controller.set_active_project(build_empty_project())

    finished_ids: list[list[str]] = []
    controller.media_import_finished.connect(lambda ids: finished_ids.append(list(ids)))

    started = controller.import_media_files_async(["/tmp/x.mp4"])
    assert started is True

    _process_until(lambda: bool(finished_ids))

    assert finished_ids == [["media_x"]]
    assert controller.active_project().media_items == [asset]


def test_thumbnail_service_memory_cache_is_thread_safe(tmp_path) -> None:
    """Stress the OrderedDict cache from multiple threads.

    Without the lock, ``_read_cached_bytes`` would race with
    ``_remember_in_cache``: a thread can call ``.get(key)`` and find a hit,
    then ``popitem(last=False)`` on another thread evicts that key before the
    first thread reaches ``.move_to_end(key)`` — raising ``KeyError`` and
    silently dropping the thumbnail. This pins the lock that prevents it.
    """

    import threading
    from app.services.thumbnail_service import ThumbnailService

    service = ThumbnailService(cache_root=tmp_path, max_memory_entries=8)
    payload = b"\x89PNG\r\n\x1a\n"
    errors: list[BaseException] = []
    stop = threading.Event()

    def thrash() -> None:
        try:
            for index in range(2000):
                if stop.is_set():
                    return
                key_path = tmp_path / f"{index % 32}.png"
                service._write_cached_bytes(key_path, payload)  # noqa: SLF001
                service._read_cached_bytes(key_path)  # noqa: SLF001
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
            stop.set()

    threads = [threading.Thread(target=thrash) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors, f"thread-unsafe cache raised: {errors}"


def test_thumbnail_loader_dedupes_in_flight_requests() -> None:
    create_application(["pytest"])
    service = _StubThumbnailService(payload=b"\x89PNG\r\n\x1a\n")
    loader = AsyncMediaThumbnailLoader(service)
    asset = MediaAsset(
        media_id="media_dup",
        name="dup",
        file_path="/tmp/dup.mp4",
        media_type="video",
    )

    received: list[tuple[str, object]] = []
    loader.thumbnail_ready.connect(lambda mid, payload: received.append((mid, payload)))

    loader.request(asset, project_path=None)
    loader.request(asset, project_path=None)
    loader.request(asset, project_path=None)

    _process_until(lambda: bool(received))

    assert len(received) == 1
    assert service.calls == ["media_dup"]
