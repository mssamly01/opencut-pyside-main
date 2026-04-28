"""Filmstrip generation runs off the UI thread when a video clip is rendered.

Before: ``TimelineScene._draw_track_clips`` called
``ThumbnailService.get_filmstrip_bytes`` synchronously on the UI thread, which
forks 1–256 ``ffmpeg`` subprocesses sequentially and froze the timeline for
several seconds whenever a video clip was added.

After: the scene shows the clip immediately with no thumbnails, kicks off
``AsyncFilmstripLoader``, and swaps in pixmaps when the worker emits
``filmstrip_ready``. Repeat renders (zoom, selection change, …) hit the
pixmap cache without re-spawning ffmpeg.
"""

from __future__ import annotations

from app.bootstrap import create_application
from app.domain.clips.video_clip import VideoClip
from app.domain.media_asset import MediaAsset
from app.domain.project import build_empty_project
from app.domain.timeline import Timeline
from app.domain.track import Track
from app.services.async_media_loader import AsyncFilmstripLoader
from app.services.thumbnail_service import ThumbnailService
from app.services.waveform_service import WaveformService
from app.ui.timeline.timeline_scene import TimelineScene
from PySide6.QtCore import QEventLoop, QTimer


class _StubThumbnailService(ThumbnailService):
    def __init__(self, frames: list[bytes]) -> None:
        super().__init__()
        self._frames = list(frames)
        self.filmstrip_calls = 0

    def get_filmstrip_bytes(  # type: ignore[override]
        self,
        project,
        clip,
        project_path=None,
        frame_count=8,
    ) -> list[bytes]:
        self.filmstrip_calls += 1
        return list(self._frames[:frame_count])

    def get_thumbnail_bytes(self, project, clip, project_path=None) -> bytes | None:  # type: ignore[override]
        return None


def _process_until(predicate, timeout_ms: int = 2000) -> None:
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


def _make_project_with_video_clip() -> tuple[object, VideoClip]:
    project = build_empty_project()
    asset = MediaAsset(
        media_id="m1",
        name="clip.mp4",
        file_path="/tmp/clip.mp4",
        media_type="video",
        duration_seconds=10.0,
        width=1920,
        height=1080,
    )
    project.media_items.append(asset)

    clip = VideoClip(
        clip_id="c1",
        name="clip.mp4",
        track_id="track-1",
        timeline_start=0.0,
        duration=4.0,
        media_id="m1",
        source_start=0.0,
        source_end=4.0,
    )
    track = Track(track_id="track-1", name="Video", track_type="video", clips=[clip])
    project.timeline = Timeline(tracks=[track])
    return project, clip


def test_async_filmstrip_loader_emits_bytes_off_thread() -> None:
    create_application(["pytest"])
    project, clip = _make_project_with_video_clip()
    service = _StubThumbnailService(frames=[b"\x89PNG", b"\x89PNG", b"\x89PNG"])
    loader = AsyncFilmstripLoader(thumbnail_service=service)

    received: list[tuple[str, str, list]] = []
    loader.filmstrip_ready.connect(lambda key, cid, frames: received.append((key, cid, list(frames))))

    loader.request(
        cache_key="key-1",
        clip_id=clip.clip_id,
        project=project,
        clip=clip,
        project_path=None,
        frame_count=3,
    )

    _process_until(lambda: bool(received))

    assert received[0][0] == "key-1"
    assert received[0][1] == "c1"
    assert len(received[0][2]) == 3
    assert service.filmstrip_calls == 1


def test_async_filmstrip_loader_dedupes_same_cache_key() -> None:
    create_application(["pytest"])
    project, clip = _make_project_with_video_clip()
    service = _StubThumbnailService(frames=[b"\x89PNG"])
    loader = AsyncFilmstripLoader(thumbnail_service=service)

    received: list[str] = []
    loader.filmstrip_ready.connect(lambda key, _cid, _frames: received.append(key))

    loader.request("dup", clip.clip_id, project, clip, None, 1)
    loader.request("dup", clip.clip_id, project, clip, None, 1)
    loader.request("dup", clip.clip_id, project, clip, None, 1)

    _process_until(lambda: bool(received))

    assert received == ["dup"]
    assert service.filmstrip_calls == 1


def test_timeline_scene_render_does_not_block_on_filmstrip() -> None:
    """Rendering a video clip must NOT call ffmpeg synchronously on the UI thread.

    The old code blocked ``__init__``/``render_timeline`` while ffmpeg ran on
    the UI thread. With the async loader, render returns immediately, the
    ClipItem starts with empty thumbnails, and ``get_filmstrip_bytes`` is only
    called once the worker thread is unblocked.

    We use a ``threading.Event`` to gate the worker so the assertion does not
    depend on wall-clock timing (which is flaky on slow CI runners like
    macOS-arm64).
    """

    import threading

    create_application(["pytest"])
    project, _clip = _make_project_with_video_clip()

    class _GatedService(_StubThumbnailService):
        def __init__(self, frames: list[bytes]) -> None:
            super().__init__(frames=frames)
            self.gate = threading.Event()
            self.entered = threading.Event()

        def get_filmstrip_bytes(self, *args, **kwargs):  # type: ignore[override]
            self.entered.set()
            self.gate.wait(timeout=5.0)
            return super().get_filmstrip_bytes(*args, **kwargs)

    service = _GatedService(frames=[b"\x89PNG"] * 4)

    scene = TimelineScene(
        project=project,
        project_path=None,
        thumbnail_service=service,
        waveform_service=WaveformService(),
    )

    # Render returned while the worker is still blocked inside get_filmstrip_bytes.
    # If the synchronous path ever returns, this would block forever or run on the
    # main thread (failing the assertion below).
    clip_item = scene._clip_items_by_id.get("c1")  # noqa: SLF001
    assert clip_item is not None
    assert clip_item._thumbnail_sources == []  # noqa: SLF001

    # Let the worker finish so the test doesn't leak threads.
    service.gate.set()
    _process_until(lambda: not scene._filmstrip_loader._pending)  # noqa: SLF001
